"""GRACE vs USBR validation metric (no network)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.validation.mead_grace import SOURCE_TITLE, validate_grace_vs_mead

IDX = pd.date_range("2003-01-01", "2024-12-01", freq="MS")


def test_correlated_series_give_high_r_and_trend():
    rng = np.random.default_rng(0)
    t = np.arange(len(IDX))
    signal = -0.02 * t + rng.normal(0, 0.5, len(IDX))
    grace = pd.Series(signal + 2 * np.sin(2 * np.pi * t / 12), index=IDX)
    elevation = pd.Series(350 + 3 * signal + rng.normal(0, 0.2, len(IDX)), index=IDX)
    out = validate_grace_vs_mead(grace, 2003, 2024, fetch_elevation=lambda s, e: elevation).to_dict()
    assert out["r"] > 0.9 and out["n_months"] == len(IDX)
    assert out["elevation_trend_m_per_decade"] < 0
    assert out["source"] == SOURCE_TITLE and out["url"].startswith("https://www.usbr.gov")


def test_too_little_overlap_gives_no_r():
    grace = pd.Series(np.arange(10.0), index=IDX[:10])
    elevation = pd.Series(np.arange(len(IDX), dtype=float), index=IDX)
    out = validate_grace_vs_mead(grace, 2003, 2024, fetch_elevation=lambda s, e: elevation)
    assert out.r is None and out.n_months == 10
