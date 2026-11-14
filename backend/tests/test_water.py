import numpy as np
import pandas as pd
import pytest
import xarray as xr

from app.extractors.water import (
    GREEN,
    NIR,
    STATE,
    clear_sky_mask,
    composite_water_area,
    fetch_water_area,
    pixel_area_km2,
    to_monthly,
)

CLOUDY = 0b01
SHADOW = 0b100


def make_dataset(water_cols_per_time: list[int], cloudy_times: tuple[int, ...] = ()) -> xr.Dataset:
    lat = np.linspace(36.5, 36.0, 10)
    lon = np.linspace(-114.9, -114.4, 10)
    times = pd.date_range("2010-01-01", periods=len(water_cols_per_time), freq="8D")
    green = np.full((len(times), 10, 10), 0.08)
    nir = np.full((len(times), 10, 10), 0.30)  # land: NDWI < 0
    state = np.zeros((len(times), 10, 10))
    for t, cols in enumerate(water_cols_per_time):
        nir[t, :, :cols] = 0.02  # water: NDWI > 0
        if t in cloudy_times:
            state[t] = CLOUDY
    dims = ("time", "lat", "lon")
    return xr.Dataset(
        {GREEN: (dims, green), NIR: (dims, nir), STATE: (dims, state)},
        coords={"time": times, "lat": lat, "lon": lon},
    )


def test_clear_sky_mask_rejects_cloud_and_shadow():
    state = np.array([0, CLOUDY, SHADOW, 1 << 10, np.nan])
    assert clear_sky_mask(state).tolist() == [True, False, False, False, False]


def test_pixel_area_shrinks_with_latitude():
    area = pixel_area_km2(np.array([0.0, 60.0]), np.array([0.0, 1.0]))
    assert area[1, 0] == pytest.approx(area[0, 0] * 0.5, rel=1e-6)


def test_composite_water_area_counts_only_water_pixels():
    green = np.array([[0.08, 0.08]])
    nir = np.array([[0.02, 0.30]])
    area = np.array([[2.0, 2.0]])
    assert composite_water_area(green, nir, np.zeros((1, 2)), area) == 2.0


def test_too_cloudy_composite_is_nan():
    green = np.full((1, 10), 0.08)
    nir = np.full((1, 10), 0.02)
    state = np.zeros((1, 10))
    state[0, :3] = CLOUDY  # 70% clear < 80%
    assert np.isnan(composite_water_area(green, nir, state, np.ones((1, 10))))


def test_to_monthly_uses_median_and_full_index():
    idx = pd.to_datetime(["2003-01-01", "2003-01-09", "2003-01-17", "2003-03-06"])
    s = pd.Series([10.0, 100.0, 12.0, 5.0], index=idx, name="water_area")
    monthly = to_monthly(s, 2003, 2003)
    assert len(monthly) == 12
    assert monthly.loc["2003-01-01"] == 12.0
    assert np.isnan(monthly.loc["2003-02-01"])
    assert monthly.loc["2003-03-01"] == 5.0


def test_fetch_water_area_detects_shrinking_lake(tmp_path):
    ds = make_dataset([8, 8, 8, 8, 6, 6, 6, 4, 4, 4], cloudy_times=(3,))
    ds.to_netcdf(tmp_path / "MOD09A1.061_500m_aid0001.nc")
    monthly = fetch_water_area(tmp_path, 2010, 2010)
    valid = monthly.dropna()
    assert valid.iloc[0] > valid.iloc[-1] > 0


def test_fetch_water_area_without_bundle_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        fetch_water_area(tmp_path)
