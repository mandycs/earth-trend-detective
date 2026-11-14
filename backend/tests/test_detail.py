"""Drone-view detail crop: pure helpers (no network)."""

import numpy as np
import pandas as pd
import pytest

from app.assets.detail import size_for, water_surface_m, yearly_levels_m


def test_water_surface_is_the_most_common_flat_height():
    dem = np.full((10, 10), 329.6, dtype=np.float32)
    dem[:3] = np.linspace(340, 400, 30).reshape(3, 10)
    level, share = water_surface_m(dem)
    assert level == pytest.approx(329.6)
    assert share == pytest.approx(0.7)


def test_yearly_levels_are_calendar_means_inside_the_period():
    idx = pd.date_range("2002-01-01", "2005-12-01", freq="MS")
    monthly = pd.Series(np.repeat([300.0, 310.0, 320.0, 330.0], 12), index=idx)
    monthly.iloc[13] = np.nan
    assert yearly_levels_m(monthly, (2003, 2004)) == {2003: 310.0, 2004: 320.0}


def test_size_keeps_ground_aspect():
    w, h = size_for((-114.845, 36.075, -114.775, 36.13), 2048)
    assert w == 2048 and 1900 < h < 2100
