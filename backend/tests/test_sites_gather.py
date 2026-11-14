"""Sites loading, per-source gather dispatch and the /sites endpoints (no network)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import gather as gather_mod
from app.catalog import load_catalog
from app.extractors import appeears, gldas, grace, power, water
from app.extractors.appeears import TaskRecord
from app.gather import (
    APPEEARS_NOT_REQUESTED,
    APPEEARS_PENDING,
    conform,
    gather_site_series,
)
from app.main import app
from app.sites import Site, load_sites


def monthly(
    start: str, end: str, slope: float = 0.0, name: str | None = None
) -> pd.Series:
    idx = pd.date_range(start, end, freq="MS")
    rng = np.random.default_rng(1)
    t = np.arange(len(idx))
    values = (
        10 + 3 * np.sin(2 * np.pi * t / 12) + slope * t + rng.normal(0, 0.2, len(idx))
    )
    return pd.Series(values, index=idx, name=name)


LAKE = Site(
    "lake_mead",
    "Lake Mead (USA)",
    (-114.9, 35.9, -114.0, 36.6),
    (-114.5, 36.2),
    ("water_body", "desert"),
)
ALETSCH = Site(
    "aletsch",
    "Aletsch",
    (7.95, 46.38, 8.15, 46.56),
    (8.03, 46.47),
    ("snow", "glacier", "mountain"),
)


@pytest.fixture
def calls() -> dict:
    return {}


@pytest.fixture
def fake_sources(monkeypatch, calls):
    def fake_power(lat, lon, bands, start, end, **_):
        calls["power"] = (lat, lon, dict(bands), start, end)
        return {k: monthly("2000-01-01", "2025-12-01", name=k) for k in bands}

    def fake_grace(bbox, start, end, **_):
        calls["grace"] = (tuple(bbox), start, end)
        return monthly("2002-04-01", "2025-06-01", slope=-0.05, name="grace_tws")

    def fake_gldas(lat, lon, variables, start, end, **_):
        calls["gldas"] = (lat, lon, [v.id for v in variables], start, end)
        return {
            v.id: monthly(f"{start}-01-01", f"{end}-12-01", name=v.id)
            for v in variables
        }

    def fake_appeears(site_id, **_):
        calls["appeears"] = site_id
        return {}

    monkeypatch.setattr(power, "fetch_monthly", fake_power)
    monkeypatch.setattr(grace, "fetch_grace_series", fake_grace)
    monkeypatch.setattr(gldas, "fetch_monthly", fake_gldas)
    monkeypatch.setattr(appeears, "fetch_site_series", fake_appeears)
    monkeypatch.setattr(water, "bundle_paths", lambda *a, **k: [])  # never the real cache
    monkeypatch.setattr(
        appeears,
        "load_tasks",
        lambda *a, **k: {
            "lake_mead": TaskRecord("lake_mead", "lake_mead", "t1", "now"),
            "lake_mead_water": TaskRecord("lake_mead_water", "lake_mead_water", "t2", "now"),
        },
    )


# --------------------------------------------------------------------------- sites


def test_load_sites_real_file():
    cat = load_sites()
    assert cat.study_period == (2003, 2024)
    lake = cat.get("lake_mead")
    assert lake is not None and lake.lat == 36.2 and lake.lon == -114.5
    assert {s.id for s in cat.sites} >= {"lake_mead", "aletsch", "donana"}
    assert cat.get("nope") is None


def test_load_sites_rejects_point_outside_bbox(tmp_path: Path):
    path = tmp_path / "sites.yaml"
    path.write_text(
        "study_period: [2003, 2024]\nsites:\n"
        "  - {id: x, name: X, bbox: [0, 0, 1, 1], point: [5, 5], tags: [a]}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="outside its bbox"):
        load_sites(path)


def test_load_sites_rejects_duplicates(tmp_path: Path):
    path = tmp_path / "sites.yaml"
    row = "  - {id: x, name: X, bbox: [0, 0, 1, 1], point: [0.5, 0.5], tags: [a]}\n"
    path.write_text(
        "study_period: [2003, 2024]\nsites:\n" + row + row, encoding="utf-8"
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_sites(path)


# --------------------------------------------------------------------------- gather


def test_dispatch_per_source(fake_sources, calls):
    result = gather_site_series(LAKE, load_catalog(), 2003, 2024)
    lat, lon, bands, start, end = calls["power"]
    assert (lat, lon, start, end) == (36.2, -114.5, 2003, 2024)
    assert bands == {
        "t2m": "T2M",
        "precip": "PRECTOTCORR",
        "solar": "ALLSKY_SFC_SW_DWN",
    }
    assert calls["grace"] == (LAKE.bbox, 2003, 2024)
    assert calls["gldas"][:3] == (36.2, -114.5, ["soil_moisture", "runoff"])
    assert calls["appeears"] == "lake_mead"
    assert set(result.series) == {
        "t2m",
        "precip",
        "solar",
        "soil_moisture",
        "runoff",
        "grace_tws",
    }
    assert result.missing == {"lst_day": APPEEARS_PENDING, "water_area": APPEEARS_PENDING}
    assert set(result.sources) == {"power", "grace", "gldas"}


def test_series_are_trimmed_to_period(fake_sources):
    result = gather_site_series(LAKE, load_catalog(), 2003, 2024)
    for s in result.series.values():
        assert s.index[0] == pd.Timestamp("2003-01-01")
        assert s.index[-1] == pd.Timestamp("2024-12-01")
        assert len(s) == 22 * 12
        assert s.index.freqstr == "MS"


def test_one_source_failing_keeps_the_others(fake_sources, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("GES DISC down")

    monkeypatch.setattr(gldas, "fetch_monthly", boom)
    result = gather_site_series(LAKE, load_catalog(), 2003, 2024)
    assert {"t2m", "precip", "solar", "grace_tws"} <= set(result.series)
    assert "soil_moisture" not in result.series
    assert result.missing["soil_moisture"] == gather_mod.SOURCES["gldas"].failure
    assert result.missing["runoff"] == gather_mod.SOURCES["gldas"].failure
    assert "gldas" not in result.sources


def test_appeears_raising_degrades_into_missing(fake_sources, monkeypatch):
    def boom(site_id, **_):
        raise StopIteration

    monkeypatch.setattr(appeears, "fetch_site_series", boom)
    result = gather_site_series(ALETSCH, load_catalog(), 2003, 2024)
    assert {"lst_day", "snow_cover"} <= set(result.missing)
    assert "t2m" in result.series


def test_appeears_not_requested_reason(fake_sources, monkeypatch):
    monkeypatch.setattr(appeears, "load_tasks", lambda *a, **k: {})
    result = gather_site_series(ALETSCH, load_catalog(), 2003, 2024)
    assert result.missing["snow_cover"] == APPEEARS_NOT_REQUESTED


def test_all_nan_series_goes_to_missing(fake_sources, monkeypatch):
    monkeypatch.setattr(
        grace, "fetch_grace_series", lambda *a, **k: monthly("1990-01-01", "1995-12-01")
    )
    result = gather_site_series(LAKE, load_catalog(), 2003, 2024)
    assert "grace_tws" not in result.series
    assert "no total water stored" in result.missing["grace_tws"]


def test_conform_does_not_mutate_and_normalizes_mid_month():
    raw = pd.Series(
        [1.0, 2.0], index=pd.to_datetime(["2003-01-16", "2003-03-15"]), name="x"
    )
    out = conform(raw, 2003, 2003)
    assert raw.index[0] == pd.Timestamp("2003-01-16")
    assert out.loc["2003-01-01"] == 1.0 and np.isnan(out.loc["2003-02-01"])
    assert len(out) == 12 and out.name == "x"


# --------------------------------------------------------------------------- endpoints


def test_sites_endpoint():
    body = TestClient(app).get("/sites").json()
    lake = next(s for s in body if s["id"] == "lake_mead")
    assert lake["bbox"] == [-114.9, 35.9, -114.0, 36.6] and "desert" in lake["tags"]


def test_site_sweep_endpoint(fake_sources):
    response = TestClient(app).get("/sites/lake_mead/sweep")
    assert response.status_code == 200
    body = response.json()
    assert body["start"] == 2003 and body["end"] == 2024
    assert body["site"]["id"] == "lake_mead"
    ids = {v["id"] for v in body["variables"]}
    # lake_mead declares upstream_climate in sites.yaml -> two extra driver rows
    assert ids == {
        "t2m", "precip", "solar", "t2m_upstream", "precip_upstream",
        "soil_moisture", "runoff", "grace_tws",
    }
    assert all(v["residual_pct_non_climate"] is None for v in body["variables"])
    grace_row = next(v for v in body["variables"] if v["id"] == "grace_tws")
    assert grace_row["direction"] == "down"
    assert body["missing"] == {"lst_day": APPEEARS_PENDING, "water_area": APPEEARS_PENDING}
    assert {s["id"] for s in body["sources"]} == {"power", "grace", "gldas"}


def test_site_sweep_custom_period(fake_sources, calls):
    response = TestClient(app).get(
        "/sites/lake_mead/sweep", params={"start": 2005, "end": 2020}
    )
    assert response.status_code == 200
    assert calls["power"][3:] == (2005, 2020)


def test_site_sweep_unknown_site_404():
    response = TestClient(app).get("/sites/atlantis/sweep")
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "atlantis" in detail and "lake_mead" in detail


def test_site_sweep_bad_years_422():
    response = TestClient(app).get(
        "/sites/lake_mead/sweep", params={"start": 2020, "end": 2010}
    )
    assert response.status_code == 422


def test_water_area_not_downloaded_is_missing_with_appeears_wording(fake_sources, monkeypatch):
    monkeypatch.setattr(appeears, "load_tasks", lambda *a, **k: {})
    result = gather_site_series(LAKE, load_catalog(), 2003, 2024)
    assert result.missing["water_area"] == APPEEARS_NOT_REQUESTED
    assert "appeears_water" not in result.sources


def test_water_area_dispatch_when_downloaded(fake_sources, monkeypatch, tmp_path):
    calls = {}

    def fake_fetch(bundle, start, end):
        calls["bundle"] = bundle
        return monthly(f"{start}-01-01", f"{end}-12-01", slope=-0.1, name="water_area")

    monkeypatch.setattr(water, "bundle_paths", lambda *a, **k: [tmp_path / "x.nc"])
    monkeypatch.setattr(water, "fetch_water_area", fake_fetch)
    result = gather_site_series(LAKE, load_catalog(), 2003, 2024)
    assert calls["bundle"].name == "lake_mead_water"
    assert "water_area" in result.series and "appeears_water" in result.sources
    assert "water_area" not in gather_site_series(ALETSCH, load_catalog(), 2003, 2024).series


def test_local_netcdf_sources_never_overlap_with_the_pool(fake_sources, monkeypatch):
    """netCDF4/HDF5 is not thread-safe: AppEEARS reads start only after GRACE is done."""
    import threading

    grace_done = threading.Event()
    seen = {}

    def slow_grace(bbox, start, end, **_):
        grace_done.set()
        return monthly("2002-04-01", "2025-06-01", name="grace_tws")

    def check_appeears(site_id, **_):
        seen["grace_done_first"] = grace_done.is_set()
        seen["thread"] = threading.current_thread() is threading.main_thread()
        return {}

    monkeypatch.setattr(grace, "fetch_grace_series", slow_grace)
    monkeypatch.setattr(appeears, "fetch_site_series", check_appeears)
    gather_site_series(LAKE, load_catalog(), 2003, 2024)
    assert seen == {"grace_done_first": True, "thread": True}
