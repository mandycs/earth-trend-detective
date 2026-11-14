import numpy as np
import pandas as pd
import pytest

from app.stats.years import MAX_YEARS, years_needed

IDX = pd.date_range("2003-01-01", "2012-12-01", freq="MS")  # 10 years


def anomalies(slope_per_year: float, noise: float, phi: float = 0.0, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    e = np.zeros(len(IDX))
    for i in range(1, len(IDX)):
        e[i] = phi * e[i - 1] + rng.normal(0, noise)
    t = np.arange(len(IDX)) / 12
    return pd.Series(slope_per_year * t + e, index=IDX)


def test_clear_trend_needs_no_more_years():
    a = anomalies(1.0, 0.2)
    assert years_needed(a, slope_per_decade=10.0) == 0


def test_weak_trend_needs_more_years():
    a = anomalies(0.02, 1.0, seed=1)
    n = years_needed(a, slope_per_decade=0.2)
    assert n is not None and 5 <= n <= MAX_YEARS


def test_autocorrelation_increases_years_needed():
    white = years_needed(anomalies(0.05, 1.0, phi=0.0, seed=2), slope_per_decade=0.5)
    red = years_needed(anomalies(0.05, 1.0, phi=0.8, seed=2), slope_per_decade=0.5)
    assert red is not None and white is not None and red > white


def test_zero_or_missing_slope_returns_none():
    a = anomalies(0.0, 1.0)
    assert years_needed(a, slope_per_decade=0.0) is None
    assert years_needed(a, slope_per_decade=None) is None


def test_beyond_horizon_returns_none():
    a = anomalies(0.0, 1.0, seed=3)
    assert years_needed(a, slope_per_decade=1e-6) is None


def test_input_not_mutated():
    a = anomalies(0.05, 1.0, seed=4)
    before = a.copy()
    years_needed(a, slope_per_decade=0.5)
    pd.testing.assert_series_equal(a, before)


@pytest.mark.parametrize("n_valid", [0, 5])
def test_too_few_points_returns_none(n_valid):
    a = anomalies(0.05, 1.0).copy()
    a.iloc[n_valid:] = np.nan
    assert years_needed(a, slope_per_decade=0.5) is None
