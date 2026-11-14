"""Synthetic AppEEARS-like NetCDF bundles (area task, netcdf4, geographic projection).

Mirrors the AppEEARS layout: one file per product named `<PRODUCT>_<res>_aid0001.nc`,
dims (time, lat, lon), lat north -> south, a `crs` grid-mapping variable, time encoded
as `days since 2000-01-01` with a julian calendar (decodes to cftime), packed integer
layers with `_FillValue` and, where the product has one, `scale_factor`.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

TIME_ENCODING = {"units": "days since 2000-01-01 00:00:00", "calendar": "julian", "dtype": "float64"}


def _grid(bbox, ny: int, nx: int) -> tuple[np.ndarray, np.ndarray]:
    w, s, e, n = bbox
    dy, dx = (n - s) / ny, (e - w) / nx
    return np.linspace(n - dy / 2, s + dy / 2, ny), np.linspace(w + dx / 2, e - dx / 2, nx)


def write_layer(
    path: Path,
    band: str,
    values: np.ndarray,
    times: pd.DatetimeIndex,
    bbox,
    dtype: str,
    fill: int,
    scale_factor: float | None = None,
) -> Path:
    """`values` in physical units (NaN = fill); written packed like AppEEARS does."""
    ny, nx = values.shape[1:]
    lat, lon = _grid(bbox, ny, nx)
    da = xr.DataArray(values, dims=("time", "lat", "lon"), attrs={"grid_mapping": "crs", "long_name": band})
    ds = xr.Dataset(
        {band: da, "crs": xr.DataArray(np.int8(0), attrs={"grid_mapping_name": "latitude_longitude"})},
        coords={"time": times, "lat": ("lat", lat, {"units": "degrees_north"}), "lon": ("lon", lon, {"units": "degrees_east"})},
    )
    enc = {"dtype": dtype, "_FillValue": fill}
    if scale_factor is not None:
        enc = {**enc, "scale_factor": scale_factor, "add_offset": 0.0}
    path.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(path, encoding={band: enc, "time": TIME_ENCODING})
    return path


def trend_cube(times: pd.DatetimeIndex, ny: int, nx: int, base: float, slope_per_year: np.ndarray, amp: float, noise: float, seed: int = 0) -> np.ndarray:
    """Seasonal cycle + per-pixel linear trend (slope grid (ny, nx), units/yr) + noise."""
    rng = np.random.default_rng(seed)
    t_years = ((times - times[0]).days.to_numpy() / 365.25)[:, None, None]
    season = amp * np.sin(2 * np.pi * times.day_of_year.to_numpy() / 365.25)[:, None, None]
    return base + season + slope_per_year[None] * t_years + rng.normal(0, noise, (len(times), ny, nx))
