"""The reef site.json: sea temperature, the heat-stress record, chlorophyll. Offline, synthetic series."""

from __future__ import annotations

import copy
import datetime as dt
import json
import re

import numpy as np
import pandas as pd
import pytest

from app import layers, site_export
from app.catalog import load_catalog
from app.detective.ledger import Ledger
from app.detective.place import Place
from app.detective.session import Session
from app.detective.tools import context
from app.reef import dhw
from app.reef import export as reef_export
from app.reef.points import REEF_POINTS, SITE_ID
from app.site_story import format_number
from app.sites import load_sites
from tests.reef.test_dhw import _scout_yearly

START, END = 2003, 2024
TODAY = dt.date(2026, 11, 15)


def _months() -> pd.DatetimeIndex:
    return pd.date_range(f"{START}-01-01", f"{END}-12-01", freq="MS")


def _sst() -> pd.Series:
    idx = _months()
    rng = np.random.default_rng(7)
    t = (idx.year - START) + (idx.month - 1) / 12
    season = 2.5 * np.cos(2 * np.pi * (idx.month - 2) / 12)
    return pd.Series(26.0 + season + 0.025 * t + rng.normal(0, 0.05, len(idx)), index=idx, name="sst")


def _chl(slope_per_year: float = 0.0) -> pd.Series:
    idx = _months()
    rng = np.random.default_rng(11)
    t = (idx.year - START) + (idx.month - 1) / 12
    return pd.Series(-0.3 + slope_per_year * t + rng.normal(0, 0.15, len(idx)), index=idx, name="chlorophyll")


def _heat() -> dict:
    return dhw.heat_stress_summary(_scout_yearly(), list(REEF_POINTS), START, END)


def _doc(tmp_path, chl: pd.Series | None = None) -> dict:
    site = load_sites().get(SITE_ID)
    series = reef_export.ReefSeries(sst=_sst(), chlorophyll_log10=_chl() if chl is None else chl)
    return reef_export.build_reef_site_json(
        site, load_catalog(), START, END, tmp_path / SITE_ID, series, _heat(), today=TODAY
    )


def _row(doc: dict, var_id: str) -> dict:
    return next(v for v in doc["variables"] if v["id"] == var_id)


def test_sst_is_lead_and_real(tmp_path):
    lead = _doc(tmp_path)["variables"][0]
    assert lead["id"] == "sst"
    assert lead["verdict"] == "real" and lead["direction"] == "up"
    assert lead["kind"] == "trend"
    assert lead["footprint"] == {
        "km": 474,
        "label": "the whole map, averaged (NASA JPL MUR, sampled about every 5 km)",
    }


def test_dhw_row_is_events_second(tmp_path):
    row = _doc(tmp_path)["variables"][1]
    assert row["id"] == "dhw" and row["kind"] == "events"
    assert row["p_value"] is None and row["sen_slope_per_decade"] is None
    assert row["q_value"] is None and row["ci_low"] is None and row["years_needed"] is None
    assert [t["value"] for t in row["thresholds"]] == [4.0, 8.0]
    assert "Not a trend test" in row["note"]
    assert "1 in 2003–2013, 20 in 2014–2024" in row["note"]
    assert row["badge"] == "Heat-stress record" and row["unit"] == "°C-weeks"
    assert row["series"] == dhw.worst_reef_series(_heat())
    assert row["footprint"]["km"] == 5
    assert set(site_export.VARIABLE_FIELDS) <= set(row)


def test_no_residual_anywhere(tmp_path):
    doc = _doc(tmp_path)
    for row in doc["variables"]:
        assert row["residual_pct_non_climate"] is None
        assert row["residual_pct_range"] is None
    assert re.search(r"split|climate", doc["caveats"][0], re.I)
    assert not re.search(r"clue", doc["caveats"][0], re.I)
    assert doc["caveats"] == list(reef_export.REEF_CAVEATS)


def test_no_crw_sst_and_no_land_variables(tmp_path):
    doc = _doc(tmp_path)
    assert {v["id"] for v in doc["variables"]} == {"sst", "dhw", "chlorophyll"}
    for src in doc["sources"]:
        assert "NOAA_DHW_monthly" not in src["title"] and "NOAA_DHW_monthly" not in src["url"]
    assert {"title", "url"} <= set(doc["sources"][0])


def test_chlorophyll_log10_unit_and_note(tmp_path):
    row = _row(_doc(tmp_path), "chlorophyll")
    assert row["unit"] == "log10(mg/m³)"
    assert row["verdict"] == "unknown"
    assert row["note"].startswith("No trend detected. Read from water colour near the coast")
    assert row["footprint"] == {"km": 4, "label": "one 4 km MODIS pixel off the Burdekin River mouth"}


def test_chlorophyll_note_without_prefix_when_a_trend_is_found(tmp_path):
    row = _row(_doc(tmp_path, chl=_chl(slope_per_year=0.05)), "chlorophyll")
    assert row["verdict"] != "unknown"
    assert row["note"].startswith("Read from water colour near the coast")


def test_reef_catalog_only_changes_chlorophyll_units():
    catalog = load_catalog()
    reef = reef_export.reef_catalog(catalog)
    assert len(reef) == len(catalog)
    for before, after in zip(catalog, reef):
        if before.id == "chlorophyll":
            assert after.units == "log10(mg/m³)"
            assert after.dataset == before.dataset
        else:
            assert after == before


def test_headline_from_figures(tmp_path):
    doc = _doc(tmp_path)
    slope = format_number(doc["variables"][0]["sen_slope_per_decade"])
    assert f"({slope} °C per decade)" in doc["headline"]
    assert "Heat stress at or above 4 °C-weeks: 1 reef-year in 2003–2013, 20 in 2014–2024." in doc["headline"]
    assert doc["heat_stress"] == _heat()
    assert doc["vertical_exaggeration"] == 30
    assert doc["country"] == "Australia"
    assert doc["missing"] == {}
    json.dumps(doc, allow_nan=False)


def test_headline_and_note_plural_and_threshold_from_heat():
    heat = copy.deepcopy(_heat())
    heat["periods"][0]["reef_years_at_or_above"]["4"] = 3
    row = {"id": "sst", "verdict": "real", "sen_slope_per_decade": 0.25}
    assert "at or above 4 °C-weeks: 3 reef-years in 2003–2013, 20 in 2014–2024." in reef_export.reef_headline(row, heat)
    assert reef_export.dhw_note(_heat()) == (
        "Not a trend test. Reef-years at or above 4 °C-weeks, five reefs: 1 in 2003–2013, 20 in 2014–2024."
    )
    heat["thresholds"][0]["value"] = 8.0  # the counts follow the first threshold's key
    assert "at or above 8 °C-weeks: 0 reef-years in 2003–2013, 6 in 2014–2024." in reef_export.reef_headline(row, heat)


def test_failed_years_are_listed_in_missing(tmp_path):
    site = load_sites().get(SITE_ID)
    series = reef_export.ReefSeries(
        sst=_sst(), chlorophyll_log10=_chl(), sst_missing_years=(2019, 2011), chlorophyll_missing_years=(2007,)
    )
    doc = reef_export.build_reef_site_json(
        site, load_catalog(), START, END, tmp_path / SITE_ID, series, _heat(), today=TODAY
    )
    assert doc["missing"] == {
        "sst": "no data for 2011, 2019 (fetch failed)",
        "chlorophyll": "no data for 2007 (fetch failed)",
    }
    only_sst = reef_export.ReefSeries(sst=_sst(), chlorophyll_log10=_chl(), sst_missing_years=(2011,))
    assert reef_export.reef_missing(only_sst) == {"sst": "no data for 2011 (fetch failed)"}


def test_load_series_keeps_failed_years(monkeypatch, tmp_path):
    from app.extractors import erddap
    from app.reef import sst

    grid = sst.MurGrid(
        times=_months(), monthly=_sst().to_numpy().reshape(-1, 1, 1), lat=np.array([-19.0]), lon=np.array([147.0]),
        years=tuple(range(START, END + 1)), missing_years=(2011,),
    )
    monkeypatch.setattr(sst, "mur_grid", lambda *a, **k: grid)

    def fake_point(*a, **k):
        raw = (10 ** _chl()).rename("chlor_a")
        raw.attrs["missing_years"] = [2019]
        return raw, (-19.45, 147.75)

    monkeypatch.setattr(erddap, "fetch_point_monthly", fake_point)
    site = load_sites().get(SITE_ID)
    series = reef_export.load_series(site, START, END, tmp_path, offline=True)
    assert series.sst_missing_years == (2011,)
    assert series.chlorophyll_missing_years == (2019,)


def test_headline_is_none_when_sst_not_real():
    row = {"id": "sst", "verdict": "unknown", "sen_slope_per_decade": 0.1}
    assert reef_export.reef_headline(row, _heat()) is None


def test_site_export_routes_sea_site(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(reef_export, "export_reef", lambda site, sites_dir, *a, **k: calls.append(
        (site.id, sites_dir)) or {"id": site.id})

    def no_gather(*a, **k):
        raise AssertionError("the land gather must not run for the reef")

    monkeypatch.setattr(site_export, "gather_site_series", no_gather)
    monkeypatch.setattr(site_export, "build_site_json", no_gather)
    assert site_export.export_site(SITE_ID, sites_dir=tmp_path) == {"id": SITE_ID}
    assert calls == [(SITE_ID, tmp_path)]


def test_export_reef_offline_writes_site_and_layers(monkeypatch, tmp_path):
    monkeypatch.setattr(reef_export, "load_series", lambda site, start, end, cache_dir, offline: reef_export.ReefSeries(
        sst=_sst(), chlorophyll_log10=_chl()))
    monkeypatch.setattr(reef_export, "load_heat", lambda start, end, cache_dir, offline: _heat())
    site = load_sites().get(SITE_ID)
    doc = reef_export.export_reef(site, tmp_path, tmp_path / "cache")
    written = json.loads((tmp_path / SITE_ID / "site.json").read_text(encoding="utf-8"))
    assert written == doc and written["variables"][1]["id"] == "dhw"
    assert (tmp_path / SITE_ID / "layers.json").is_file()


def test_offline_client_never_reaches_the_network():
    client = reef_export.offline_client()
    with pytest.raises(FileNotFoundError, match="offline"):
        client.get("https://coastwatch.pfeg.noaa.gov/erddap/griddap/x.csv")


def test_solved_case_reads_reef(monkeypatch, tmp_path):
    doc = _doc(tmp_path)
    site_export.write_site_json(doc, tmp_path / SITE_ID)
    monkeypatch.setattr(layers, "SITES_DIR", tmp_path)
    place = Place(lat=-18.8, lon=147.6, bbox=(145.5, -21.0, 150.0, -17.0), tags=("reef",))
    session = Session(ledger=Ledger(), place=place, catalog=load_catalog(), series={})
    out = context.solved_case(session, site_id=SITE_ID)
    assert out["status"] == "ok"
    assert "dhw" in {v["id"] for v in out["variables"]}


def _heat_with_gaps() -> dict:
    yearly = copy.deepcopy(_scout_yearly())
    outer = next(p.id for p in REEF_POINTS if p.id == "outer")
    heron = next(p.id for p in REEF_POINTS if p.id == "heron")
    for y in (2012, 2013, 2014):
        yearly[outer].pop(y, None)
    yearly[heron].pop(2022, None)
    return dhw.heat_stress_summary(yearly, list(REEF_POINTS), START, END)


def test_reef_years_without_data_are_listed_and_said(tmp_path):
    heat = _heat_with_gaps()
    site = load_sites().get(SITE_ID)
    series = reef_export.ReefSeries(sst=_sst(), chlorophyll_log10=_chl())
    doc = reef_export.build_reef_site_json(site, load_catalog(), START, END, tmp_path / SITE_ID, series, heat, today=TODAY)
    assert doc["missing"]["dhw"] == (
        "no data for 4 reef-years (fetch failed): Outer shelf (central) 2012, 2013, 2014; Heron Reef (south) 2022"
    )
    assert doc["headline"].endswith("(4 reef-years without data are not counted).")
    dhw_row = next(v for v in doc["variables"] if v["id"] == "dhw")
    assert dhw_row["note"].endswith(" 4 reef-years without data are not counted.")
    # no gaps: nothing listed, nothing added
    assert "dhw" not in _doc(tmp_path)["missing"]
    assert "without data" not in _doc(tmp_path)["headline"]
