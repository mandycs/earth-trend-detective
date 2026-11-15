import numpy as np
import pandas as pd
import pytest

from app import gather
from app.catalog import load_catalog
from app.detective.ledger import Ledger
from app.detective.place import Place
from app.detective.session import Session
from app.detective.tools import TOOLS
from app.detective.tools import data as tools
from app.investigate import landcover
from app.investigate.landcover import LandCover


def _synthetic(start: int = 2003, end: int = 2024, slope_per_year: float = 0.05) -> pd.Series:
    idx = pd.date_range(f"{start}-01-01", f"{end}-12-01", freq="MS")
    t = np.arange(idx.size) / 12.0
    rng = np.random.default_rng(0)
    seasonal = 5 * np.sin(2 * np.pi * idx.month / 12)
    return pd.Series(10 + seasonal + slope_per_year * t + rng.normal(0, 0.2, idx.size), index=idx)


def _session(tags=("vegetated",), site_id=None) -> Session:
    place = Place(lat=37.0, lon=-4.5, bbox=(-4.6, 36.9, -4.4, 37.1), tags=tuple(tags), site_id=site_id)
    return Session(ledger=Ledger(), place=place, catalog=load_catalog(), series={})


@pytest.fixture
def power_calls(monkeypatch):
    calls = []

    def fake_power(site, variables, catalog, start, end):
        calls.append((site, tuple(v.id for v in variables), start, end))
        return {v.id: _synthetic(start, end).rename(v.id) for v in variables}

    monkeypatch.setattr(gather, "FETCHERS", {**gather.FETCHERS, "power": fake_power})
    return calls


def test_get_series_then_trend_test_logs_a_test(power_calls):
    s = _session()
    got = tools.get_series(s, var_id="t2m")
    assert got["status"] == "ok"
    assert got["series_id"] in s.series
    assert got["evidence_id"].startswith("e")
    assert got["n_months"] == 264
    assert got["chart"][0]["year"] == 2003 and len(got["chart"]) == 22
    res = tools.trend_test(s, series_id=got["series_id"])
    assert s.ledger.n_tests == 1
    assert res["verdict"] in {"real", "likely", "unknown"}
    assert res["direction"] == "up"
    assert res["n_tests_so_far"] == 1
    assert res["slope_per_decade"] > 0


def test_repeated_calls_hit_the_ledger_cache(power_calls):
    s = _session()
    first = tools.get_series(s, var_id="t2m")
    again = tools.get_series(s, var_id="t2m")
    assert again["evidence_id"] == first["evidence_id"]
    assert len(power_calls) == 1
    t1 = tools.trend_test(s, series_id=first["series_id"])
    t2 = tools.trend_test(s, series_id=first["series_id"])
    assert t1["evidence_id"] == t2["evidence_id"]
    assert s.ledger.n_tests == 1


def test_get_series_no_data_is_not_available(monkeypatch):
    monkeypatch.setattr(gather, "FETCHERS", {**gather.FETCHERS, "power": lambda *a: {}})
    s = _session()
    got = tools.get_series(s, var_id="t2m")
    assert got["status"] == "not_available"
    assert got["reason"]
    assert not s.series


def test_get_series_failing_source_is_not_available(monkeypatch):
    def boom(*a):
        raise RuntimeError("down")

    monkeypatch.setattr(gather, "FETCHERS", {**gather.FETCHERS, "power": boom})
    got = tools.get_series(_session(), var_id="t2m")
    assert got["status"] == "not_available"


def test_get_series_unknown_variable():
    got = tools.get_series(_session(), var_id="nope")
    assert got["status"] == "not_available"


def test_appeears_variables_not_available_off_case():
    got = tools.list_variables(_session(tags=("vegetated",)))
    rows = {r["id"]: r for r in got["variables"]}
    assert "ndvi" not in rows and rows["ndvi_gibs"]["available"] is True  # swapped for its GIBS twin
    assert rows["et"]["available"] is False  # no twin: listed as not available here
    assert rows["et"]["reason"].startswith("not_available_here")
    assert rows["t2m"]["available"] is True
    assert rows["t2m"]["definition"]
    assert rows["t2m"]["resolution"]
    assert "evidence_id" in got


def test_get_series_appeears_off_case_does_not_fetch(monkeypatch):
    def boom(*a):
        raise AssertionError("must not fetch")

    monkeypatch.setattr(gather, "FETCHERS", {**gather.FETCHERS, "appeears": boom})
    got = tools.get_series(_session(tags=("vegetated",)), var_id="ndvi")
    assert got["status"] == "not_available"


def test_trend_window(power_calls):
    s = _session()
    sid = tools.get_series(s, var_id="t2m")["series_id"]
    res = tools.trend_test(s, series_id=sid, start=2013)
    assert res["n_months"] == 144
    assert res["years"] == [2013, 2024]


def test_trend_test_unknown_series():
    s = _session()
    res = tools.trend_test(s, series_id="missing")
    assert res["status"] == "not_available"
    assert s.ledger.n_tests == 0


def test_profile_place_sets_tags(monkeypatch):
    cover = LandCover(year=2023, shares={"Croplands": 0.6, "Grasslands": 0.4})
    monkeypatch.setattr(landcover, "fetch_land_cover", lambda lat, lon, year, client=None: cover)
    s = _session(tags=())
    got = tools.profile_place(s)
    assert got["dominant"] == "Croplands"
    assert got["land_cover"] == {"Croplands": 0.6, "Grasslands": 0.4}
    assert got["data_cells"] == {"grace": "~300 km", "power": "~50 km"}
    assert set(got["tags"]) == set(s.place.tags)
    assert s.place.tags == landcover.tags_for(cover.shares)


def test_profile_place_land_cover_failure_keeps_going(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("gibs down")

    monkeypatch.setattr(landcover, "fetch_land_cover", boom)
    s = _session(tags=("vegetated",))
    got = tools.profile_place(s)
    assert got["land_cover"] == {}
    assert got["tags"] == ["vegetated"]


def test_place_as_site_for_a_point_and_a_case():
    point = Place(lat=37.0, lon=-4.5, bbox=(-4.6, 36.9, -4.4, 37.1), tags=("urban",))
    site = point.as_site()
    assert site.point == (-4.5, 37.0) and site.bbox == (-4.6, 36.9, -4.4, 37.1)
    assert site.tags == ("urban",)
    from app.sites import load_sites

    case = load_sites().sites[0]
    assert Place(lat=0, lon=0, bbox=(0, 0, 1, 1), site_id=case.id).as_site() == case


def test_registry_lists_the_data_tools():
    assert {"profile_place", "list_variables", "get_series", "trend_test"} <= set(TOOLS)
    for name, spec in TOOLS.items():
        assert spec.description, name
        assert "session" not in spec.args_schema.model_fields, name
    assert set(TOOLS["get_series"].args_schema.model_fields) == {"var_id", "start", "end"}


def test_cached_trend_test_reflects_tests_logged_since(power_calls, monkeypatch):
    from app.detective.ledger import TestRecord
    from app.stats.trend import TrendResult

    # a strong test alone (p=0.01 -> q=0.01, real) that cannot survive 20 tests (q=0.2)
    strong = TrendResult(264, 22.0, False, 0.5, 0.2, 0.8, 1.0, 0.5, 0.01, 1.0)
    monkeypatch.setattr(tools, "mk_trend_test", lambda anomalies: strong)
    s = _session()
    sid = tools.get_series(s, var_id="t2m")["series_id"]
    first = tools.trend_test(s, series_id=sid)
    assert first["verdict"] == "real" and first["n_tests_so_far"] == 1
    for i in range(19):
        s.ledger.add_test(TestRecord(f"x{i}", f"v{i}", "v", "trend", 0.5, 0.1, False, None))
    again = tools.trend_test(s, series_id=sid)
    assert again["evidence_id"] == first["evidence_id"]
    assert s.ledger.n_tests == 20  # the repeated call logged nothing
    assert again["verdict"] != "real"
    assert again["q_session"] == pytest.approx(0.2)
    assert again["n_tests_so_far"] == 20


def test_transient_failure_is_not_cached(monkeypatch):
    state = {"calls": 0}

    def flaky(site, variables, catalog, start, end):
        state["calls"] += 1
        if state["calls"] == 1:
            raise RuntimeError("timeout")
        return {v.id: _synthetic(start, end) for v in variables}

    monkeypatch.setattr(gather, "FETCHERS", {**gather.FETCHERS, "power": flaky})
    s = _session()
    assert tools.get_series(s, var_id="t2m")["status"] == "not_available"
    got = tools.get_series(s, var_id="t2m")
    assert got["status"] == "ok"
    assert got["evidence_id"] == "e1"


def test_fetcher_returning_a_non_dict_is_not_available(monkeypatch):
    monkeypatch.setattr(gather, "FETCHERS", {**gather.FETCHERS, "power": lambda *a: None})
    got = tools.get_series(_session(), var_id="t2m")
    assert got["status"] == "not_available" and got["reason"]


def test_fetcher_returning_garbage_series_is_not_available(monkeypatch):
    monkeypatch.setattr(gather, "FETCHERS", {**gather.FETCHERS, "power": lambda *a: {"t2m": "bad"}})
    got = tools.get_series(_session(), var_id="t2m")
    assert got["status"] == "not_available"


def test_unknown_case_never_raises():
    s = _session(site_id="nope")
    assert tools.list_variables(s)["status"] == "not_available"
    assert tools.get_series(s, var_id="t2m")["status"] == "not_available"


def test_solved_case_gets_appeears_variables(monkeypatch):
    calls = []

    def fake_appeears(site, variables, catalog, start, end):
        calls.append(site.id)
        return {"ndvi": _synthetic(start, end)}

    monkeypatch.setattr(gather, "FETCHERS", {**gather.FETCHERS, "appeears": fake_appeears})
    s = _session(tags=("wetland", "vegetated", "agriculture"), site_id="donana")
    rows = {r["id"]: r for r in tools.list_variables(s)["variables"]}
    assert rows["ndvi"]["available"] is True
    assert rows["ndvi"]["resolution"] == "~1 km"
    got = tools.get_series(s, var_id="ndvi")
    assert got["status"] == "ok"
    assert calls == ["donana"]


def test_opt_in_driver_off_case_is_not_available(power_calls):
    s = _session()
    rows = {r["id"]: r for r in tools.list_variables(s)["variables"]}
    assert rows["degree_days"]["available"] is False
    got = tools.get_series(s, var_id="degree_days")
    assert got["status"] == "not_available"
    assert got["reason"] == tools.EXTRA_DRIVER_REASON
    assert power_calls == []


def test_resolution_comes_from_the_dataset():
    rows = {r["id"]: r for r in tools.list_variables(_session(tags=("vegetated", "snow")))["variables"]}
    assert rows["t2m"]["resolution"] == "~50 km"
    assert rows["grace_tws"]["resolution"] == "~300 km"
    assert rows["soil_moisture"]["resolution"] == "~25 km"
    assert rows["lst_gibs"]["resolution"] == "~5.6 km"  # off-case: the GIBS yearly twins
    assert rows["snow_gibs"]["resolution"] == "~5.6 km"
    in_case = {r["id"]: r for r in tools.list_variables(_session(tags=("vegetated", "snow"), site_id="donana"))["variables"]}
    assert in_case["lst_day"]["resolution"] == "~1 km"
    assert in_case["snow_cover"]["resolution"] == "~500 m"
    assert rows["et"]["resolution"] == "dataset native resolution"
