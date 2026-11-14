"""Validate the GRACE water-storage story at Lake Mead against USBR reservoir elevation.

Not NASA data: USBR elevation only checks that the NASA signal tracks the real reservoir.
Metric: Pearson correlation of monthly anomalies (seasonal cycle removed from both) on
the months where both series have data.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from app.stats.deseason import monthly_anomalies
from app.stats.trend import trend_test
from app.validation.usbr import USBR_MEAD_URL, fetch_mead_elevation

logger = logging.getLogger(__name__)

SOURCE_TITLE = "U.S. Bureau of Reclamation (not NASA, validation only)"
METRIC = "correlation of monthly anomalies"
MIN_OVERLAP = 24

ElevationFetcher = Callable[[int, int], pd.Series]


@dataclass(frozen=True)
class MeadValidation:
    r: float | None
    n_months: int
    elevation_trend_m_per_decade: float | None

    def to_dict(self) -> dict:
        return {
            "source": SOURCE_TITLE,
            "url": USBR_MEAD_URL,
            "metric": METRIC,
            "r": self.r,
            "n_months": self.n_months,
            "elevation_trend_m_per_decade": self.elevation_trend_m_per_decade,
        }


def _finite(value: float) -> float | None:
    return float(value) if value is not None and math.isfinite(value) else None


def validate_grace_vs_mead(
    grace_tws: pd.Series,
    start: int,
    end: int,
    fetch_elevation: ElevationFetcher = fetch_mead_elevation,
) -> MeadValidation:
    """Correlate GRACE storage anomalies with USBR elevation anomalies over [start, end]."""
    elevation = fetch_elevation(start, end)
    elev_anom = monthly_anomalies(elevation)
    both = pd.concat(
        [monthly_anomalies(grace_tws).rename("grace"), elev_anom.rename("elev")], axis=1, join="inner"
    ).dropna()
    n = len(both)
    r = _finite(both["grace"].corr(both["elev"])) if n >= MIN_OVERLAP else None
    trend = trend_test(elev_anom)
    slope = None if trend.too_short else _finite(trend.sen_slope_per_decade)
    logger.info("Mead validation: r=%s over %d months", r, n)
    return MeadValidation(r=r, n_months=n, elevation_trend_m_per_decade=slope)
