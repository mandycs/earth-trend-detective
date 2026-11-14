import dataclasses
import math

import numpy as np
import pandas as pd
import pytest

from app.catalog import load_catalog
from app.stats.deseason import monthly_anomalies
from app.stats.residual import ACCUMULATION_MONTHS, ResidualResult, compute_residuals
from tests.test_stats_helpers import ar1_noise, monthly_index, synthetic_series

MONTHS = 264  # 2003-2024


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


def _season(amplitude: float = 3.0) -> np.ndarray:
    return amplitude * np.sin(2 * np.pi * monthly_index(months=MONTHS).month.to_numpy() / 12.0)


def _impact(driver: pd.Series, gain: float, human_per_decade: float, sigma: float, seed: int) -> pd.Series:
    """Impact = gain * driver anomaly + independent linear human trend + own season + noise."""
    t_years = np.arange(MONTHS) / 12.0
    values = (
        50.0
        + gain * monthly_anomalies(driver).to_numpy()
        + human_per_decade / 10.0 * t_years
        + _season()
        + ar1_noise(MONTHS, 0.3, sigma, seed)
    )
    return pd.Series(values, index=driver.index)


def _runoff_case(driver_trend: float, human: float, seed: int = 0) -> dict[str, pd.Series]:
    # runoff's only catalog driver is precip: a clean one-regressor model.
    precip = synthetic_series(driver_trend, sigma=1.0, seed=seed + 100)
    return {"precip": precip, "runoff": _impact(precip, 2.0, human, 0.5, seed)}


def test_impact_fully_driven_by_trending_climate_is_mostly_climate(catalog):
    results = compute_residuals(_runoff_case(driver_trend=1.5, human=0.0, seed=1), catalog)
    r = results["runoff"]
    assert r.drivers_used == ("precip",)
    assert r.r2 > 0.8
    assert r.total_slope_per_decade == pytest.approx(3.0, abs=0.6)
    assert r.climate_slope_per_decade == pytest.approx(3.0, abs=0.6)
    assert abs(r.residual_slope_per_decade) < 0.4
    assert r.pct_non_climate is not None and r.pct_non_climate < 15


def test_independent_human_trend_lands_in_residual(catalog):
    results = compute_residuals(_runoff_case(driver_trend=0.0, human=-3.0, seed=2), catalog)
    r = results["runoff"]
    assert r.residual_slope_per_decade == pytest.approx(-3.0, abs=0.5)
    assert r.residual_verdict == "real"
    assert r.residual_p_value < 0.05
    assert r.pct_non_climate is not None and r.pct_non_climate > 80
    assert "clue" in r.caveat


def test_mixed_case_splits_roughly_in_proportion(catalog):
    # climate: 2 * 1.0/decade = 2; human: +2 -> total 4, half non-climate
    r = compute_residuals(_runoff_case(driver_trend=1.0, human=2.0, seed=3), catalog)["runoff"]
    assert r.pct_non_climate == pytest.approx(50, abs=15)


def test_no_total_trend_gives_no_pct(catalog):
    r = compute_residuals(_runoff_case(driver_trend=0.0, human=0.0, seed=4), catalog)["runoff"]
    assert r.pct_non_climate is None
    assert r.r2 is not None  # the fit itself is still reported


def test_opposite_signs_are_clipped_to_0_and_100(catalog):
    # climate pushes up (+3), human pushes down harder (-6): total -3, residual -6 -> 200% -> 100
    up = compute_residuals(_runoff_case(driver_trend=1.5, human=-6.0, seed=5), catalog)["runoff"]
    assert up.pct_non_climate == 100.0
    # climate pushes up (+6), human pulls down (-3): total +3, residual opposes it -> 0
    down = compute_residuals(_runoff_case(driver_trend=3.0, human=-3.0, seed=6), catalog)["runoff"]
    assert down.pct_non_climate == 0.0


def test_missing_driver_skips_variable(catalog):
    precip = synthetic_series(0.0, seed=7)
    ndvi = _impact(precip, 0.01, 0.0, 0.01, seed=7)
    # ndvi needs precip, t2m and solar; t2m/solar are absent -> skipped, no partial model
    results = compute_residuals({"precip": precip, "ndvi": ndvi}, catalog)
    assert "ndvi" not in results
    # drivers themselves never get a residual
    assert "precip" not in results


def test_all_nan_driver_counts_as_missing(catalog):
    case = _runoff_case(0.0, -3.0, seed=8)
    case = {**case, "precip": case["precip"] * np.nan}
    assert compute_residuals(case, catalog) == {}


def test_nan_gaps_are_tolerated(catalog):
    case = _runoff_case(driver_trend=0.0, human=-3.0, seed=9)
    runoff = case["runoff"].copy()
    runoff.iloc[150:162] = np.nan  # a GRACE-style year-long gap
    runoff.iloc[::17] = np.nan
    precip = case["precip"].copy()
    precip.iloc[5:8] = np.nan
    r = compute_residuals({"precip": precip, "runoff": runoff}, catalog)["runoff"]
    valid = runoff.notna() & precip.notna()
    assert r.n_months == int(valid.sum())
    assert r.residual_slope_per_decade == pytest.approx(-3.0, abs=0.6)
    assert r.pct_non_climate > 80


def test_too_few_months_gives_no_pct(catalog):
    case = _runoff_case(driver_trend=0.0, human=-3.0, seed=10)
    short = {k: v.iloc[:40] for k, v in case.items()}
    r = compute_residuals(short, catalog)["runoff"]
    assert r.n_months == 40
    assert r.pct_non_climate is None
    assert r.r2 is None
    assert r.residual_verdict == "unknown"


def test_storage_variable_gets_accumulated_rainfall_driver(catalog):
    idx = monthly_index(months=MONTHS)
    precip = synthetic_series(0.0, sigma=1.0, phi=0.0, seed=11)
    t2m = synthetic_series(0.0, sigma=0.5, seed=12)  # untrended: see collinearity note in residual.py
    window = ACCUMULATION_MONTHS["grace_tws"]
    acc = monthly_anomalies(precip).rolling(window, min_periods=window).mean()
    t_years = np.arange(MONTHS) / 12.0
    tws = pd.Series(
        10.0 * acc.to_numpy() - 4.0 / 10.0 * t_years + ar1_noise(MONTHS, 0.5, 0.3, 13), index=idx
    )
    r = compute_residuals({"precip": precip, "t2m": t2m, "grace_tws": tws}, catalog)["grace_tws"]
    assert f"precip_{window}mo" in r.drivers_used
    assert r.n_months == MONTHS - (window - 1)
    assert r.r2 > 0.3  # the unexplained human trend itself holds much of the variance
    assert r.residual_slope_per_decade == pytest.approx(-4.0, abs=0.7)
    assert r.pct_non_climate > 80


def test_inputs_not_mutated_and_result_frozen(catalog):
    case = _runoff_case(driver_trend=1.0, human=1.0, seed=14)
    case["runoff"].iloc[10] = np.nan
    originals = {k: v.copy() for k, v in case.items()}
    results = compute_residuals(case, catalog)
    for k, v in case.items():
        pd.testing.assert_series_equal(v, originals[k])
    assert set(case) == set(originals)
    r = results["runoff"]
    assert isinstance(r, ResidualResult)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.pct_non_climate = 1.0  # type: ignore[misc]


def test_to_dict_is_json_safe(catalog):
    case = _runoff_case(driver_trend=0.0, human=-3.0, seed=15)
    short = {k: v.iloc[:40] for k, v in case.items()}
    d = compute_residuals(short, catalog)["runoff"].to_dict()
    assert d["var_id"] == "runoff"
    assert d["drivers_used"] == ["precip"]
    for value in d.values():
        assert not (isinstance(value, float) and not math.isfinite(value))
    assert d["total_slope_per_decade"] is None
