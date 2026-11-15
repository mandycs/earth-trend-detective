"""Trend test on one value per year (the annual path).

For sources that give a single value a year (GIBS seasonal means decoded from colours,
yearly heat-stress peaks). There is no seasonal cycle to remove and year-to-year values are
far less autocorrelated than months, so the test is plain Mann-Kendall (no Hamed-Rao
correction) with the Sen slope and its Gilbert CI, as on the monthly path. At least
MIN_YEARS valid values, else `too_short`.

These results are never mixed with monthly-anomaly tests in one verdict: callers mark them
`basis: "annual"`.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pymannkendall as mk

from app.stats.deseason import anomaly_std
from app.stats.trend import TrendResult, sen_slope_ci
from app.stats.years import years_needed

MIN_YEARS = 10
"""Fewer valid yearly values than this and we refuse to give a verdict."""


def to_annual(series: pd.Series, start: int, end: int) -> pd.Series:
    """One value per year on Jan 1 of each year in [start, end] (NaN where missing); a new series."""
    index = pd.DatetimeIndex(series.index)
    values = pd.Series(series.to_numpy(dtype=float), index=index.year).groupby(level=0).mean()
    years = range(start, end + 1)
    out = values.reindex(list(years))
    out.index = pd.to_datetime([f"{y}-01-01" for y in years])
    return out.rename(series.name)


def _valid(series: pd.Series) -> pd.Series:
    return series.dropna().sort_index()


def annual_trend(series: pd.Series) -> TrendResult:
    """Plain MK + Sen (per decade) on one value per year. `n_months` is 0 on this path."""
    valid = _valid(series)
    n = int(valid.size)
    years = valid.index.year.to_numpy(dtype=float)
    span = float(years[-1] - years[0] + 1) if n else 0.0
    std = anomaly_std(valid)  # same spread as the monthly path (values kept with their trend)
    nan = float("nan")
    if n < MIN_YEARS:
        return TrendResult(0, span, True, nan, nan, nan, nan, std, nan, nan)
    values = valid.to_numpy(dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        plain = mk.original_test(values)
    p_value, var_s = float(plain.p), float(plain.var_s)
    slope_year, low_year, high_year = sen_slope_ci(years - years[0], values, var_s)
    slope = slope_year * 10.0
    return TrendResult(
        n_months=0,
        years_span=span,
        too_short=False,
        sen_slope_per_decade=slope,
        ci_low=low_year * 10.0,
        ci_high=high_year * 10.0,
        sigma_per_decade=slope / std if math.isfinite(std) and std > 0 else nan,
        anomaly_std=std,
        p_value=p_value,
        var_s=var_s,
    )


def n_years(series: pd.Series) -> int:
    return int(series.notna().sum())


def annual_years_needed(series: pd.Series, result: TrendResult) -> int | None:
    """Extra years of yearly values until the trend would be clear (`stats/years.py`, per_year=1).

    Too short: at least the years missing to reach MIN_YEARS, more if the formula on the
    values we have says so (needs 5 values to estimate a slope and its noise).
    """
    valid = _valid(series)
    if not result.too_short:
        return years_needed(valid, result.sen_slope_per_decade, per_year=1)
    missing = MIN_YEARS - int(valid.size)
    slope = None
    if valid.size >= 2:
        years = valid.index.year.to_numpy(dtype=float)
        slope, _, _ = sen_slope_ci(years - years[0], valid.to_numpy(dtype=float), float("nan"))
        slope *= 10.0
    by_formula = years_needed(valid, slope, per_year=1)
    return max(missing, by_formula or 0)
