"""Per-site driver model selection: candidates, time-blocked CV, snow-term derivations."""

import json

import numpy as np
import pandas as pd
import pytest

from app.catalog import load_catalog
from app.stats.deseason import monthly_anomalies
from app.stats.residual import (
    MIN_CV_GAIN,
    blocked_cv_r2,
    compute_residuals,
    degree_days,
    winter_precip,
)
from tests.test_stats_helpers import ar1_noise, monthly_index, synthetic_series

MONTHS = 264  # 2003-2024


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


def _t_years() -> np.ndarray:
    return np.arange(MONTHS) / 12.0


def _acc(series: pd.Series, window: int = 12) -> pd.Series:
    return monthly_anomalies(series).rolling(window, min_periods=window).mean()


def _local_drivers(seed: int) -> dict[str, pd.Series]:
    return {
        "precip": synthetic_series(0.0, sigma=1.0, phi=0.0, seed=seed),
        "t2m": synthetic_series(0.0, sigma=0.5, seed=seed + 1),
    }


# --------------------------------------------------------------------------- backward compatibility


def test_without_extra_drivers_only_m0_is_a_candidate(catalog):
    precip = synthetic_series(0.0, sigma=1.0, seed=1)
    runoff = pd.Series(
        2.0 * monthly_anomalies(precip).to_numpy() + ar1_noise(MONTHS, 0.3, 0.5, 2),
        index=precip.index,
    )
    r = compute_residuals({"precip": precip, "runoff": runoff}, catalog)["runoff"]
    assert r.model_id == "M0"
    assert r.model_label
    assert [c.id for c in r.candidates] == ["M0"]
    assert r.cv_r2 is not None and r.cv_r2 > 0.5
    assert r.candidates[0].cv_r2 == pytest.approx(r.cv_r2)


def test_to_dict_lists_candidates_json_safe(catalog):
    precip = synthetic_series(0.0, sigma=1.0, seed=3)
    runoff = 2.0 * precip
    d = compute_residuals({"precip": precip, "runoff": runoff}, catalog)["runoff"].to_dict()
    assert d["model_id"] == "M0"
    assert isinstance(d["candidates"], list)
    assert set(d["candidates"][0]) == {"id", "label", "cv_r2", "drivers", "n_months", "pct_non_climate"}
    assert d["pct_range"] is None  # one candidate only: no range
    json.dumps(d, allow_nan=False)


# --------------------------------------------------------------------------- upstream climate (M1)


def _mead_case(seed: int, upstream_gain: float, upstream_trend: float = 0.0, human: float = -4.0):
    drivers = _local_drivers(seed)
    up_p = synthetic_series(upstream_trend, sigma=1.0, phi=0.0, seed=seed + 10)
    up_t = synthetic_series(0.0, sigma=0.5, seed=seed + 11)
    tws = pd.Series(
        upstream_gain * _acc(up_p).to_numpy()
        + human / 10.0 * _t_years()
        + ar1_noise(MONTHS, 0.5, 0.3, seed + 12),
        index=up_p.index,
    )
    return {**drivers, "precip_upstream": up_p, "t2m_upstream": up_t, "grace_tws": tws}


def test_upstream_model_chosen_when_storage_follows_upstream_rain(catalog):
    r = compute_residuals(_mead_case(seed=20, upstream_gain=10.0), catalog)["grace_tws"]
    scores = {c.id: c.cv_r2 for c in r.candidates}
    assert set(scores) == {"M0", "M1"}
    assert scores["M1"] > scores["M0"] + 0.3
    assert r.model_id == "M1"
    assert "precip_upstream_12mo" in r.drivers_used and "t2m_upstream" in r.drivers_used
    assert r.cv_r2 == pytest.approx(scores["M1"])
    # the human trend is untouched by the upstream rain, so it stays in the residual
    assert r.residual_slope_per_decade == pytest.approx(-4.0, abs=0.7)


def test_irrelevant_upstream_drivers_keep_m0(catalog):
    r = compute_residuals(_mead_case(seed=30, upstream_gain=0.0), catalog)["grace_tws"]
    assert r.model_id == "M0"
    assert {c.id for c in r.candidates} == {"M0", "M1"}


def test_false_selection_rate_of_irrelevant_upstream_is_low(catalog):
    picks = [
        compute_residuals(_mead_case(seed=s, upstream_gain=0.0), catalog)["grace_tws"].model_id
        for s in range(100, 200)
    ]
    # null case: upstream rain is pure noise; MIN_CV_GAIN keeps spurious picks near 5%
    assert picks.count("M1") <= 8


def test_selection_does_not_reward_a_driver_that_only_shares_the_trend(catalog):
    # upstream rain trends down like the human signal but its wiggles do not drive storage:
    # a CV that rewarded trend-matching would pick M1 and shrink the non-climate share.
    r = compute_residuals(
        _mead_case(seed=40, upstream_gain=0.0, upstream_trend=-1.5), catalog
    )["grace_tws"]
    assert r.model_id == "M0"
    assert r.pct_non_climate is not None and r.pct_non_climate > 80


def test_upstream_needs_both_upstream_drivers(catalog):
    case = _mead_case(seed=50, upstream_gain=10.0)
    del case["t2m_upstream"]
    r = compute_residuals(case, catalog)["grace_tws"]
    assert [c.id for c in r.candidates] == ["M0"]


def test_upstream_is_not_offered_to_non_storage_variables(catalog):
    case = _mead_case(seed=60, upstream_gain=10.0)
    runoff = 2.0 * monthly_anomalies(case["precip"]) + ar1_noise(MONTHS, 0.3, 0.5, 61)
    r = compute_residuals({**case, "runoff": runoff}, catalog)["runoff"]
    assert [c.id for c in r.candidates] == ["M0"]


# --------------------------------------------------------------------------- snow terms (M2)


def test_degree_days_is_positive_temperature_times_days():
    idx = pd.date_range("2003-01-01", periods=3, freq="MS")
    t2m = pd.Series([-5.0, 2.0, np.nan], index=idx)
    out = degree_days(t2m)
    assert out.tolist()[:2] == [0.0, 2.0 * 28]
    assert np.isnan(out.iloc[2])
    assert t2m.iloc[0] == -5.0  # input untouched


def test_winter_precip_accumulates_oct_to_apr_and_holds_until_september():
    idx = pd.date_range("2003-01-01", "2005-09-01", freq="MS")
    precip = pd.Series(1.0, index=idx)  # 1 mm/day
    out = winter_precip(precip)
    # first water year (Oct 2002 - Sep 2003) is incomplete -> NaN
    assert out.loc["2003-01-01":"2003-09-01"].isna().all()
    assert out.loc["2003-10-01"] == 31
    assert out.loc["2003-11-01"] == 31 + 30
    oct_to_apr = 31 + 30 + 31 + 31 + 29 + 31 + 30  # 2004 is a leap year
    assert out.loc["2004-04-01"] == oct_to_apr
    assert out.loc["2004-09-01"] == oct_to_apr  # held through the melt season
    assert out.loc["2004-10-01"] == 31  # reset each October


def test_winter_precip_gap_blanks_rest_of_water_year():
    idx = pd.date_range("2003-10-01", "2004-12-01", freq="MS")
    precip = pd.Series(1.0, index=idx)
    precip.loc["2003-12-01"] = np.nan
    out = winter_precip(precip)
    assert out.loc["2003-11-01"] == 61
    assert out.loc["2003-12-01":"2004-09-01"].isna().all()
    assert out.loc["2004-10-01"] == 31


def _snow_case(seed: int, snow_gain: float, human: float = -3.0):
    idx = monthly_index(months=MONTHS)
    drivers = _local_drivers(seed)
    dd = synthetic_series(0.0, sigma=20.0, seed=seed + 20)
    wp = synthetic_series(0.0, sigma=50.0, phi=0.8, seed=seed + 21)
    tws = pd.Series(
        snow_gain * (monthly_anomalies(wp).to_numpy() / 50.0 - monthly_anomalies(dd).to_numpy() / 20.0)
        + human / 10.0 * _t_years()
        + ar1_noise(MONTHS, 0.5, 0.3, seed + 22),
        index=idx,
    )
    return {**drivers, "degree_days": dd, "winter_precip": wp, "grace_tws": tws}


def test_snow_model_chosen_when_storage_follows_snow_terms(catalog):
    r = compute_residuals(_snow_case(seed=70, snow_gain=3.0), catalog)["grace_tws"]
    scores = {c.id: c.cv_r2 for c in r.candidates}
    assert set(scores) == {"M0", "M2"}
    assert r.model_id == "M2"
    assert scores["M2"] > scores["M0"] + MIN_CV_GAIN
    assert {"degree_days", "winter_precip"} <= set(r.drivers_used)
    assert len(r.drivers_used) <= 5


def test_irrelevant_snow_terms_keep_m0(catalog):
    r = compute_residuals(_snow_case(seed=80, snow_gain=0.0), catalog)["grace_tws"]
    assert r.model_id == "M0"


# --------------------------------------------------------------------------- CV helper


def test_blocked_cv_r2_scores_signal_high_and_noise_low():
    idx = monthly_index(months=MONTHS)
    rng = np.random.default_rng(0)
    x = pd.DataFrame({"x": rng.normal(size=MONTHS)}, index=idx)
    y_signal = pd.Series(3.0 * x["x"].to_numpy() + rng.normal(0, 0.5, MONTHS), index=idx)
    y_noise = pd.Series(rng.normal(size=MONTHS), index=idx)
    assert blocked_cv_r2(y_signal, x) > 0.9
    assert blocked_cv_r2(y_noise, x) < 0.05


def test_blocked_cv_r2_ignores_shared_linear_trend():
    idx = monthly_index(months=MONTHS)
    rng = np.random.default_rng(1)
    trend = np.linspace(0, 10, MONTHS)
    x = pd.DataFrame({"x": trend + rng.normal(size=MONTHS)}, index=idx)
    y = pd.Series(trend + rng.normal(size=MONTHS), index=idx)  # same trend, independent wiggles
    assert blocked_cv_r2(y, x) < 0.05


def test_blocked_cv_r2_too_short_is_none():
    idx = monthly_index(months=30)
    x = pd.DataFrame({"x": np.arange(30.0)}, index=idx)
    assert blocked_cv_r2(pd.Series(np.arange(30.0), index=idx), x) is None


def test_every_candidate_gets_its_own_share_and_the_range_spans_them(catalog):
    # Upstream drought explains part of the decline: the local-only model (M0) leaves it in
    # the residual, the upstream model (M1) does not, so the two shares differ.
    r = compute_residuals(_mead_case(seed=40, upstream_gain=10.0, upstream_trend=-1.5), catalog)["grace_tws"]
    shares = {c.id: c.pct_non_climate for c in r.candidates}
    assert set(shares) == {"M0", "M1"}
    assert all(v is not None for v in shares.values())
    chosen = next(c for c in r.candidates if c.id == r.model_id)
    assert chosen.pct_non_climate == pytest.approx(r.pct_non_climate)
    lo, hi = r.pct_range
    assert lo == min(shares.values()) and hi == max(shares.values())
    assert r.to_dict()["pct_range"] == [lo, hi]
