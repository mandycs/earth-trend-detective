"""Climate vs non-climate split of a trend (generalized RESTREND).

Question answered: "how much of this change does the local climate NOT explain?"

Method, per impact variable (e.g. water stored, soil moisture):
1. Deseasonalize the impact and each of its climate drivers (anomalies, deseason.py).
2. Fit ordinary least squares  impact_anom ~ const + driver_anoms  on the months
   where every series is valid. The fit has NO time term, so it can only explain
   the impact through month-to-month co-variation with climate.
3. climate part = fitted values; residual = impact_anom - fitted.
4. Sen slope per decade of the total anomaly, the climate part and the residual
   (all on the same months), and Mann-Kendall Hamed-Rao on the residual (trend.py).
5. pct_non_climate = share of the total trend carried by the residual (see below).

Assumptions and limits (say these out loud):
- The residual is a clue, not a cause. Anything not in the model (water use,
  land clearing, dams, but also a missing climate driver or a non-linear
  response) ends up in the residual.
- Linear, same-month response, except for storage variables, which also get a
  trailing mean of rainfall anomalies (ACCUMULATION_MONTHS), because stores
  integrate rain over months.
- Collinearity: if a driver trends in the same period as a non-climate trend
  (e.g. warming while groundwater is pumped), OLS can credit part of the
  non-climate trend to that driver. That biases pct_non_climate DOWN
  (conservative), never up.
- OLS coefficients are unbiased under autocorrelation; we do not use their
  standard errors. Significance comes only from Hamed-Rao on the residual.
- The residual verdict uses the raw p-value (no FDR across variables): there is
  one residual per impact variable and it is a secondary, explanatory number.
- Depends on the period analysed (study_period in sites.yaml).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm

from app.catalog import Variable
from app.stats.deseason import monthly_anomalies
from app.stats.trend import MIN_MONTHS, TrendResult, trend_test
from app.stats.verdict import Verdict, classify

logger = logging.getLogger(__name__)

ACCUMULATION_DRIVER = "precip"
ACCUMULATION_MONTHS: Mapping[str, int] = {
    "grace_tws": 12,  # total water storage integrates about a year of rain
    "soil_moisture": 3,  # top 10 cm soil remembers a season of rain at most
}
"""Storage variables get one extra regressor: the trailing N-month mean of the
rainfall anomaly (current month included), named e.g. `precip_12mo`. Fixed a
priori from physical memory, not searched, to avoid fishing for a good fit."""

MAX_REGRESSORS = 4
"""Hard cap on regressors (catalog drivers + accumulated rain) against overfitting."""

TOTAL_TREND_P = 0.10
"""pct_non_climate is only given when the total trend is at least `likely`
(raw p < 0.10, same threshold as verdict.LIKELY_P); otherwise a share of a
trend that may not exist is meaningless."""

LOW_R2 = 0.10
"""Below this, climate explains almost none of the month-to-month variation;
the split is still computed but the caveat says so."""

CAVEAT = (
    "Factors not in the model, such as water use, end up in the residual. "
    "This is a clue, not proof of a cause."
)
LOW_R2_CAVEAT = " Climate explains little of the ups and downs here, so read the split with extra care."


@dataclass(frozen=True)
class ResidualResult:
    var_id: str
    drivers_used: tuple[str, ...]
    n_months: int
    r2: float | None
    total_slope_per_decade: float | None
    climate_slope_per_decade: float | None
    residual_slope_per_decade: float | None
    residual_p_value: float | None
    residual_verdict: str
    pct_non_climate: float | None
    caveat: str

    def to_dict(self) -> dict:
        return {k: _clean(v) for k, v in asdict(self).items()} | {"drivers_used": list(self.drivers_used)}


def _clean(value: object) -> object:
    """NaN/inf -> None so results are JSON-safe."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _finite(value: float) -> float | None:
    return float(value) if value is not None and math.isfinite(value) else None


def _has_data(series: pd.Series | None) -> bool:
    return series is not None and bool(series.notna().any())


def design_matrix(var: Variable, driver_anoms: Mapping[str, pd.Series]) -> pd.DataFrame:
    """Regressor columns (anomalies) for one impact variable, before dropping NaN rows."""
    columns = {d: driver_anoms[d] for d in var.drivers}
    window = ACCUMULATION_MONTHS.get(var.id)
    if window and ACCUMULATION_DRIVER in driver_anoms:
        acc = driver_anoms[ACCUMULATION_DRIVER].rolling(window, min_periods=window).mean()
        columns[f"{ACCUMULATION_DRIVER}_{window}mo"] = acc
    if len(columns) > MAX_REGRESSORS:
        raise ValueError(f"{var.id}: {len(columns)} regressors exceeds MAX_REGRESSORS={MAX_REGRESSORS}")
    return pd.DataFrame(columns)


def pct_non_climate(total: TrendResult, residual: TrendResult) -> float | None:
    """Share of the total Sen trend carried by the residual, in percent, clipped to [0, 100].

    pct = 100 * residual_slope / total_slope

    - None if either trend could not be computed or the total trend is not at
      least `likely` (p >= TOTAL_TREND_P). This also covers a tiny total slope:
      a near-zero slope cannot be significant, so we never divide by ~0.
    - Residual pushing against the total (opposite sign) -> 0: climate alone
      explains more than the observed change.
    - Climate pushing against the total, residual larger than total -> >100,
      clipped to 100: all of the change, and more, is non-climate.
    Sen slopes are not exactly additive (total != climate + residual), so the
    climate share is not reported as 100 - pct; the slopes are reported as-is.
    """
    if total.too_short or residual.too_short:
        return None
    if not math.isfinite(total.p_value) or total.p_value >= TOTAL_TREND_P:
        return None
    if not (math.isfinite(total.sen_slope_per_decade) and math.isfinite(residual.sen_slope_per_decade)):
        return None
    if total.sen_slope_per_decade == 0:
        return None
    ratio = residual.sen_slope_per_decade / total.sen_slope_per_decade
    return float(np.clip(100.0 * ratio, 0.0, 100.0))


def _unusable(var_id: str, drivers: tuple[str, ...], n_months: int, why: str) -> ResidualResult:
    logger.info("residual %s: no split (%s, n=%d)", var_id, why, n_months)
    return ResidualResult(
        var_id=var_id,
        drivers_used=drivers,
        n_months=n_months,
        r2=None,
        total_slope_per_decade=None,
        climate_slope_per_decade=None,
        residual_slope_per_decade=None,
        residual_p_value=None,
        residual_verdict=Verdict.UNKNOWN.value,
        pct_non_climate=None,
        caveat=CAVEAT,
    )


def residual_for(var: Variable, impact: pd.Series, driver_anoms: Mapping[str, pd.Series]) -> ResidualResult:
    """Fit the climate model for one impact variable and split its trend."""
    regressors = design_matrix(var, driver_anoms)
    drivers_used = tuple(regressors.columns)
    frame = pd.concat([monthly_anomalies(impact).rename("_impact"), regressors], axis=1).dropna()
    n_months = int(len(frame))
    if n_months < MIN_MONTHS:
        return _unusable(var.id, drivers_used, n_months, "too few overlapping months")

    y = frame["_impact"]
    X = sm.add_constant(frame[list(drivers_used)], has_constant="add")
    if np.linalg.matrix_rank(X.to_numpy()) < X.shape[1] or float(y.std()) == 0.0:
        return _unusable(var.id, drivers_used, n_months, "degenerate design")
    fit = sm.OLS(y, X).fit()
    r2 = float(fit.rsquared)
    if not math.isfinite(r2):
        return _unusable(var.id, drivers_used, n_months, "R² undefined")

    climate = fit.fittedvalues
    residual = y - climate
    total_t, climate_t, residual_t = trend_test(y), trend_test(climate), trend_test(residual)
    # Raw p used as q on purpose: one residual per variable, explanatory, no FDR.
    verdict, _ = classify(residual_t.p_value, residual_t.p_value, residual_t.sen_slope_per_decade)
    pct = pct_non_climate(total_t, residual_t)
    caveat = CAVEAT + (LOW_R2_CAVEAT if r2 < LOW_R2 else "")
    logger.info(
        "residual %s: n=%d r2=%.2f total=%.3g climate=%.3g residual=%.3g p=%.3g pct=%s",
        var.id, n_months, r2, total_t.sen_slope_per_decade, climate_t.sen_slope_per_decade,
        residual_t.sen_slope_per_decade, residual_t.p_value, pct,
    )
    return ResidualResult(
        var_id=var.id,
        drivers_used=drivers_used,
        n_months=n_months,
        r2=r2,
        total_slope_per_decade=_finite(total_t.sen_slope_per_decade),
        climate_slope_per_decade=_finite(climate_t.sen_slope_per_decade),
        residual_slope_per_decade=_finite(residual_t.sen_slope_per_decade),
        residual_p_value=_finite(residual_t.p_value),
        residual_verdict=verdict.value,
        pct_non_climate=pct,
        caveat=caveat,
    )


def compute_residuals(series: Mapping[str, pd.Series], catalog: Sequence[Variable]) -> dict[str, ResidualResult]:
    """Residual split for every impact variable present whose catalog drivers are ALL present.

    Input: month-start index, catalog units, NaN for gaps. Inputs are not modified.
    A variable with any driver missing (or all-NaN) is skipped rather than fitted
    on a partial model, because an omitted driver's effect would be counted as
    non-climate and inflate pct_non_climate.
    """
    available = {k: s for k, s in series.items() if _has_data(s)}
    by_id = {v.id: v for v in catalog}
    driver_anoms = {
        k: monthly_anomalies(s) for k, s in available.items() if k in by_id and by_id[k].role == "driver"
    }
    results: dict[str, ResidualResult] = {}
    for var_id, impact in available.items():
        var = by_id.get(var_id)
        if var is None or var.role != "impact" or not var.drivers:
            continue
        missing = [d for d in var.drivers if d not in driver_anoms]
        if missing:
            logger.info("residual %s: skipped, missing drivers %s", var_id, missing)
            continue
        results[var_id] = residual_for(var, impact, driver_anoms)
    return results
