"""Synthetic AppEEARS-like NetCDF bundles (area task, netcdf4, geographic projection).

Mirrors the real AppEEARS file (checked on MOD11A2.061_1km_aid0001.nc, lake_mead,
AppEEARS v3.137): one file per product `<PRODUCT>_<res>_aid0001.nc` holding every
requested layer plus its QC layer, dims (time, lat, lon), lat north -> south, an int8
`crs` grid-mapping variable, time as int `seconds since 2000-01-01 00:00:00+00:00` in a
julian calendar (decodes to cftime), packed integer layers with `_FillValue`,
`scale_factor`/`add_offset` (also 1.0/0.0 on QC layers) and valid_min/valid_max attrs
that xarray does NOT apply. QC_Day: int16, `_FillValue = 0` (which is also "good").
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

TIME_ENCODING = {"units": "seconds since 2000-01-01 00:00:00+00:00", "calendar": "julian", "dtype": "int32"}


def _grid(bbox, ny: int, nx: int) -> tuple[np.ndarray, np.ndarray]:
    w, s, e, n = bbox
    dy, dx = (n - s) / ny, (e - w) / nx
    return np.linspace(n - dy / 2, s + dy / 2, ny), np.linspace(w + dx / 2, e - dx / 2, nx)


def write_product(path: Path, layers: dict, times: pd.DatetimeIndex, bbox) -> Path:
    """`layers`: band -> (values in physical units, NaN = fill; dtype; fill; scale_factor|None)."""
    first = next(iter(layers.values()))[0]
    ny, nx = first.shape[1:]
    lat, lon = _grid(bbox, ny, nx)
    data_vars = {"crs": xr.DataArray(np.int8(-127), attrs={"grid_mapping_name": "latitude_longitude", "epsg_code": 4326})}
    encoding = {"time": TIME_ENCODING}
    for band, (values, dtype, fill, scale) in layers.items():
        info = np.iinfo(dtype)
        data_vars[band] = xr.DataArray(
            values, dims=("time", "lat", "lon"),
            attrs={"grid_mapping": "crs", "long_name": band, "valid_min": info.min, "valid_max": info.max},
        )
        enc = {"dtype": dtype, "_FillValue": fill}
        if scale is not None:
            enc = {**enc, "scale_factor": scale, "add_offset": 0.0}
        encoding[band] = enc
    ds = xr.Dataset(
        data_vars,
        coords={"time": times, "lat": ("lat", lat, {"units": "degrees_north"}), "lon": ("lon", lon, {"units": "degrees_east"})},
        attrs={"Conventions": "CF-1.6", "source": "AppEEARS (synthetic)"},
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(path, encoding=encoding)
    return path


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
    """Single-layer product file (see write_product)."""
    return write_product(path, {band: (values, dtype, fill, scale_factor)}, times, bbox)


def write_lst(path: Path, kelvin: np.ndarray, times: pd.DatetimeIndex, bbox, qc: np.ndarray | None = None) -> Path:
    """MOD11A2 like the real file: int32 LST (scale 0.02, fill 0) + int16 QC_Day (fill 0)."""
    qc_values = np.where(np.isfinite(kelvin), 0, 2) if qc is None else qc
    qc_values = np.where(qc_values == 0, np.nan, qc_values).astype(float)  # 0 is written as fill
    return write_product(
        path,
        {"LST_Day_1km": (kelvin, "int32", 0, 0.02), "QC_Day": (qc_values, "int16", 0, 1.0)},
        times,
        bbox,
    )


def trend_cube(times: pd.DatetimeIndex, ny: int, nx: int, base: float, slope_per_year: np.ndarray, amp: float, noise: float, seed: int = 0) -> np.ndarray:
    """Seasonal cycle + per-pixel linear trend (slope grid (ny, nx), units/yr) + noise."""
    rng = np.random.default_rng(seed)
    t_years = ((times - times[0]).days.to_numpy() / 365.25)[:, None, None]
    season = amp * np.sin(2 * np.pi * times.day_of_year.to_numpy() / 365.25)[:, None, None]
    return base + season + slope_per_year[None] * t_years + rng.normal(0, noise, (len(times), ny, nx))
