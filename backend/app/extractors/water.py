"""Open-water area of a reservoir from MODIS MOD09A1 8-day surface reflectance.

Method (per 8-day composite):
- NDWI = (green - NIR) / (green + NIR), green = band 4, NIR = band 2 (McFeeters 1996).
  A pixel is open water when NDWI > NDWI_WATER_THRESHOLD.
- Clear-sky mask from `sur_refl_state_500m`: cloud state (bits 0-1) == clear, no cloud
  shadow (bit 2), no internal cloud flag (bit 10).
- A composite is used only when at least MIN_CLEAR_FRACTION of the box is clear;
  cloudy pixels are not guessed.
- Water area = number of water pixels x pixel area (cos-latitude corrected), in km².
- Monthly value = median of the valid composites in that month (robust to one bad scene).

Data source: NASA AppEEARS area bundle (netCDF4, geographic projection).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

logger = logging.getLogger(__name__)

GREEN = "sur_refl_b04"
NIR = "sur_refl_b02"
STATE = "sur_refl_state_500m"
NDWI_WATER_THRESHOLD = 0.0
MIN_CLEAR_FRACTION = 0.8
EARTH_RADIUS_KM = 6371.0088


def clear_sky_mask(state: np.ndarray) -> np.ndarray:
    """True where the MOD09A1 state flags say the pixel is clear (no cloud, shadow)."""
    s = np.nan_to_num(np.asarray(state, dtype=float), nan=-1).astype(np.int64)
    valid = s >= 0
    cloud_clear = (s & 0b11) == 0
    no_shadow = (s >> 2) & 1 == 0
    no_internal_cloud = (s >> 10) & 1 == 0
    return valid & cloud_clear & no_shadow & no_internal_cloud


def pixel_area_km2(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Area of each grid cell (lat x lon) in km² for a regular geographic grid."""
    dlat = abs(float(np.median(np.diff(lat)))) if len(lat) > 1 else 0.0
    dlon = abs(float(np.median(np.diff(lon)))) if len(lon) > 1 else 0.0
    cell = np.deg2rad(dlat) * np.deg2rad(dlon) * EARTH_RADIUS_KM**2
    return np.outer(np.cos(np.deg2rad(lat)), np.ones(len(lon))) * cell


def composite_water_area(
    green: np.ndarray, nir: np.ndarray, state: np.ndarray, area_km2: np.ndarray
) -> float:
    """Water area (km²) of one composite, or NaN when the box is too cloudy."""
    green = np.asarray(green, dtype=float)
    nir = np.asarray(nir, dtype=float)
    clear = clear_sky_mask(state) & np.isfinite(green) & np.isfinite(nir)
    if clear.mean() < MIN_CLEAR_FRACTION:
        return float("nan")
    with np.errstate(divide="ignore", invalid="ignore"):
        ndwi = (green - nir) / (green + nir)
    water = clear & (ndwi > NDWI_WATER_THRESHOLD)
    return float(area_km2[water].sum())


def water_area_from_dataset(ds: xr.Dataset) -> pd.Series:
    """8-day water area series (km²) from a dataset with GREEN, NIR, STATE over (time, lat, lon)."""
    area = pixel_area_km2(ds["lat"].values, ds["lon"].values)
    times = pd.to_datetime(ds["time"].values)
    values = [
        composite_water_area(ds[GREEN].isel(time=i).values, ds[NIR].isel(time=i).values,
                             ds[STATE].isel(time=i).values, area)
        for i in range(len(times))
    ]
    return pd.Series(values, index=times, name="water_area").sort_index()


def to_monthly(composites: pd.Series, start_year: int, end_year: int) -> pd.Series:
    """Median of valid composites per month, on a full month-start index with NaN gaps."""
    monthly = composites.dropna().groupby(composites.dropna().index.to_period("M")).median()
    monthly.index = monthly.index.to_timestamp()
    full = pd.date_range(f"{start_year}-01-01", f"{end_year}-12-01", freq="MS")
    return monthly.reindex(full).rename(composites.name)


def _open_bundle(paths: Sequence[Path]) -> list[xr.Dataset]:
    datasets = []
    for p in paths:
        ds = xr.open_dataset(p)
        if {GREEN, NIR, STATE} <= set(ds.data_vars):
            datasets.append(ds[[GREEN, NIR, STATE]])
        else:
            ds.close()
    return datasets


def fetch_water_area(
    bundle_dir: Path, start_year: int = 2003, end_year: int = 2024
) -> pd.Series:
    """Monthly open-water area (km²) from an already-downloaded AppEEARS MOD09A1 bundle."""
    paths = sorted(bundle_dir.glob("*.nc"))
    datasets = _open_bundle(paths)
    if not datasets:
        raise FileNotFoundError(f"no MOD09A1 netCDF with {GREEN}/{NIR}/{STATE} in {bundle_dir}")
    parts = [water_area_from_dataset(ds) for ds in datasets]
    composites = pd.concat(parts).sort_index()
    composites = composites[~composites.index.duplicated(keep="first")]
    logger.info("water area: %d composites, %d valid", len(composites), composites.notna().sum())
    return to_monthly(composites, start_year, end_year)
