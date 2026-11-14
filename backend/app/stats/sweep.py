"""Sweep: test every variable of a site, correct for multiple testing, rank."""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass

import pandas as pd

from app.catalog import Variable
from app.stats.deseason import monthly_anomalies
from app.stats.fdr import benjamini_hochberg
from app.stats.trend import TrendResult, trend_test
from app.stats.verdict import Verdict, classify

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VariableResult:
    """One row of the sweep; field names mirror `site.json` variables."""

    id: str
    label: str
    unit: str
    sen_slope_per_decade: float | None
    ci_low: float | None
    ci_high: float | None
    sigma_per_decade: float | None
    p_value: float | None
    q_value: float | None
    verdict: str
    direction: str
    n_months: int
    years_span: float
    too_short: bool
    years_needed: int | None = None
    residual_pct_non_climate: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _clean(value: float) -> float | None:
    """NaN/inf -> None so results are JSON-safe."""
    return None if value is None or not math.isfinite(value) else float(value)


def _build(var: Variable, trend: TrendResult, q_value: float) -> VariableResult:
    verdict, direction = classify(q_value, trend.p_value, trend.sen_slope_per_decade)
    return VariableResult(
        id=var.id,
        label=var.label,
        unit=var.units,
        sen_slope_per_decade=_clean(trend.sen_slope_per_decade),
        ci_low=_clean(trend.ci_low),
        ci_high=_clean(trend.ci_high),
        sigma_per_decade=_clean(trend.sigma_per_decade),
        p_value=_clean(trend.p_value),
        q_value=_clean(q_value),
        verdict=verdict.value,
        direction=direction.value,
        n_months=trend.n_months,
        years_span=round(trend.years_span, 2),
        too_short=trend.too_short,
    )


def _rank_key(result: VariableResult) -> tuple[int, float]:
    """real/likely first, then unknown, then too short; within a group by |sigma/decade|."""
    if result.too_short:
        group = 2
    elif result.verdict in (Verdict.REAL, Verdict.LIKELY):
        group = 0
    else:
        group = 1
    return group, -abs(result.sigma_per_decade or 0.0)


def run_sweep(series: Mapping[str, pd.Series], catalog: Sequence[Variable]) -> list[VariableResult]:
    """Deseasonalize, trend-test, FDR-correct and rank every series.

    Raises KeyError if a series id is not in the catalog.
    """
    by_id = {v.id: v for v in catalog}
    missing = set(series) - set(by_id)
    if missing:
        raise KeyError(f"variables not in catalog: {sorted(missing)}")

    trends = {var_id: trend_test(monthly_anomalies(s)) for var_id, s in series.items()}
    q_values = benjamini_hochberg({k: t.p_value for k, t in trends.items()})
    results = [_build(by_id[k], t, q_values[k]) for k, t in trends.items()]
    logger.info("sweep: %d variables, %d real", len(results), sum(r.verdict == "real" for r in results))
    return sorted(results, key=_rank_key)
