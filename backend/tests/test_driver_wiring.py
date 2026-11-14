"""Per-site extra climate drivers: sites.yaml fields, catalog entries, gather wiring (no network)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app import gather as gather_mod
from app.catalog import load_catalog, variables_for_site
from app.extractors import appeears, gldas, grace, power
from app.gather import gather_site_series
from app.sites import Site, UpstreamClimate, load_sites

EXTRA_DRIVERS = {"t2m_upstream", "precip_upstream", "degree_days", "winter_precip"}


def _monthly(start: str, end: str, base: float) -> pd.Series:
    idx = pd.date_range(start, end, freq="MS")
    t = np.arange(len(idx))
    return pd.Series(base + 3 * np.sin(2 * np.pi * t / 12), index=idx)


@pytest.fixture
def power_calls(monkeypatch) -> list:
    calls: list = []

    def fake_power(lat, lon, bands, start, end, **_):
        calls.append((lat, lon, dict(bands)))
        # value depends on the point, so averaging is visible
        base = {"T2M": lon / 10.0, "PRECTOTCORR": 1.0 + lat / 100.0, "ALLSKY_SFC_SW_DWN": 20.0}
        return {k: _monthly("2003-01-01", "2024-12-01", base[b]) for k, b in bands.items()}

    monkeypatch.setattr(power, "fetch_monthly", fake_power)
    monkeypatch.setattr(grace, "fetch_grace_series", lambda *a, **k: _monthly("2003-01-01", "2024-12-01", 0.0))
    monkeypatch.setattr(gldas, "fetch_monthly", lambda lat, lon, variables, *a, **k: {})
    monkeypatch.setattr(appeears, "fetch_site_series", lambda *a, **k: {})
    monkeypatch.setattr(appeears, "load_tasks", lambda *a, **k: {})
    return calls


UPSTREAM = UpstreamClimate(points=((-106.5, 39.5), (-109.8, 43.0)), label="Upper Colorado basin")
MEAD = Site(
    "lake_mead", "Lake Mead", (-114.9, 35.9, -114.0, 36.6), (-114.5, 36.2), ("water_body", "desert"),
    upstream_climate=UPSTREAM,
)
ALETSCH = Site(
    "aletsch", "Aletsch", (7.95, 46.38, 8.15, 46.56), (8.03, 46.47), ("snow", "glacier", "mountain"),
    snow_terms=True,
)


# --------------------------------------------------------------------------- sites.yaml


def test_real_sites_declare_extra_drivers():
    cat = load_sites()
    mead, aletsch, donana = cat.get("lake_mead"), cat.get("aletsch"), cat.get("donana")
    assert mead.upstream_climate is not None
    assert len(mead.upstream_climate.points) >= 1
    assert "Colorado" in mead.upstream_climate.label
    assert not mead.snow_terms
    assert aletsch.snow_terms and aletsch.upstream_climate is None
    assert donana.upstream_climate is None and not donana.snow_terms


def test_site_defaults_keep_old_constructor():
    s = Site("x", "X", (0, 0, 1, 1), (0.5, 0.5), ("a",))
    assert s.upstream_climate is None and s.snow_terms is False


def _write(tmp_path: Path, extra: str) -> Path:
    path = tmp_path / "sites.yaml"
    path.write_text(
        "study_period: [2003, 2024]\nsites:\n"
        "  - {id: x, name: X, bbox: [0, 0, 1, 1], point: [0.5, 0.5], tags: [a]" + extra + "}\n",
        encoding="utf-8",
    )
    return path


def test_upstream_single_point_form(tmp_path: Path):
    site = load_sites(_write(tmp_path, ", upstream_climate: {point: [10, 20], label: Up}")).sites[0]
    assert site.upstream_climate == UpstreamClimate(points=((10.0, 20.0),), label="Up")


def test_upstream_rejects_bad_point(tmp_path: Path):
    with pytest.raises(ValueError, match="upstream"):
        load_sites(_write(tmp_path, ", upstream_climate: {points: [[500, 20]], label: Up}"))
    with pytest.raises(ValueError, match="upstream"):
        load_sites(_write(tmp_path, ", upstream_climate: {label: Up}"))


# --------------------------------------------------------------------------- catalog


def test_extra_drivers_are_catalog_drivers_never_picked_by_tags():
    catalog = load_catalog()
    by_id = {v.id: v for v in catalog}
    assert EXTRA_DRIVERS <= set(by_id)
    assert all(by_id[d].role == "driver" and by_id[d].source == "power" for d in EXTRA_DRIVERS)
    for tags in (["snow", "glacier", "mountain"], ["water_body", "desert"], ["any"]):
        assert not EXTRA_DRIVERS & {v.id for v in variables_for_site(catalog, tags)}
    # no impact needs them in its base model, so missing extras never skip a residual
    assert not any(EXTRA_DRIVERS & set(v.drivers) for v in catalog)


# --------------------------------------------------------------------------- gather


def test_gather_fetches_and_averages_upstream_points(power_calls):
    result = gather_site_series(MEAD, load_catalog(), 2003, 2024)
    points = [(lat, lon) for lat, lon, _ in power_calls]
    assert points[0] == (36.2, -114.5)
    assert set(points[1:]) == {(39.5, -106.5), (43.0, -109.8)}
    assert all(b == {"t2m_upstream": "T2M", "precip_upstream": "PRECTOTCORR"} for *_, b in power_calls[1:])
    up_t = result.series["t2m_upstream"]
    assert up_t.mean() == pytest.approx(((-106.5 + -109.8) / 2) / 10.0, abs=1e-6)
    assert {"degree_days", "winter_precip"}.isdisjoint(result.series)
    assert "power" in result.sources


def test_upstream_failure_keeps_local_drivers(power_calls, monkeypatch):
    real = power.fetch_monthly

    def flaky(lat, lon, bands, start, end, **kw):
        if lat != 36.2:
            raise RuntimeError("POWER down")
        return real(lat, lon, bands, start, end, **kw)

    monkeypatch.setattr(power, "fetch_monthly", flaky)
    result = gather_site_series(MEAD, load_catalog(), 2003, 2024)
    assert {"t2m", "precip", "solar"} <= set(result.series)
    assert "t2m_upstream" not in result.series
    assert "t2m_upstream" in result.missing


def test_gather_derives_snow_terms_from_local_power(power_calls):
    result = gather_site_series(ALETSCH, load_catalog(), 2003, 2024)
    assert len(power_calls) == 1  # no extra request: derived from the same local T2M/precip
    assert set(power_calls[0][2].values()) == {"T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"}
    assert {"degree_days", "winter_precip"} <= set(result.series)
    assert (result.series["degree_days"] >= 0).all()
    assert result.series["winter_precip"].loc["2003-01-01":"2003-09-01"].isna().all()
    assert {"t2m_upstream", "precip_upstream"}.isdisjoint(result.series)


def test_plain_site_gets_no_extra_drivers(power_calls):
    plain = Site("p", "P", (0, 0, 1, 1), (0.5, 0.5), ("desert",))
    result = gather_site_series(plain, load_catalog(), 2003, 2024)
    assert EXTRA_DRIVERS.isdisjoint(result.series) and EXTRA_DRIVERS.isdisjoint(result.missing)
    assert len(power_calls) == 1
    assert gather_mod.SOURCES["power"]
