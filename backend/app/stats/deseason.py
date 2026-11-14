"""Remove the seasonal cycle from monthly series.

An anomaly is how far a month is from what that calendar month usually is
(e.g. this July minus the average July over the whole series).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def monthly_anomalies(series: pd.Series) -> pd.Series:
    """Value minus that calendar month's mean over the series. NaN stays NaN.

    Returns a new series; the input is not modified.
    """
    values = series.astype(float)
    months = values.index.month
    climatology = values.groupby(months).transform("mean")
    return (values - climatology).rename(series.name)


def anomaly_std(anomalies: pd.Series) -> float:
    """Sample standard deviation of the anomalies, ignoring NaN (NaN if < 2 values)."""
    valid = anomalies.dropna().to_numpy(dtype=float)
    if valid.size < 2:
        return float("nan")
    return float(np.std(valid, ddof=1))
