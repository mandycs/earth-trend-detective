"""Yearly variables in the detective: GIBS twins off-case, heat stress on reefs, annual trend path."""

import numpy as np
import pandas as pd
import pytest

from app import gather
from app.catalog import load_catalog
from app.detective.ledger import Ledger
from app.detective.place import Place
from app.detective.session import Session
from app.detective.tools import analysis
from app.detective.tools import data as tools
from app.extractors import erddap, gibs_values


def _session(tags=("vegetated",), site_id=None, lat=37.0, lon=-4.5) -> Session:
    place = Place(lat=lat, lon=lon, bbox=(lon - 0.1, lat - 0.1, lon + 0.1, lat + 0.1), tags=tuple(tags), site_id=site_id)
    return Session(ledger=Ledger(), place=place, catalog=load_catalog(), series={})


def _yearly(start=2003, end=2024, slope=0.004, dropped=()) -> pd.Series:
    years = [y for y in range(start, end + 1) if y not in dropped]
    rng = np.random.default_rng(1)
    values = 0.4 + slope * (np.array(years) - start) + rng.normal(0, 0.003, len(years))
    s = pd.Series(values, index=pd.to_datetime([f"{y}-01-01" for y in years]))
    s.attrs = {"temporal": "annual", "palette_step": 0.005, "months": list(range(1, 13)), "dropped_years": list(dropped)}
    return s


@pytest.fixture
def gibs_calls(monkeypatch):
    calls = []

    def fake(layer, bbox, start, end, client=None):
        calls.append((layer.id, start, end))
        return _yearly(start, end)

    monkeypatch.setattr(gibs_values, "fetch_annual", fake)
    return calls


def _rows(session):
    return {r["id"]: r for r in tools.list_variables(session)["variables"]}


def test_off_case_ndvi_becomes_ndvi_gibs():
    rows = _rows(_session(tags=("vegetated", "snow")))
    assert "ndvi" not in rows and "lst_day" not in rows
    for twin in ("ndvi_gibs", "lst_gibs"):
        assert rows[twin]["available"] is True, rows[twin]
        assert rows[twin]["source"] == "gibs"
    assert rows["et"]["available"] is False and rows["et"]["reason"] == tools.OFF_CASE_REASON  # no GIBS twin


def test_inside_a_case_the_monthly_series_stays_and_the_twin_is_hidden(gibs_calls):
    s = _session(tags=("wetland", "vegetated", "agriculture"), site_id="donana")
    rows = _rows(s)
    assert "ndvi" in rows and "ndvi_gibs" not in rows
    got = tools.get_series(s, var_id="ndvi_gibs")
    assert got["status"] == "not_available" and got["reason"] == tools.ON_CASE_TWIN_REASON
    assert gibs_calls == []


def test_off_case_ndvi_points_to_its_twin():
    got = tools.get_series(_session(), var_id="ndvi")
    assert got["status"] == "not_available" and got["use_instead"] == "ndvi_gibs"


def test_ndvi_gibs_goes_through_the_annual_trend_path(gibs_calls):
    s = _session()
    got = tools.get_series(s, var_id="ndvi_gibs")
    assert got["status"] == "ok", got
    assert got["basis"] == "annual" and got["n_years"] == 22
    assert got["precision"] == "palette step ≈ 0.005 NDVI"
    assert len(got["chart"]) == 22 and "n_months" not in got
    series = s.series[got["series_id"]]
    assert len(series) == 22  # one value per year, never spread over months
    res = tools.trend_test(s, series_id=got["series_id"])
    assert res["basis"] == "annual" and res["status"] == "observed"
    assert res["precision"] == "palette step ≈ 0.005 NDVI"
    assert res["n_years"] == 22 and res["too_short"] is False
    assert res["slope_per_decade"] > 0 and res["direction"] == "up"
    assert res["test_id"] == "t1" and s.ledger.n_tests == 1 and res["n_tests_so_far"] == 1
    assert "annual mean of monthly values" in s.ledger.test("t1").label


def test_annual_test_counts_in_the_session_family(gibs_calls, monkeypatch):
    idx = pd.date_range("2003-01-01", "2024-12-01", freq="MS")
    monthly = pd.Series(10 + np.sin(2 * np.pi * idx.month / 12), index=idx)
    monkeypatch.setattr(gather, "FETCHERS", {**gather.FETCHERS, "power": lambda site, vs, *a: {v.id: monthly for v in vs}})
    s = _session()
    t2m = tools.trend_test(s, series_id=tools.get_series(s, var_id="t2m")["series_id"])
    green = tools.trend_test(s, series_id=tools.get_series(s, var_id="ndvi_gibs")["series_id"])
    assert "basis" not in t2m or t2m["basis"] == "monthly"
    assert green["n_tests_so_far"] == 2 and s.ledger.n_tests == 2


def test_transparent_years_leave_too_few_years(monkeypatch):
    monkeypatch.setattr(gibs_values, "fetch_annual", lambda layer, bbox, start, end, client=None: _yearly(2003, 2014, dropped=(2004, 2006, 2008)))
    s = _session()
    got = tools.get_series(s, var_id="ndvi_gibs", start=2003, end=2014)
    assert got["dropped_years"] == [2004, 2006, 2008]
    res = tools.trend_test(s, series_id=got["series_id"])
    assert res["too_short"] is True and res["n_years"] == 9
    assert isinstance(res["years_needed"], int) and res["years_needed"] >= 1
    assert res["verdict"] == "unknown"


def test_no_climate_split_on_yearly_values(gibs_calls):
    got = analysis.climate_residual(_session(), var_id="ndvi_gibs")
    assert got["status"] == "not_available" and got["reason"] == analysis.ANNUAL_RESIDUAL_REASON


def test_years_needed_for_uses_the_annual_formula(monkeypatch):
    monkeypatch.setattr(gibs_values, "fetch_annual", lambda layer, bbox, start, end, client=None: _yearly(2015, 2023))
    s = _session()
    got = tools.get_series(s, var_id="ndvi_gibs", start=2015, end=2023)
    out = analysis.years_needed_for(s, got["series_id"])
    assert isinstance(out["years_needed"], int) and out["years_needed"] >= 1


# --------------------------------------------------------------------------- heat stress


def _dhw(monkeypatch):
    calls = []

    def fake(dataset, variable, lat, lon, start, end, months=erddap.YEARLY_MAX_MONTHS, client=None):
        calls.append((lat, months))
        s = pd.Series(
            np.linspace(1, 8, end - start + 1), index=pd.to_datetime([f"{y}-01-01" for y in range(start, end + 1)])
        )
        s.attrs = {"cell": (lat, lon), "temporal": "annual", "missing_years": []}
        return s, (lat, lon)

    monkeypatch.setattr(erddap, "fetch_point_yearly_max", fake)
    return calls


def test_heat_stress_offered_on_reefs_only(monkeypatch):
    calls = _dhw(monkeypatch)
    reef = _session(tags=("coast", "reef"), lat=-18.3, lon=147.7)
    assert _rows(reef)["dhw"]["available"] is True
    sea = _session(tags=("ocean",), lat=36.0, lon=-10.0)
    row = _rows(sea)["dhw"]
    assert row["available"] is False and row["reason"] == tools.NOT_REEF_REASON
    got = tools.get_series(sea, var_id="dhw")
    assert got["status"] == "not_available" and got["reason"] == tools.NOT_REEF_REASON
    land = _rows(_session())["dhw"]
    assert land["available"] is False and land["reason"] == tools.NOT_SEA_REASON
    assert calls == []


@pytest.mark.parametrize(("lat", "months"), [(-18.3, (1, 6)), (24.5, (7, 12))])
def test_heat_stress_window_follows_the_hemisphere(monkeypatch, lat, months):
    calls = _dhw(monkeypatch)
    s = _session(tags=("coast", "reef"), lat=lat, lon=147.7)
    got = tools.get_series(s, var_id="dhw")
    assert got["status"] == "ok", got
    assert calls == [(lat, months)]
    assert got["basis"] == "annual" and "precision" not in got
    res = tools.trend_test(s, series_id=got["series_id"])
    assert res["basis"] == "annual" and res["status"] == "observed" and "precision" not in res
    assert res["n_years"] == s.end - s.start + 1


def test_no_completed_year_is_a_plain_answer(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("must not fetch")

    monkeypatch.setattr(gibs_values, "fetch_annual", boom)
    monkeypatch.setattr(gibs_values, "_this_year", lambda: 2026)
    got = tools.get_series(_session(), var_id="ndvi_gibs", start=2026, end=2026)
    assert got["status"] == "not_available" and got["reason"] == tools.NO_COMPLETED_YEAR_REASON
    assert "transient" not in got and "evidence_id" in got  # cached: not a source failure


def test_missing_years_reach_the_model(monkeypatch):
    def fake(layer, bbox, start, end, client=None):
        s = _yearly(start, end, dropped=(2010,))
        s.attrs |= {"missing_years": [2010], "dropped_years": []}
        return s

    monkeypatch.setattr(gibs_values, "fetch_annual", fake)
    got = tools.get_series(_session(), var_id="ndvi_gibs")
    assert got["missing_years"] == [2010] and "dropped_years" not in got


def test_snow_gibs_is_never_offered_and_snow_cover_has_no_twin(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("must not fetch")

    monkeypatch.setattr(gibs_values, "fetch_annual", boom)
    s = _session(tags=("snow", "mountain"))
    rows = _rows(s)
    assert rows["snow_gibs"]["available"] is False and rows["snow_gibs"]["reason"] == tools.SNOW_GIBS_REASON
    assert rows["snow_cover"]["available"] is False and rows["snow_cover"]["reason"] == tools.OFF_CASE_REASON
    got = tools.get_series(s, var_id="snow_gibs")
    assert got["status"] == "not_available" and got["reason"] == tools.SNOW_GIBS_REASON
    off = tools.get_series(s, var_id="snow_cover")
    assert off["reason"] == tools.OFF_CASE_REASON and "use_instead" not in off
    in_case = _rows(_session(tags=("snow", "glacier"), site_id="aletsch"))
    assert in_case["snow_gibs"]["available"] is False and in_case["snow_cover"]["available"] is True
