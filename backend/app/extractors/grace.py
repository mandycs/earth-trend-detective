"""GRACE / GRACE-FO JPL mascon (RL06.3 v4, CRI-filtered) monthly regional extractor.

Product: TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4 (PO.DAAC). One global NetCDF with
every month since 2002-04 on a 0.5 deg grid (lon 0..360, lat -90..90); the variable
`lwe_thickness` is the liquid-water-equivalent anomaly in cm relative to the
2004.0-2009.999 mean.

Choices for a regional mean:
- Longitudes in the file are 0..360; bbox longitudes (-180..180) are converted, and a
  bbox crossing the antimeridian/prime meridian in that convention is handled by wrap.
- Mean = cos(lat)-weighted mean of the 0.5 deg cells whose centres fall inside the bbox.
  If no centre falls inside (bbox smaller than a cell, e.g. Aletsch ~0.2 deg) the
  nearest cell to the bbox centre is used.
- `land_mask`: NOT applied. It is the ocean/land mask used by the CRI filter; all
  three sites are land cells (mask=1 at Lake Mead, Aletsch and Donana), and masking
  would only drop coastal cells of a bbox that already sits on land.
- `scale_factor` (CLM-derived gain factors): NOT applied. They are optional, model-
  based (CLM 2002-2009) and meant for sub-mascon downscaling of land hydrology; CLM
  does not simulate reservoirs (Lake Mead) and the factor is even negative at Donana
  (-0.10), which would flip the sign of the signal. The series therefore represents
  the enclosing ~3 deg mascon: regional (~300 km) water storage, not the exact bbox.
- Months: each solution goes to the calendar month of its mid-time. A few solutions
  straddle two months and collide with a neighbour (2011-12-17..2012-01-15,
  2015-04-12..05-11); they are moved to the other month they span if that one is free
  (JPL's own convention: Dec 2011 and May 2015). Remaining collisions are averaged.
- Output: monthly series named `grace_tws` (cm), month-start index covering
  start_year-01..end_year-12, NaN for months without a GRACE solution (incl. the
  2017-07..2018-05 GRACE/GRACE-FO gap).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import xarray as xr
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

SHORT_NAME = "TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4"
CMR_GRANULES_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "grace"
REPO_ENV = Path(__file__).resolve().parents[3] / ".env"
SERIES_NAME = "grace_tws"
BAND = "lwe_thickness"
FILE_GLOB = "GRCTellus.JPL.*.nc"
TIMEOUT_S = 120.0
CHUNK_BYTES = 1 << 20


# --------------------------------------------------------------------------- download


def find_latest_granule_url(client: httpx.Client) -> str:
    """Return the HTTPS download URL of the newest granule of the collection via CMR."""
    params = {"short_name": SHORT_NAME, "sort_key": "-start_date", "page_size": "1"}
    response = client.get(CMR_GRANULES_URL, params=params)
    response.raise_for_status()
    entries = response.json()["feed"]["entry"]
    if not entries:
        raise RuntimeError(f"CMR returned no granules for {SHORT_NAME}")
    for link in entries[0].get("links", []):
        href = link.get("href", "")
        if href.startswith("https://") and href.endswith(".nc") and link.get("rel", "").endswith("/data#"):
            return href
    raise RuntimeError(f"no HTTPS .nc data link in CMR granule {entries[0].get('title')!r}")


def _load_token() -> str:
    load_dotenv(REPO_ENV)
    token = os.environ.get("NASA_TOKEN", "").strip()
    if not token:
        raise RuntimeError("NASA_TOKEN not set (expected in repo-root .env)")
    return token


def download_granule(url: str, cache_dir: Path, token: str, client: httpx.Client) -> Path:
    """Stream `url` into `cache_dir` (atomic rename); reuse the file if already there."""
    target = cache_dir / url.rsplit("/", 1)[-1]
    if target.exists():
        return target
    cache_dir.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    logger.info("downloading GRACE granule %s", target.name)
    with client.stream("GET", url, headers={"Authorization": f"Bearer {token}"}) as response:
        response.raise_for_status()
        with partial.open("wb") as fh:
            for chunk in response.iter_bytes(CHUNK_BYTES):
                fh.write(chunk)
    partial.replace(target)
    logger.info("GRACE granule saved (%d MB)", target.stat().st_size // (1 << 20))
    return target


def ensure_grace_file(cache_dir: Path = DEFAULT_CACHE_DIR, client: httpx.Client | None = None) -> Path:
    """Path to a local mascon file: newest cached one, else download the latest from CMR."""
    cached = sorted(cache_dir.glob(FILE_GLOB))
    if cached:
        return cached[-1]
    own_client = client is None
    http = client or httpx.Client(timeout=TIMEOUT_S, follow_redirects=True)
    try:
        url = find_latest_granule_url(http)
        return download_granule(url, cache_dir, _load_token(), http)
    finally:
        if own_client:
            http.close()


# --------------------------------------------------------------------------- extraction


def _to_360(lon: float) -> float:
    return lon % 360.0


def _lon_mask(lons: np.ndarray, min_lon: float, max_lon: float) -> np.ndarray:
    lo, hi = _to_360(min_lon), _to_360(max_lon)
    if max_lon - min_lon >= 360.0:
        return np.ones_like(lons, dtype=bool)
    if lo <= hi:
        return (lons >= lo) & (lons <= hi)
    return (lons >= lo) | (lons <= hi)  # bbox wraps across 0 deg in 0..360 space


def _nearest_index(values: np.ndarray, target: float, periodic: bool = False) -> int:
    diff = np.abs(values - target)
    if periodic:
        diff = np.minimum(diff, 360.0 - diff)
    return int(np.argmin(diff))


def regional_mean(da: xr.DataArray, bbox: Sequence[float]) -> xr.DataArray:
    """cos(lat)-weighted mean over cells inside bbox, nearest cell if none inside.

    `da` must have dims (time, lat, lon) with lon in 0..360. Returns a 1-D (time) array.
    """
    min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox)
    if min_lat > max_lat:
        raise ValueError(f"invalid bbox latitudes: {bbox}")
    lats = da["lat"].values
    lons = da["lon"].values
    lat_sel = (lats >= min_lat) & (lats <= max_lat)
    lon_sel = _lon_mask(lons, min_lon, max_lon)
    if lat_sel.any() and lon_sel.any():
        sub = da.isel(lat=np.flatnonzero(lat_sel), lon=np.flatnonzero(lon_sel))
        weights = np.cos(np.deg2rad(sub["lat"]))
        return sub.weighted(weights).mean(dim=("lat", "lon"), skipna=True)
    centre_lat = (min_lat + max_lat) / 2.0
    span = (max_lon - min_lon) % 360.0
    centre_lon = _to_360(min_lon + span / 2.0)
    i_lat = _nearest_index(lats, centre_lat)
    i_lon = _nearest_index(lons, centre_lon, periodic=True)
    logger.debug("bbox %s smaller than a grid cell; using nearest cell", bbox)
    return da.isel(lat=i_lat, lon=i_lon, drop=True)


def _assign_months(ds: xr.Dataset) -> pd.DatetimeIndex:
    """Month-start label for each GRACE solution (mid-month stamp -> month start).

    If `time_bounds` is present, a solution colliding with another one in the same month
    is moved to another month covered by its bounds when that month is free.
    """
    months = pd.DatetimeIndex(pd.to_datetime(ds["time"].values)).to_period("M")
    if "time_bounds" not in ds:
        return months.to_timestamp()
    bounds = pd.to_datetime(ds["time_bounds"].values.ravel()).to_period("M").to_numpy().reshape(-1, 2)
    labels = list(months)
    for i in range(len(labels)):
        if sum(1 for m in labels if m == labels[i]) < 2:
            continue
        start, end = bounds[i]
        if start == end:
            continue  # a clean single-month solution keeps its month
        for candidate in (start, end):
            if candidate != labels[i] and candidate not in labels:
                labels[i] = candidate
                break
    return pd.PeriodIndex(labels, freq="M").to_timestamp()


def extract_series(ds: xr.Dataset, bbox: Sequence[float], start_year: int, end_year: int) -> pd.Series:
    """Monthly regional `grace_tws` series from an opened mascon dataset."""
    mean = regional_mean(ds[BAND], bbox)
    raw = pd.Series(np.asarray(mean.values, dtype=float), index=_assign_months(ds))
    # Collisions that could not be resolved are averaged.
    raw = raw.groupby(level=0).mean()
    full = pd.date_range(f"{start_year}-01-01", f"{end_year}-12-01", freq="MS")
    series = raw.reindex(full)
    series.name = SERIES_NAME
    series.index.name = "date"
    return series


def fetch_grace_series(
    bbox: Sequence[float],
    start_year: int,
    end_year: int,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    client: httpx.Client | None = None,
) -> pd.Series:
    """Monthly GRACE total water storage anomaly (cm) for a bbox [min_lon, min_lat, max_lon, max_lat]."""
    path = ensure_grace_file(cache_dir, client)
    with xr.open_dataset(path) as ds:
        return extract_series(ds, bbox, start_year, end_year)


# --------------------------------------------------------------------------- CLI


def _summary(series: pd.Series) -> str:
    valid = series.dropna()
    if valid.empty:
        return f"n={len(series)} months, all NaN"
    first, last = valid.index[0], valid.index[-1]
    return (
        f"n={len(series)} months, nan={int(series.isna().sum())}, "
        f"first {first:%Y-%m}={valid.iloc[0]:.2f} cm, last {last:%Y-%m}={valid.iloc[-1]:.2f} cm, "
        f"min={valid.min():.2f}, max={valid.max():.2f}"
    )


def main() -> None:
    import yaml

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # keep signed redirect URLs out of logs
    sites_path = Path(__file__).resolve().parents[2] / "catalog" / "sites.yaml"
    data = yaml.safe_load(sites_path.read_text(encoding="utf-8"))
    start_year, end_year = data["study_period"]
    for site in data["sites"]:
        series = fetch_grace_series(site["bbox"], start_year, end_year)
        print(f"{site['id']:<10} {_summary(series)}")


if __name__ == "__main__":
    main()
