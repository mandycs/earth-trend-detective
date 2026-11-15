"""How many more years of data until the current trend would be statistically clear.

Plain words: "if things keep changing at today's rate, about N more years of data are
needed before we can tell the change apart from natural ups and downs."

Method (standard trend-detection formula, Weatherhead et al. 1998, JGR 103:17149):
- Noise = anomalies minus the Sen trend line; sigma = its std, rho = its lag-1
  autocorrelation (month to month), clipped to [0, MAX_RHO].
- With monthly sampling over T years, the OLS slope standard error is about
  sigma / (T^1.5 * sqrt(k)) with k = (1 - rho) / (1 + rho) (effective sample size).
- The trend is detectable (two-sided, 95%) when |slope| / SE >= Z, so
  T_needed = (Z * sigma / (|slope| * sqrt(k)))^(2/3).
- years_needed = ceil(T_needed - current span), at least 0.

One value per year (`per_year=1`, the annual path): the slope error grows by sqrt(12 / per_year)
for the same noise, since sum((t - mean t)^2) is about per_year * T^3 / 12, and rho is the
year-to-year autocorrelation.

Assumes the current rate continues and the noise stays the same. Returns None when there
is no slope, too few data, or the answer is beyond MAX_YEARS (no trend in sight).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

Z = 1.96
MAX_RHO = 0.95
MAX_YEARS = 50
MIN_POINTS = 24
MIN_ANNUAL_POINTS = 5
DAYS_PER_YEAR = 365.25


def years_needed(anomalies: pd.Series, slope_per_decade: float | None, per_year: int = 12) -> int | None:
    """Extra years of data needed to detect `slope_per_decade` in these anomalies.

    `per_year` = 12 for monthly anomalies (the default), 1 for one value per year.
    """
    if slope_per_decade is None or not math.isfinite(slope_per_decade) or slope_per_decade == 0:
        return None
    valid = anomalies.dropna()
    if len(valid) < (MIN_POINTS if per_year == 12 else MIN_ANNUAL_POINTS):
        return None

    t_years = (valid.index - valid.index[0]).days.to_numpy() / DAYS_PER_YEAR
    slope_per_year = slope_per_decade / 10.0
    detrended = valid.to_numpy(dtype=float) - slope_per_year * t_years
    detrended = detrended - detrended.mean()
    sigma = float(np.std(detrended, ddof=1))
    if not math.isfinite(sigma) or sigma == 0:
        return 0

    noise = pd.Series(detrended, index=valid.index).asfreq("MS" if per_year == 12 else "YS")
    rho = noise.autocorr(lag=1)
    rho = 0.0 if not math.isfinite(rho) else min(max(rho, 0.0), MAX_RHO)
    k = (1 - rho) / (1 + rho)

    t_needed = (Z * sigma * math.sqrt(12 / per_year) / (abs(slope_per_year) * math.sqrt(k))) ** (2 / 3)
    span = float(t_years[-1])
    extra = max(0, math.ceil(t_needed - span))
    return extra if extra <= MAX_YEARS else None
