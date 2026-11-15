import numpy as np
import pandas as pd
import pytest

from app import gather
from app.catalog import load_catalog
from app.detective.ledger import Ledger
from app.detective.place import Place
from app.detective.session import Session
from app.detective.tools import TOOLS
from app.detective.tools import analysis
from app.detective.tools import data as tools

WORDING = "not explained by the climate we measured — a clue, not proof"


def _synthetic(start: int, end: int, slope_per_year: float, seed: int = 0) -> pd.Series:
    idx = pd.date_range(f"{start}-01-01", f"{end}-12-01", freq="MS")
    t = np.arange(idx.size) / 12.0
    rng = np.random.default_rng(seed)
    seasonal = 5 * np.sin(2 * np.pi * idx.month / 12)
    return pd.Series(10 + seasonal + slope_per_year * t + rng.normal(0, 0.2, idx.size), index=idx)


def _session(tags=("vegetated",), lat=37.0, lon=-4.5) -> Session:
    place = Place(lat=lat, lon=lon, bbox=(lon - 0.1, lat - 0.1, lon + 0.1, lat + 0.1), tags=tuple(tags))
    return Session(ledger=Ledger(), place=place, catalog=load_catalog(), series={})


@pytest.fixture
def fetch_calls(monkeypatch):
    """power: flat drivers; grace: a trend the drivers cannot explain."""
    calls = []

    def fake_power(site, variables, catalog, start, end):
        calls.append(("power", tuple(v.id for v in variables), site.point))
        return {v.id: _synthetic(start, end, 0.0, seed=len(v.id)).rename(v.id) for v in variables}

    def fake_grace(site, variables, catalog, start, end):
        calls.append(("grace", tuple(v.id for v in variables), site.point))
        return {v.id: _synthetic(start, end, -0.5, seed=7).rename(v.id) for v in variables}

    monkeypatch.setattr(gather, "FETCHERS", {**gather.FETCHERS, "power": fake_power, "grace": fake_grace})
    return calls


# --------------------------------------------------------------------------- climate_residual


def test_residual_is_cached_per_target(fetch_calls):
    s = _session()
    first = analysis.climate_residual(s, var_id="grace_tws")
    assert first["wording"] == WORDING
    assert "withheld" not in first
    assert first["pct_not_explained"] is not None and first["pct_not_explained"] > 50
    assert {"precip", "t2m"} <= set(first["drivers"])
    assert first["test_ids"] == [first["test_id"]]
    n_fetches = len(fetch_calls)
    again = analysis.climate_residual(s, var_id="grace_tws")
    assert again["evidence_id"] == first["evidence_id"]
    assert len(fetch_calls) == n_fetches
    residuals = [t for t in s.ledger._tests.values() if t.kind == "residual"]
    assert len(residuals) == 1
    assert s.ledger.n_tests == 1


def test_residual_verdict_comes_from_the_ledger(fetch_calls):
    s = _session()
    got = analysis.climate_residual(s, var_id="grace_tws")
    q, verdict, direction = s.ledger.corrected()[got["test_id"]]
    assert got["q_session"] == pytest.approx(q, abs=1e-4)
    assert got["verdict"] == str(verdict)
    assert got["direction"] == str(direction) == "down"


def test_residual_withheld_on_glacier(fetch_calls):
    s = _session(tags=("glacier",))
    got = analysis.climate_residual(s, var_id="grace_tws")
    assert "withheld" in got and got["withheld"]
    assert "pct_not_explained" not in got
    assert got["wording"] == WORDING
    assert s.ledger.n_tests == 0


def test_residual_not_for_a_driver(fetch_calls):
    s = _session()
    got = analysis.climate_residual(s, var_id="t2m")
    assert got["status"] == "not_available"
    assert s.ledger.n_tests == 0


def test_residual_missing_driver_is_not_available(monkeypatch):
    def fake_power(site, variables, catalog, start, end):
        return {}

    def fake_grace(site, variables, catalog, start, end):
        return {v.id: _synthetic(start, end, -0.5).rename(v.id) for v in variables}

    monkeypatch.setattr(gather, "FETCHERS", {**gather.FETCHERS, "power": fake_power, "grace": fake_grace})
    s = _session()
    got = analysis.climate_residual(s, var_id="grace_tws")
    assert got["status"] == "not_available"
    assert "precip" in got["reason"] or "t2m" in got["reason"]
    assert s.ledger.n_tests == 0


# --------------------------------------------------------------------------- correlate


def test_correlate_logs_one_test_per_lag(fetch_calls):
    s = _session()
    a = tools.get_series(s, var_id="grace_tws")["series_id"]
    b = tools.get_series(s, var_id="precip")["series_id"]
    got = analysis.correlate(s, series_a=a, series_b=b, max_lag=2)
    assert [row["lag"] for row in got["lags"]] == [0, 1, 2]
    assert s.ledger.n_tests == 3
    assert all(t.kind == "correlate" for t in s.ledger._tests.values())
    assert got["test_ids"] == [row["test_id"] for row in got["lags"]]
    corrected = s.ledger.corrected()
    for row in got["lags"]:
        assert -1 <= row["r"] <= 1
        assert row["q_session"] == pytest.approx(corrected[row["test_id"]][0], abs=1e-4)
    again = analysis.correlate(s, series_a=a, series_b=b, max_lag=2)
    assert again["evidence_id"] == got["evidence_id"]
    assert s.ledger.n_tests == 3


def test_correlate_finds_a_lagged_link():
    s = _session()
    years = pd.date_range("2003-01-01", "2024-12-01", freq="MS")
    rng = np.random.default_rng(3)
    yearly = pd.Series(rng.normal(0, 1, 22), index=range(2003, 2025))
    driver = pd.Series(yearly.reindex(years.year).to_numpy(), index=years).rename("precip")
    follower = pd.Series(yearly.shift(1).reindex(years.year).to_numpy(), index=years).rename("grace_tws")
    s.series["precip:2003-2024"] = driver
    s.series["grace_tws:2003-2024"] = follower
    got = analysis.correlate(s, series_a="grace_tws:2003-2024", series_b="precip:2003-2024", max_lag=1)
    lag0, lag1 = got["lags"]
    assert lag1["r"] > 0.95
    assert abs(lag1["r"]) > abs(lag0["r"])


def test_correlate_unknown_series():
    s = _session()
    got = analysis.correlate(s, series_a="nope:2003-2024", series_b="nada:2003-2024")
    assert got["status"] == "not_available"
    assert s.ledger.n_tests == 0


# --------------------------------------------------------------------------- compare


@pytest.fixture
def two_places(monkeypatch):
    """t2m rises +1 per decade at lon -4.5 and falls -1 per decade anywhere else."""
    calls = []

    def fake_power(site, variables, catalog, start, end):
        calls.append(site.point)
        slope = 0.1 if site.point[0] == -4.5 else -0.1
        return {v.id: _synthetic(start, end, slope).rename(v.id) for v in variables}

    monkeypatch.setattr(gather, "FETCHERS", {**gather.FETCHERS, "power": fake_power})
    return calls


def test_compare_two_places_returns_difference(two_places):
    s = _session()
    got = analysis.compare(s, var_id="t2m", a={"lat": 37.0, "lon": -4.5}, b={"lat": 40.0, "lon": 2.0})
    assert got["a"]["slope_per_decade"] == pytest.approx(1.0, abs=0.1)
    assert got["b"]["slope_per_decade"] == pytest.approx(-1.0, abs=0.1)
    assert got["difference_per_decade"] == pytest.approx(2.0, abs=0.15)
    assert got["difference_per_decade"] == pytest.approx(
        got["a"]["slope_per_decade"] - got["b"]["slope_per_decade"], abs=1e-3
    )
    assert {got["a"]["direction"], got["b"]["direction"]} == {"up", "down"}
    assert got["a"]["direction"] == "up"
    assert s.ledger.n_tests == 2
    assert all(t.kind == "compare" for t in s.ledger._tests.values())
    assert got["test_ids"] == [got["a"]["test_id"], got["b"]["test_id"]]
    assert (2.0, 40.0) in two_places  # side b fetched at its own point
    assert s.place.lat == 37.0  # the investigated place is unchanged


def test_compare_is_cached(two_places):
    s = _session()
    args = {"var_id": "t2m", "a": {"lat": 37.0, "lon": -4.5}, "b": {"lat": 40.0, "lon": 2.0}}
    first = analysis.compare(s, **args)
    again = analysis.compare(s, **args)
    assert again["evidence_id"] == first["evidence_id"]
    assert s.ledger.n_tests == 2


def test_compare_two_periods(two_places):
    s = _session()
    got = analysis.compare(s, var_id="t2m", a={"start": 2003, "end": 2013}, b={"start": 2014, "end": 2024})
    assert got["a"]["years"] == [2003, 2013]
    assert got["b"]["years"] == [2014, 2024]
    assert got["a"]["direction"] == got["b"]["direction"] == "up"
    assert s.ledger.n_tests == 2


def test_compare_needs_a_place_or_a_period(two_places):
    s = _session()
    got = analysis.compare(s, var_id="t2m", a={}, b={"lat": 40.0, "lon": 2.0})
    assert got["status"] == "not_available"
    assert s.ledger.n_tests == 0


# --------------------------------------------------------------------------- years_needed_for


def test_years_needed_logs_no_test(fetch_calls):
    s = _session()
    sid = tools.get_series(s, var_id="t2m")["series_id"]
    got = analysis.years_needed_for(s, series_id=sid)
    assert "years_needed" in got
    assert s.ledger.n_tests == 0


def test_registry_lists_the_analysis_tools():
    for name in ("climate_residual", "correlate", "compare", "years_needed_for"):
        assert name in TOOLS
        assert TOOLS[name].description


# --------------------------------------------------------------------------- passing failures


def _flaky_power(monkeypatch, slope_for=lambda site: 0.0):
    """power raises once, then answers; grace always answers."""
    state = {"calls": 0}

    def power(site, variables, catalog, start, end):
        state["calls"] += 1
        if state["calls"] == 1:
            raise ConnectionError("timeout")
        return {v.id: _synthetic(start, end, slope_for(site), seed=len(v.id)).rename(v.id) for v in variables}

    def grace(site, variables, catalog, start, end):
        return {v.id: _synthetic(start, end, -0.5, seed=7).rename(v.id) for v in variables}

    monkeypatch.setattr(gather, "FETCHERS", {**gather.FETCHERS, "power": power, "grace": grace})
    return state


def test_residual_retries_after_a_passing_source_failure(monkeypatch):
    _flaky_power(monkeypatch)
    s = _session()
    first = analysis.climate_residual(s, var_id="grace_tws")
    assert first["status"] == "not_available"
    assert "evidence_id" not in first
    assert s.ledger.n_tests == 0
    again = analysis.climate_residual(s, var_id="grace_tws")
    assert again.get("status") != "not_available"
    assert again["pct_not_explained"] is not None
    assert s.ledger.n_tests == 1


def test_compare_retries_after_a_passing_source_failure(monkeypatch):
    _flaky_power(monkeypatch, slope_for=lambda site: 0.1)
    s = _session()
    args = {"var_id": "t2m", "a": {"lat": 37.0, "lon": -4.5}, "b": {"lat": 40.0, "lon": 2.0}}
    first = analysis.compare(s, **args)
    assert first["status"] == "not_available"
    assert "evidence_id" not in first
    assert s.ledger.n_tests == 0
    again = analysis.compare(s, **args)
    assert again["difference_per_decade"] is not None
    assert s.ledger.n_tests == 2


def test_residual_model_failure_does_not_raise(fetch_calls, monkeypatch):
    def boom(*a, **k):
        raise ValueError("singular")

    monkeypatch.setattr(analysis, "residual_for", boom)
    s = _session()
    got = analysis.climate_residual(s, var_id="grace_tws")
    assert got["status"] == "not_available"
    assert got["wording"] == WORDING
    assert s.ledger.n_tests == 0


def _monthly(values_by_year: dict[int, float], start=2003, end=2024) -> pd.Series:
    idx = pd.date_range(f"{start}-01-01", f"{end}-12-01", freq="MS")
    return pd.Series([values_by_year.get(t.year, np.nan) for t in idx], index=idx, dtype=float)


def test_correlate_counts_pairs_after_dropping_gaps():
    s = _session()
    rng = np.random.default_rng(5)
    vals = dict(zip(range(2003, 2025), rng.normal(0, 1, 22)))
    a = _monthly(vals).rename("grace_tws")
    gappy = {y: v for y, v in vals.items() if y not in (2010, 2015)}  # 2 missing years
    b = _monthly(gappy).rename("precip")
    s.series["grace_tws:2003-2024"], s.series["precip:2003-2024"] = a, b
    got = analysis.correlate(s, series_a="grace_tws:2003-2024", series_b="precip:2003-2024", max_lag=0)
    # 21 year-on-year changes in a; b loses the changes into and out of each gap year (4)
    assert got["lags"][0]["n_years"] == 17
    assert got["lags"][0]["r"] == pytest.approx(1.0, abs=1e-6)


def test_correlate_too_few_pairs_is_too_short():
    s = _session()
    rng = np.random.default_rng(6)
    vals = dict(zip(range(2003, 2012), rng.normal(0, 1, 9)))  # 9 years -> 8 changes < 10 pairs
    s.series["grace_tws:2003-2011"] = _monthly(vals, 2003, 2011).rename("grace_tws")
    s.series["precip:2003-2011"] = _monthly(vals, 2003, 2011).rename("precip")
    got = analysis.correlate(s, series_a="grace_tws:2003-2011", series_b="precip:2003-2011", max_lag=0)
    row = got["lags"][0]
    assert row["too_short"] is True
    assert row["p"] is None and row["r"] is None
    record = s.ledger._tests[row["test_id"]]
    assert np.isnan(record.p_value) and record.too_short
    assert row["verdict"] == "unknown"
