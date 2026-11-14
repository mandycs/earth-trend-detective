"""The site sweep reports a non-climate % only for observed impacts (not for GLDAS model output)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

import app.main as main
from app.gather import GatherResult

IDX = pd.date_range("2003-01-01", "2024-12-01", freq="MS")


def seasonal(seed: int, slope: float = 0.0) -> pd.Series:
    rng = np.random.default_rng(seed)
    t = np.arange(len(IDX))
    return pd.Series(10 + 3 * np.sin(2 * np.pi * t / 12) + slope * t + rng.normal(0, 0.3, len(IDX)), index=IDX)


def fake_gather(site, catalog, start, end) -> GatherResult:
    series = {
        "t2m": seasonal(1),
        "precip": seasonal(2),
        "solar": seasonal(3),
        # Strong non-climate decline in both an observed (GRACE) and a modelled (GLDAS) variable.
        "grace_tws": seasonal(4, slope=-0.05),
        "soil_moisture": seasonal(5, slope=-0.05),
    }
    return GatherResult(series=series, missing={}, sources=("power", "grace", "gldas"))


def test_non_climate_pct_only_for_observed_sources(monkeypatch):
    monkeypatch.setattr(main, "gather_site_series", fake_gather)
    body = TestClient(main.app).get("/sites/lake_mead/sweep").json()
    rows = {v["id"]: v for v in body["variables"]}

    assert rows["grace_tws"]["verdict"] == "real"
    assert rows["grace_tws"]["residual_pct_non_climate"] > 80
    assert rows["grace_tws"]["residual"]["observed"] is True

    assert rows["soil_moisture"]["residual_pct_non_climate"] is None
    assert rows["soil_moisture"]["residual"]["observed"] is False

    assert rows["t2m"]["residual_pct_non_climate"] is None  # drivers have no residual
