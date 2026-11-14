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
- Annual water mask (story-mode map): a pixel is water in a year when it is water in at
  least half of its clear observations that year (and has >= MIN_CLEAR_OBS of them).

Data source: NASA AppEEARS area bundle (netCDF4, geographic projection).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from app.extractors.appeears import nc_times

logger = logging.getLogger(__name__)

GREEN = "sur_refl_b04"
NIR = "sur_refl_b02"
STATE = "sur_refl_state_500m"
NDWI_WATER_THRESHOLD = 0.0
MIN_CLEAR_FRACTION = 0.8
EARTH_RADIUS_KM = 6371.0088
MIN_CLEAR_OBS = 3
WATER_FREQUENCY = 0.5
CACHE_CSV = "water_area_monthly.csv"


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
    times = nc_times(ds["time"].values)
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
            datasets.append(ds[[GREEN, NIR, STATE]].sortby("lat", ascending=False))
        else:
            ds.close()
    return datasets


def bundle_paths(bundle_dir: Path) -> list[Path]:
    return sorted(p for p in bundle_dir.rglob("*.nc") if p.is_file()) if bundle_dir.is_dir() else []


def _cache_is_fresh(cache: Path, paths: Sequence[Path]) -> bool:
    return cache.exists() and all(cache.stat().st_mtime >= p.stat().st_mtime for p in paths)


def fetch_water_area(
    bundle_dir: Path, start_year: int = 2003, end_year: int = 2024
) -> pd.Series:
    """Monthly open-water area (km²) from an already-downloaded AppEEARS MOD09A1 bundle.

    The 8-day composite series is cached as CSV in the bundle folder (rebuilt when a
    NetCDF is newer), so repeated sweeps do not re-read ~1000 grids.
    """
    paths = bundle_paths(bundle_dir)
    cache = bundle_dir / CACHE_CSV
    if paths and _cache_is_fresh(cache, paths):
        composites = pd.read_csv(cache, index_col=0, parse_dates=True)["water_area"]
        return to_monthly(composites, start_year, end_year)
    datasets = _open_bundle(paths)
    if not datasets:
        raise FileNotFoundError(f"no MOD09A1 netCDF with {GREEN}/{NIR}/{STATE} in {bundle_dir}")
    try:
        parts = [water_area_from_dataset(ds) for ds in datasets]
    finally:
        for ds in datasets:
            ds.close()
    composites = pd.concat(parts).sort_index()
    composites = composites[~composites.index.duplicated(keep="first")]
    logger.info("water area: %d composites, %d valid", len(composites), composites.notna().sum())
    composites.rename("water_area").to_csv(cache)
    return to_monthly(composites, start_year, end_year)


def composite_water_mask(green: np.ndarray, nir: np.ndarray, state: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(clear, water) boolean grids of one composite; no box-level cloud threshold."""
    green = np.asarray(green, dtype=float)
    nir = np.asarray(nir, dtype=float)
    clear = clear_sky_mask(state) & np.isfinite(green) & np.isfinite(nir)
    with np.errstate(divide="ignore", invalid="ignore"):
        ndwi = (green - nir) / (green + nir)
    return clear, clear & (ndwi > NDWI_WATER_THRESHOLD)


def annual_water_masks(
    bundle_dir: Path, start_year: int = 2003, end_year: int = 2024
) -> tuple[dict[int, np.ndarray], np.ndarray, np.ndarray]:
    """Per-year water mask (True = water), plus lat and lon (north -> south) of the grid.

    A year without any pixel having MIN_CLEAR_OBS clear looks is left out.
    """
    datasets = _open_bundle(bundle_paths(bundle_dir))
    if not datasets:
        raise FileNotFoundError(f"no MOD09A1 netCDF with {GREEN}/{NIR}/{STATE} in {bundle_dir}")
    lat = datasets[0]["lat"].values
    lon = datasets[0]["lon"].values
    shape = (len(lat), len(lon))
    clear_n: dict[int, np.ndarray] = {}
    water_n: dict[int, np.ndarray] = {}
    try:
        for ds in datasets:
            for i, t in enumerate(nc_times(ds["time"].values)):
                if not start_year <= t.year <= end_year:
                    continue
                clear, water = composite_water_mask(
                    ds[GREEN].isel(time=i).values, ds[NIR].isel(time=i).values, ds[STATE].isel(time=i).values
                )
                clear_n[t.year] = clear_n.get(t.year, np.zeros(shape)) + clear
                water_n[t.year] = water_n.get(t.year, np.zeros(shape)) + water
    finally:
        for ds in datasets:
            ds.close()
    masks: dict[int, np.ndarray] = {}
    for year in sorted(clear_n):
        enough = clear_n[year] >= MIN_CLEAR_OBS
        if not enough.any():
            continue
        with np.errstate(divide="ignore", invalid="ignore"):
            freq = water_n[year] / clear_n[year]
        masks[year] = enough & (freq >= WATER_FREQUENCY)
    return masks, lat, lon
