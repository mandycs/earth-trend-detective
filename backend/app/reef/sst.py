"""Sea surface temperature over the reef box from NASA JPL MUR (GHRSST L4), monthly.

MUR is the only SST record of this case; NOAA Coral Reef Watch SST is never mixed in.

- `load_mur_year`: one year of the MUR grid (one ERDDAP request through `erddap.fetch_grid`),
  cached as `mur_<year>_<w>_<s>_<e>_<n>_s5.nc` in `cache_dir`. Past years only are cached.
- `mur_grid`: the years one after the other (never in parallel), as a `maps.Grid` with
  rows north -> south (ERDDAP answers south first), month-start times, °C. A year whose
  fetch fails is listed in `missing_years`, never left as a silent gap.
- `box_mean_series`: plain mean of the valid sea pixels per month.
- `write_sst_maps`: `trend_sst` and `year_sst_<YYYY>` through `maps.write_variable_maps`,
  with the missing years written into both sidecars.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import warnings
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from app.assets import maps
from app.catalog import Variable, load_catalog
from app.extractors import erddap

logger = logging.getLogger(__name__)

MUR_STRIDE = 5  # ~0.05° over the central box (81 x 91 cells)
SST_VAR_ID = "sst"
DIMS = ("time", "latitude", "longitude")
_RENAME = {"lat": "latitude", "lon": "longitude"}

Fetch = Callable[..., xr.DataArray]


@dataclass(frozen=True)
class MurGrid(maps.Grid):
    years: tuple[int, ...] = ()  # years requested, read or not
    missing_years: tuple[int, ...] = ()  # years whose fetch failed after its retries


def _sst_variable() -> Variable:
    return next(v for v in load_catalog() if v.id == SST_VAR_ID)


def _cache_file(year: int, bbox: Sequence[float], cache_dir: Path) -> Path:
    w, s, e, n = (float(x) for x in bbox)
    return cache_dir / f"mur_{year}_{w}_{s}_{e}_{n}_s{MUR_STRIDE}.nc"


def _normalise(da: xr.DataArray, var: Variable) -> xr.DataArray:
    """Dims time/latitude/longitude, latitude north -> south, month-start times, °C."""
    da = da.rename({k: v for k, v in _RENAME.items() if k in da.dims})
    da = da.transpose(*DIMS).sortby("latitude", ascending=False)
    times = pd.DatetimeIndex(da["time"].values).to_period("M").to_timestamp()
    da = da.assign_coords(time=times)
    # fetch_grid returns raw dataset units; the catalog says how to reach °C.
    return (da.astype(float) * var.scale + var.offset).rename(var.id)


def load_mur_year(
    year: int,
    bbox: Sequence[float],
    cache_dir: Path,
    fetch: Fetch = erddap.fetch_grid,
    offline: bool = False,
) -> xr.DataArray:
    """One year of MUR SST over bbox (west, south, east, north), normalised (see module).

    Raises `FileNotFoundError` offline without a cache file, `ErddapError` when the fetch fails.
    """
    var = _sst_variable()
    path = _cache_file(year, bbox, cache_dir)
    if path.is_file():
        with xr.open_dataarray(path) as cached:
            return _normalise(cached.load(), var)
    if offline:
        raise FileNotFoundError(f"MUR {year}: no cached grid at {path} (offline)")
    raw = fetch(var.dataset, var.band, tuple(bbox), year, year, MUR_STRIDE)
    if raw.attrs.get("missing_years"):
        raise erddap.ErddapError(f"MUR {year}: the fetch reported the year missing")
    if year < dt.date.today().year:  # the current year still grows: not cached
        cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".nc.tmp")
        raw.drop_attrs().to_netcdf(tmp)
        tmp.replace(path)
    return _normalise(raw, var)


def mur_grid(
    years: Sequence[int],
    bbox: Sequence[float],
    cache_dir: Path,
    fetch: Fetch = erddap.fetch_grid,
    offline: bool = False,
) -> MurGrid:
    """The MUR years, fetched one after the other, as one grid (rows north -> south, °C).

    A failed year goes to `missing_years`; if the first `erddap.FAIL_FAST_YEARS` requested
    years all fail, or every year fails, the source is down and `ErddapError` is raised.
    """
    years = list(years)
    head = years[: erddap.FAIL_FAST_YEARS]
    parts: list[xr.DataArray] = []
    missing: list[int] = []
    for year in years:
        try:
            parts.append(load_mur_year(year, bbox, cache_dir, fetch=fetch, offline=offline))
        except erddap.ErddapError as exc:
            logger.warning("MUR %s failed, listed as missing: %s", year, exc)
            missing.append(year)
            if head and missing[: len(head)] == head:
                raise erddap.ErddapError(f"MUR: the first {len(head)} years all failed") from exc
    if not parts:
        raise erddap.ErddapError("MUR: no year could be read")
    cube = xr.concat(parts, dim="time").sortby("time").sortby("latitude", ascending=False)
    return MurGrid(
        times=pd.DatetimeIndex(cube["time"].values),
        monthly=np.asarray(cube.values, dtype=float),
        lat=np.asarray(cube["latitude"].values, dtype=float),
        lon=np.asarray(cube["longitude"].values, dtype=float),
        years=tuple(years),
        missing_years=tuple(missing),
    )


def box_mean_series(grid: MurGrid) -> pd.Series:
    """Plain mean of the valid sea pixels per month (month-start index; NaN = no pixel).

    The index runs January of the first requested year to December of the last, so a
    missing month or a failed year (first and last included) shows as NaN, never disappears.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN month -> NaN
        means = np.nanmean(grid.monthly.reshape(len(grid.times), -1), axis=1)
    series = pd.Series(means, index=pd.DatetimeIndex(grid.times), dtype=float)
    years = sorted(set(grid.years) | set(series.index.year))
    if not years:
        return series.rename(SST_VAR_ID)
    full = pd.date_range(f"{years[0]}-01-01", f"{years[-1]}-12-01", freq="MS")
    return series.reindex(full).rename(SST_VAR_ID)


def write_sst_maps(
    var: Variable, grid: MurGrid, site_dir: Path, bbox: Sequence[float], start: int, end: int
) -> list[Path]:
    """`trend_sst` and `year_sst_<YYYY>` (with sidecars); missing years noted in both JSONs."""
    written = maps.write_variable_maps(var, grid, site_dir, bbox, start, end)
    missing = sorted(y for y in grid.missing_years if start <= y <= end)
    for name in (f"trend_{var.id}.json", f"year_{var.id}.json"):
        path = site_dir / name
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["missing_years"] = missing
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return written
