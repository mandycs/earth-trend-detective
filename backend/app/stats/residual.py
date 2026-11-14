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

Driver model selection (per impact variable, per site):
- A few CANDIDATE models are declared up front in CANDIDATE_MODELS, each motivated by
  physics: M0 = local catalog drivers (the original model); M1 = M0 + climate in the
  upstream basin (for storage fed by a remote river, e.g. Lake Mead <- Rocky Mountains);
  M2 = M0 + snow terms (degree-days and winter precipitation, for snow/ice sites).
  A candidate is offered only if its extra drivers are present (sites.yaml decides
  which sites fetch them) and the impact is one it applies to. Max MAX_REGRESSORS.
- The choice is made by time-blocked cross-validation (CV_FOLDS contiguous folds,
  CV_BUFFER_MONTHS dropped from training on each side of the test block) on
  out-of-sample R², all candidates scored on the same months. Before CV, the impact and
  every regressor are linearly detrended: a model must earn its place by predicting the
  month-to-month and year-to-year wiggles, not by sharing the long-term trend. Otherwise
  CV would reward any driver that happens to trend like the human signal and shrink the
  non-climate share for the wrong reason.
- The choice never looks at pct_non_climate. A richer model wins only if it beats M0 by
  at least MIN_CV_GAIN (parsimony); otherwise M0 is kept.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace

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

MAX_REGRESSORS = 5
"""Hard cap on regressors (catalog drivers + accumulated rain + candidate extras) against
overfitting. A candidate model above the cap is not offered."""

UPSTREAM_DRIVERS = ("t2m_upstream", "precip_upstream")
UPSTREAM_ACCUMULATION_MONTHS = 12
"""Upstream rain/snow reaches a reservoir through snowpack, rivers and upstream dams, so
M1 uses its trailing 12-month mean (one water year), not the same-month value. Upstream
temperature enters same-month (melt timing, evaporation)."""
UPSTREAM_IMPACTS = frozenset({"grace_tws", "water_area"})
"""Storage that a remote basin feeds. Local land variables (soil, plants) are not."""

SNOW_DRIVERS = ("degree_days", "winter_precip")
SNOW_IMPACTS = frozenset({"grace_tws", "runoff", "soil_moisture", "snow_cover"})
"""Water variables where snow storage and melt act. Plant greenness and ground
temperature are left out on purpose (no fishing)."""

CV_FOLDS = 5
CV_BUFFER_MONTHS = 12
"""Months dropped from training on each side of a test block, so 12-month accumulated
regressors and autocorrelated noise do not leak the test block into training."""
MIN_CV_GAIN = 0.05
"""A richer model must beat M0's CV R² by at least this much to be chosen."""

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
class ModelSpec:
    """One declared candidate driver model: M0's regressors plus `extra_drivers`."""

    id: str
    label: str
    extra_drivers: tuple[str, ...]
    impacts: frozenset[str] | None  # None = every impact variable


CANDIDATE_MODELS: tuple[ModelSpec, ...] = (
    ModelSpec("M0", "Local climate at the site", (), None),
    ModelSpec("M1", "Local climate + climate in the upstream basin", UPSTREAM_DRIVERS, UPSTREAM_IMPACTS),
    ModelSpec("M2", "Local climate + snow terms (melt warmth, winter precipitation)", SNOW_DRIVERS, SNOW_IMPACTS),
)
M0 = CANDIDATE_MODELS[0]


@dataclass(frozen=True)
class CandidateScore:
    id: str
    label: str
    drivers: tuple[str, ...]
    n_months: int  # months shared by all candidates, on which every CV score is computed
    cv_r2: float | None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "drivers": list(self.drivers),
            "n_months": self.n_months,
            "cv_r2": _clean(self.cv_r2),
        }


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
    model_id: str = M0.id
    model_label: str = M0.label
    cv_r2: float | None = None
    candidates: tuple[CandidateScore, ...] = ()

    def to_dict(self) -> dict:
        return {k: _clean(v) for k, v in asdict(self).items()} | {
            "drivers_used": list(self.drivers_used),
            "candidates": [c.to_dict() for c in self.candidates],
        }


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


def degree_days(t2m: pd.Series) -> pd.Series:
    """Positive degree-days per month from monthly mean temperature: max(T, 0) x days.

    A crude melt-energy proxy (a monthly mean below 0 °C can hide warm days). NaN stays NaN.
    Returns a new series.
    """
    days = pd.DatetimeIndex(t2m.index).days_in_month
    return (t2m.astype(float).clip(lower=0.0) * days).rename(t2m.name)


WINTER_MONTHS = frozenset({10, 11, 12, 1, 2, 3, 4})


def winter_precip(precip: pd.Series) -> pd.Series:
    """Water-year (Oct-Sep) running total of Oct-Apr precipitation, in mm; held May-Sep.

    A snow-supply proxy: how much fell this winter so far. Input in mm/day. A water year
    whose October is not in the series, or that has a gap, is NaN from the gap onwards.
    Resets each October. Returns a new series.
    """
    idx = pd.DatetimeIndex(precip.index)
    mm = precip.astype(float).to_numpy() * idx.days_in_month.to_numpy()
    water_year = idx.year + (idx.month >= 10).astype(int)
    out = np.full(len(idx), np.nan)
    order = np.argsort(idx.asi8, kind="stable")
    running, valid, current = 0.0, False, None
    for i in order:
        ts = idx[i]
        if water_year[i] != current:
            current = water_year[i]
            running, valid = 0.0, ts.month == 10
        if not valid:
            continue
        if ts.month in WINTER_MONTHS:
            if not math.isfinite(mm[i]):
                valid = False
                continue
            running += mm[i]
        out[i] = running
    return pd.Series(out, index=precip.index, name=precip.name)


def _months(index: pd.Index) -> np.ndarray:
    di = pd.DatetimeIndex(index)
    return (di.year * 12 + di.month).to_numpy(dtype=float)


def _detrend(values: np.ndarray, t: np.ndarray) -> np.ndarray:
    slope, intercept = np.polyfit(t, values, 1)
    return values - (slope * t + intercept)


def blocked_cv_r2(
    y: pd.Series, X: pd.DataFrame, n_folds: int = CV_FOLDS, buffer_months: int = CV_BUFFER_MONTHS
) -> float | None:
    """Out-of-sample R² of OLS y ~ const + X from time-blocked cross-validation.

    y and every column of X are linearly detrended first (see module docstring). The rows
    are split into `n_folds` contiguous blocks; each block is predicted from a fit on the
    other rows minus `buffer_months` on each side. R² = 1 - SSE / SST, pooled over all
    blocks, where SST uses the training mean (so 0 = no better than a constant, and it
    can be negative). None if too short or a fold cannot be fitted.
    """
    frame = pd.concat([y.rename("_y"), X], axis=1).dropna()
    n, p = len(frame), X.shape[1]
    if n < MIN_MONTHS:
        return None
    t = _months(frame.index)
    yd = _detrend(frame["_y"].to_numpy(dtype=float), t)
    xd = np.column_stack([_detrend(frame[c].to_numpy(dtype=float), t) for c in X.columns])
    sse = sst = 0.0
    for block in np.array_split(np.arange(n), n_folds):
        t0, t1 = t[block[0]], t[block[-1]]
        train = (t < t0 - buffer_months) | (t > t1 + buffer_months)
        if int(train.sum()) < p + 10:
            return None
        a_train = np.column_stack([np.ones(int(train.sum())), xd[train]])
        beta, *_ = np.linalg.lstsq(a_train, yd[train], rcond=None)
        pred = np.column_stack([np.ones(len(block)), xd[block]]) @ beta
        sse += float(np.sum((yd[block] - pred) ** 2))
        sst += float(np.sum((yd[block] - yd[train].mean()) ** 2))
    if sst <= 0.0:
        return None
    r2 = 1.0 - sse / sst
    return r2 if math.isfinite(r2) else None


def _extra_columns(spec: ModelSpec, driver_anoms: Mapping[str, pd.Series]) -> dict[str, pd.Series]:
    if spec.id == "M1":
        acc = driver_anoms["precip_upstream"].rolling(
            UPSTREAM_ACCUMULATION_MONTHS, min_periods=UPSTREAM_ACCUMULATION_MONTHS
        ).mean()
        return {"t2m_upstream": driver_anoms["t2m_upstream"], f"precip_upstream_{UPSTREAM_ACCUMULATION_MONTHS}mo": acc}
    return {d: driver_anoms[d] for d in spec.extra_drivers}


def candidate_designs(
    var: Variable, driver_anoms: Mapping[str, pd.Series]
) -> list[tuple[ModelSpec, pd.DataFrame]]:
    """Regressor frames for every candidate model offered to `var` (M0 first)."""
    base = design_matrix(var, driver_anoms)
    designs = [(M0, base)]
    for spec in CANDIDATE_MODELS[1:]:
        if spec.impacts is not None and var.id not in spec.impacts:
            continue
        if not all(_has_data(driver_anoms.get(d)) for d in spec.extra_drivers):
            continue
        frame = pd.concat([base, pd.DataFrame(_extra_columns(spec, driver_anoms))], axis=1)
        if frame.shape[1] > MAX_REGRESSORS:
            logger.info("residual %s: %s not offered (%d regressors)", var.id, spec.id, frame.shape[1])
            continue
        designs.append((spec, frame))
    return designs


def select_model(
    impact_anom: pd.Series, designs: Sequence[tuple[ModelSpec, pd.DataFrame]]
) -> tuple[int, tuple[CandidateScore, ...]]:
    """Index of the chosen design and the CV score of every candidate (same months for all)."""
    frames = [impact_anom.rename("_impact")] + [d for _, d in designs]
    common = pd.concat(frames, axis=1).dropna().index
    scores = tuple(
        CandidateScore(
            id=spec.id,
            label=spec.label,
            drivers=tuple(design.columns),
            n_months=len(common),
            cv_r2=blocked_cv_r2(impact_anom.loc[common], design.loc[common]),
        )
        for spec, design in designs
    )
    chosen = 0
    base = scores[0].cv_r2
    best = base
    for i, score in enumerate(scores[1:], start=1):
        if score.cv_r2 is None or base is None:
            continue
        if score.cv_r2 >= base + MIN_CV_GAIN and score.cv_r2 > best:
            chosen, best = i, score.cv_r2
    return chosen, scores


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
    """Pick the driver model for one impact variable by blocked CV, fit it, split its trend."""
    designs = candidate_designs(var, driver_anoms)
    chosen, scores = select_model(monthly_anomalies(impact), designs)
    spec, regressors = designs[chosen]
    logger.info(
        "residual %s: model %s chosen; cv_r2 %s",
        var.id, spec.id, {s.id: None if s.cv_r2 is None else round(s.cv_r2, 3) for s in scores},
    )
    return replace(
        _fit_split(var, impact, regressors),
        model_id=spec.id,
        model_label=spec.label,
        cv_r2=scores[chosen].cv_r2,
        candidates=scores,
    )


def _fit_split(var: Variable, impact: pd.Series, regressors: pd.DataFrame) -> ResidualResult:
    """Fit impact_anom ~ const + regressors and split the trend (one fixed model)."""
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
