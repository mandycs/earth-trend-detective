"""Annual trend path: plain Mann-Kendall + Sen on one value per year (no network)."""

import math

import numpy as np
import pandas as pd
import pymannkendall as mk

from app.stats.annual import MIN_YEARS, annual_trend, annual_years_needed, to_annual
from app.stats.years import years_needed


def _yearly(start: int, end: int, slope_per_year: float = 0.0, noise: float = 0.01, seed: int = 0) -> pd.Series:
    years = np.arange(start, end + 1)
    rng = np.random.default_rng(seed)
    values = 0.5 + slope_per_year * (years - start) + rng.normal(0, noise, years.size)
    return pd.Series(values, index=pd.to_datetime([f"{y}-01-01" for y in years]))


def test_annual_trend_too_short_under_ten_years():
    series = _yearly(2015, 2023, slope_per_year=0.01)  # 9 values
    res = annual_trend(series)
    assert MIN_YEARS == 10
    assert res.too_short is True
    assert res.n_months == 0 and math.isnan(res.p_value)
    needed = annual_years_needed(series, res)
    assert isinstance(needed, int) and needed >= 1  # at least the one year missing to reach ten


def test_annual_trend_gaps_count_as_missing_years():
    series = _yearly(2003, 2014, slope_per_year=0.01)
    series.iloc[[2, 5, 8]] = np.nan  # transparent years dropped by the fetcher
    res = annual_trend(series)
    assert res.too_short is True  # 9 valid years left


def test_annual_trend_clear_rise_uses_plain_mann_kendall_and_sen_per_decade():
    series = _yearly(2003, 2024, slope_per_year=0.01, noise=0.005)
    res = annual_trend(series)
    assert res.too_short is False
    assert res.p_value < 0.01
    assert abs(res.p_value - mk.original_test(series.to_numpy()).p) < 1e-12
    assert abs(res.sen_slope_per_decade - 0.1) < 0.02
    assert res.ci_low < res.sen_slope_per_decade < res.ci_high
    assert res.years_span == 22.0
    assert annual_years_needed(series, res) == 0


def test_years_needed_on_yearly_values_is_longer_than_on_monthly_ones():
    """Twelve times fewer points at the same noise: more years are needed for the same slope."""
    series = _yearly(2003, 2014, slope_per_year=0.002, noise=0.02, seed=3)
    annual = years_needed(series, 0.02, per_year=1)
    idx = pd.date_range("2003-01-01", "2014-12-01", freq="MS")
    monthly = pd.Series(np.random.default_rng(3).normal(0, 0.02, idx.size), index=idx)
    assert annual is not None and annual > (years_needed(monthly, 0.02) or 0)


def test_to_annual_keeps_one_value_per_year_in_the_window():
    series = _yearly(2001, 2010)
    out = to_annual(series, 2003, 2012)
    assert [d.year for d in out.index] == list(range(2003, 2013))
    assert out.loc["2011-01-01":].isna().all() and out.loc["2003-01-01"] == series.loc["2003-01-01"]
