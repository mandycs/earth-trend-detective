"""Trend test on deseasonalized anomalies.

- Significance: Mann-Kendall with the Hamed & Rao (1998) correction, which
  inflates Var(S) when the series is autocorrelated (monthly climate data is),
  so we do not claim trends that are just slow wiggles.
- Size: Sen slope (median of all pairwise slopes) using real time in years,
  so gaps in the record do not distort it, reported per decade.
- Uncertainty: 95% CI of the Sen slope after Gilbert (1987) / Sen (1968),
  using the autocorrelation-corrected Var(S).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pymannkendall as mk
from scipy.stats import norm

from app.stats.deseason import anomaly_std

logger = logging.getLogger(__name__)

MIN_MONTHS = 60
"""Fewer valid months than this (5 years of data) and we refuse to give a verdict."""

MIN_YEARS_SPAN = 5.0
"""The valid months must also cover at least this many years from first to last."""

CI_LEVEL = 0.95
DAYS_PER_YEAR = 365.25


@dataclass(frozen=True)
class TrendResult:
    n_months: int
    years_span: float
    too_short: bool
    sen_slope_per_decade: float
    ci_low: float
    ci_high: float
    sigma_per_decade: float
    anomaly_std: float
    p_value: float
    var_s: float


def _years_since_start(index: pd.DatetimeIndex) -> np.ndarray:
    days = (index - index[0]).days.to_numpy(dtype=float)
    return days / DAYS_PER_YEAR


def _span_years(index: pd.DatetimeIndex) -> float:
    """Span counting both end months, e.g. Jan 2003..Dec 2024 -> 22.0 years."""
    if len(index) == 0:
        return 0.0
    first, last = index[0], index[-1]
    months = (last.year - first.year) * 12 + (last.month - first.month) + 1
    return months / 12.0


def sen_slope_ci(
    times: np.ndarray, values: np.ndarray, var_s: float, level: float = CI_LEVEL
) -> tuple[float, float, float]:
    """Sen slope and its confidence interval (Gilbert 1987, eq. 16.6-16.7).

    C = z_{1-a/2} * sqrt(Var(S)); with N sorted pairwise slopes the bounds are
    the slopes of rank M1 = (N - C)/2 and M2 + 1 = (N + C)/2 + 1 (1-based),
    linearly interpolated for non-integer ranks and clipped to the data.
    """
    i, j = np.triu_indices(len(values), k=1)
    dt = times[j] - times[i]
    slopes = np.sort((values[j] - values[i]) / dt)
    n_slopes = slopes.size
    median = float(np.median(slopes))
    if not np.isfinite(var_s) or var_s <= 0:
        return median, float("nan"), float("nan")
    c = norm.ppf(1 - (1 - level) / 2) * np.sqrt(var_s)
    m1 = (n_slopes - c) / 2.0  # 1-based rank of the lower bound
    m2 = (n_slopes + c) / 2.0 + 1.0  # 1-based rank of the upper bound
    ranks = np.arange(1, n_slopes + 1)
    low = float(np.interp(np.clip(m1, 1, n_slopes), ranks, slopes))
    high = float(np.interp(np.clip(m2, 1, n_slopes), ranks, slopes))
    return median, low, high


def _mk_pvalue(values: np.ndarray) -> tuple[float, float]:
    """Hamed-Rao corrected p and Var(S); falls back to plain MK if the correction degenerates."""
    result = mk.hamed_rao_modification_test(values)
    if np.isfinite(result.p) and np.isfinite(result.var_s) and result.var_s > 0:
        return float(result.p), float(result.var_s)
    logger.info("Hamed-Rao correction undefined (n=%d); using plain Mann-Kendall", values.size)
    plain = mk.original_test(values)
    return float(plain.p), float(plain.var_s)


def _too_short(n_months: int, span: float, std: float) -> TrendResult:
    nan = float("nan")
    return TrendResult(n_months, span, True, nan, nan, nan, nan, std, nan, nan)


def trend_test(anomalies: pd.Series) -> TrendResult:
    """Run MK (Hamed-Rao) + Sen + CI on a deseasonalized monthly series."""
    valid = anomalies.dropna().sort_index()
    n_months = int(valid.size)
    span = _span_years(valid.index)
    std = anomaly_std(valid)
    if n_months < MIN_MONTHS or span < MIN_YEARS_SPAN:
        return _too_short(n_months, span, std)

    values = valid.to_numpy(dtype=float)
    times = _years_since_start(valid.index)
    with np.errstate(invalid="ignore", divide="ignore"):
        p_value, var_s = _mk_pvalue(values)
    slope_year, low_year, high_year = sen_slope_ci(times, values, var_s)
    slope = slope_year * 10.0
    sigma = slope / std if np.isfinite(std) and std > 0 else float("nan")
    return TrendResult(
        n_months=n_months,
        years_span=span,
        too_short=False,
        sen_slope_per_decade=slope,
        ci_low=low_year * 10.0,
        ci_high=high_year * 10.0,
        sigma_per_decade=sigma,
        anomaly_std=std,
        p_value=p_value,
        var_s=var_s,
    )
