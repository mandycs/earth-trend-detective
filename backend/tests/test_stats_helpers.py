"""Seeded synthetic monthly series for the statistics tests."""

from __future__ import annotations

import numpy as np
import pandas as pd


def monthly_index(start: str = "2003-01-01", months: int = 264) -> pd.DatetimeIndex:
    return pd.date_range(start, periods=months, freq="MS")


def ar1_noise(n: int, phi: float, sigma: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    eps = rng.normal(0.0, sigma, n)
    out = np.empty(n)
    out[0] = eps[0] / np.sqrt(1 - phi**2) if phi < 1 else eps[0]
    for i in range(1, n):
        out[i] = phi * out[i - 1] + eps[i]
    return out


def synthetic_series(
    trend_per_decade: float,
    *,
    months: int = 264,
    phi: float = 0.3,
    sigma: float = 1.0,
    amplitude: float = 5.0,
    seed: int = 0,
    start: str = "2003-01-01",
) -> pd.Series:
    """Linear trend + annual cycle + AR(1) noise on a month-start index."""
    index = monthly_index(start, months)
    t_years = np.arange(months) / 12.0
    season = amplitude * np.sin(2 * np.pi * index.month.to_numpy() / 12.0)
    values = 10.0 + trend_per_decade / 10.0 * t_years + season + ar1_noise(months, phi, sigma, seed)
    return pd.Series(values, index=index)
