"""Yearly open-water area of a box at 30 m from NASA OPERA DSWx-HLS (via GIBS, no auth).

OPERA DSWx-HLS (JPL, from Harmonized Landsat Sentinel-2) classifies every 30 m pixel of each
HLS scene: 0 not water, 1 open water, 2 partial surface water, 3 snow/ice, 4 cloud or cloud
shadow, 255 no data. GIBS draws the classes with fixed colours (colormap
`OPERA_Dynamic_Surface_Water_Extent`), so a PNG reads back as the exact classes, not a palette
step. The Earthdata GIS image service of the same product only starts in 2023; GIBS serves
the historical record from 2016 (no scenes from mid-August 2020 to the end of 2022).

Per year:
- The days with a scene over the box come from NASA CMR (granule search, public).
- Each month, its scene days are read in order (at most MAX_TRIES_PER_MONTH, spread) until
  one is clear: at least MIN_COVER_SHARE of the box has a class and at most MAX_CLOUD_SHARE of
  it is cloud or snow/ice. A cloudy or partial scene is skipped, never guessed.
- Water area of a clear scene = open water (class 1) plus the partial surface water (class 2)
  touching it, x the pixel areas (cos-latitude per row). Scattered class-2 pixels away from
  open water are left out (`water_mask`: in hilly winter scenes they are mostly not water).
- The year's value is the median of its clear months; a year needs MIN_MONTHS of them,
  otherwise it is dropped (`attrs["dropped_years"]`).

A year with no scene at all is listed in `attrs["no_scene_years"]` (the product gap) and not
cached (a later reprocessing may fill it); nor is a year with a month without any scene (2020,
at the edge of the gap). A month counts as failed only when a request failed and no clear
scene was found in it. A year where a request failed (CMR or GIBS, after
the GIBS retries) is a gap in `attrs["missing_years"]` and never cached. Completed years are
cached on disk, written atomically. If nothing usable comes back, `WaterExtentError` is raised.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import math
import os
import tempfile
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
from scipy import ndimage

from app.assets import gibs_layers
from app.assets.gibs_layers import GibsLayer, TileFailed

logger = logging.getLogger(__name__)

GIBS_LAYER = "OPERA_L3_Dynamic_Surface_Water_Extent-HLS"
CMR_GRANULES_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
CMR_SHORT_NAME = "OPERA_L3_DSWX-HLS_V1"
CMR_PAGE_SIZE = 2000
FIRST_YEAR = 2016  # first year of the historical record on GIBS
NATIVE_M = 30.0
RESOLUTION = "30 m"
SOURCE = "NASA JPL OPERA Dynamic Surface Water Extent (DSWx-HLS, from Harmonized Landsat Sentinel-2), via GIBS"
METHOD = "median over the year of one clear scene a month"
EARTH_RADIUS_KM = 6371.0088
TIMEOUT_S = 60.0
WORKERS = 4

NOT_WATER, OPEN_WATER, PARTIAL_WATER, SNOW_ICE, CLOUD, NO_DATA = 0, 1, 2, 3, 4, 255
OBSCURED_CLASSES = (SNOW_ICE, CLOUD)
CLASS_COLOURS: dict[tuple[int, int, int], int] = {
    (255, 255, 255): NOT_WATER,
    (0, 0, 255): OPEN_WATER,
    (180, 213, 244): PARTIAL_WATER,
    (0, 255, 255): SNOW_ICE,
    (175, 175, 175): CLOUD,
}
MIN_COVER_SHARE = 0.99  # a scene must classify (almost) the whole box: a swath edge would undercount
MAX_CLOUD_SHARE = 0.05  # of the box: cloud or snow could hide water (OPERA's cloud class includes a buffer)
MAX_TRIES_PER_MONTH = 31  # every scene day: GIBS draws about half of them empty, clear ones are few in winter
MIN_MONTHS = 9  # clear months a year needs
WATER_RULE = "open+partial-touching-open"  # part of the cache key

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "water_extent"
cache_dir_default: Path = CACHE_DIR  # patched in tests

# Only `gibs_layer` is read by the shared GetMap (`gibs_layers._fetch`, with its retries).
LAYER = GibsLayer(
    id="water_extent",
    title="Open water (OPERA DSWx-HLS)",
    gibs_layer=GIBS_LAYER,
    colormap="OPERA_Dynamic_Surface_Water_Extent",
    native_m=NATIVE_M,
    unit="class",
    to_unit=0.0,
    offset=0.0,
    scale=1.0,
    palette="",
    legend={},
    source={"name": SOURCE},
    seasons={},
    first_year=FIRST_YEAR,
)


class WaterExtentError(RuntimeError):
    """No usable water area for this box; `failed` when requests failed (not a plain no-data)."""

    def __init__(self, message: str, failed: bool = False):
        super().__init__(message)
        self.failed = failed


def _this_year() -> int:
    return dt.date.today().year


def last_complete_year() -> int:
    return _this_year() - 1


# --------------------------------------------------------------------------- one scene


def classes_from_rgba(rgba: np.ndarray) -> np.ndarray:
    """DSWx class of each pixel from its GIBS colour; transparent or unknown colour = NO_DATA."""
    rgba = np.asarray(rgba)
    out = np.full(rgba.shape[:2], NO_DATA, dtype=np.uint8)
    opaque = rgba[..., 3] > 0 if rgba.shape[-1] == 4 else np.ones(rgba.shape[:2], dtype=bool)
    rgb = rgba[..., :3]
    for colour, code in CLASS_COLOURS.items():
        out[opaque & np.all(rgb == colour, axis=-1)] = code
    return out


def pixel_area_km2(bbox: Sequence[float], shape: tuple[int, int]) -> np.ndarray:
    """Area (km²) of each pixel of a regular lat/lon grid over bbox, rows north first."""
    west, south, east, north = bbox
    ny, nx = shape
    dlat = (north - south) / ny
    dlon = (east - west) / nx
    lat_rows = north - dlat * (np.arange(ny) + 0.5)
    cell = math.radians(dlat) * math.radians(dlon) * EARTH_RADIUS_KM**2
    return np.outer(np.cos(np.radians(lat_rows)), np.ones(nx)) * cell


def water_mask(classes: np.ndarray) -> np.ndarray:
    """Open water (class 1) plus partial surface water (class 2) touching it (8 neighbours).

    Partial water away from any open water is left out: over the hills around La Viñuela the
    winter scenes carry ~20 km² of scattered class-2 pixels (thousands of specks) against a
    reservoir of at most 5.65 km², while at the shore the partial pixels are the real fringe.
    """
    classes = np.asarray(classes)
    open_water = classes == OPEN_WATER
    beside_open = ndimage.binary_dilation(open_water, structure=np.ones((3, 3), dtype=bool))
    return open_water | (beside_open & (classes == PARTIAL_WATER))


def scene_water_area(classes: np.ndarray, area_km2: np.ndarray) -> float | None:
    """Water area (km², see `water_mask`) of one scene, or None when it is cloudy or partial."""
    classes = np.asarray(classes)
    total = classes.size
    if total == 0:
        return None
    if np.count_nonzero(classes != NO_DATA) / total < MIN_COVER_SHARE:
        return None
    if np.count_nonzero(np.isin(classes, OBSCURED_CLASSES)) / total > MAX_CLOUD_SHARE:
        return None
    return float(area_km2[water_mask(classes)].sum())


def grid_size(bbox: Sequence[float], native_m: float = NATIVE_M) -> tuple[int, int]:
    """(width, height) in pixels at about `native_m` per pixel."""
    west, south, east, north = bbox
    mid = math.radians((south + north) / 2)
    width_m = math.radians(east - west) * EARTH_RADIUS_KM * 1000 * math.cos(mid)
    height_m = math.radians(north - south) * EARTH_RADIUS_KM * 1000
    return max(1, round(width_m / native_m)), max(1, round(height_m / native_m))


# --------------------------------------------------------------------------- scene days (CMR)


def scene_days(client: httpx.Client, bbox: Sequence[float], year: int) -> list[str]:
    """Days (YYYY-MM-DD) with a DSWx-HLS granule over bbox in `year`. Raises httpx.HTTPError."""
    west, south, east, north = bbox
    days: set[str] = set()
    page = 1
    while True:
        r = client.get(
            CMR_GRANULES_URL,
            params={
                "short_name": CMR_SHORT_NAME,
                "bounding_box": f"{west},{south},{east},{north}",
                "temporal": f"{year}-01-01T00:00:00Z,{year}-12-31T23:59:59Z",
                "page_size": CMR_PAGE_SIZE,
                "page_num": page,
            },
        )
        r.raise_for_status()
        entries = r.json().get("feed", {}).get("entry", [])
        days.update(str(e["time_start"])[:10] for e in entries if e.get("time_start"))
        if len(entries) < CMR_PAGE_SIZE:
            return sorted(days)
        page += 1


def tries_for_month(days: Sequence[str], max_tries: int = MAX_TRIES_PER_MONTH) -> list[str]:
    """Up to `max_tries` of a month's days, spread over the month (first and last included)."""
    days = sorted(days)
    if len(days) <= max_tries:
        return days
    idx = np.unique(np.linspace(0, len(days) - 1, max_tries).round().astype(int))
    return [days[i] for i in idx]


# --------------------------------------------------------------------------- cache


def _cache_path(cache_dir: Path, bbox: Sequence[float], year: int) -> Path:
    key = json.dumps(
        [GIBS_LAYER, [round(float(c), 6) for c in bbox], year, MIN_COVER_SHARE, MAX_CLOUD_SHARE, MAX_TRIES_PER_MONTH, WATER_RULE]
    )
    return cache_dir / f"{hashlib.sha256(key.encode()).hexdigest()[:20]}.json"


def _read_cache(path: Path) -> dict[int, float] | None:
    """The cached clear months of a year ({month: km²}); a corrupt file is deleted."""
    if not path.exists():
        return None
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
        return {int(m): float(v) for m, v in entry["months"].items()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        logger.warning("water extent cache %s unreadable (%s), fetching again", path.name, exc)
        path.unlink(missing_ok=True)
        return None


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# --------------------------------------------------------------------------- one year


class _Year:
    def __init__(self, months: dict[int, float], failed: bool, no_scene: bool, scene_months: int = 0):
        self.months = months
        self.failed = failed
        self.no_scene = no_scene
        self.scene_months = scene_months  # months with at least one scene day in the product


def _month_area(
    client: httpx.Client, bbox: Sequence[float], days: Sequence[str], size: tuple[int, int], area: np.ndarray
) -> tuple[float | None, bool]:
    """(water km² of the first clear try, a request failed)."""
    failed = False
    for day in tries_for_month(days):
        try:
            rgba = gibs_layers._fetch(client, LAYER, bbox, day, size)
        except TileFailed as exc:
            logger.warning("%s", exc)
            failed = True
            continue
        if rgba is None:
            continue
        km2 = scene_water_area(classes_from_rgba(rgba), area)
        if km2 is not None:
            return km2, False  # a flaky day before a clear one loses nothing
    return None, failed


def _fetch_year(client: httpx.Client, bbox: Sequence[float], year: int, size: tuple[int, int], area: np.ndarray) -> _Year:
    try:
        days = scene_days(client, bbox, year)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("CMR DSWx-HLS %s: %s", year, type(exc).__name__)
        return _Year({}, failed=True, no_scene=False)
    if not days:
        return _Year({}, failed=False, no_scene=True)
    by_month: dict[int, list[str]] = {}
    for day in days:
        by_month.setdefault(int(day[5:7]), []).append(day)
    months: dict[int, float] = {}
    failed = False
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(lambda m: (m, _month_area(client, bbox, by_month[m], size, area)), sorted(by_month)))
    for month, (km2, month_failed) in results:
        failed = failed or month_failed
        if km2 is not None:
            months[month] = km2
    return _Year(months, failed=failed, no_scene=False, scene_months=len(by_month))


def year_value(months: dict[int, float], min_months: int = MIN_MONTHS) -> float | None:
    """Median of the clear months, None when fewer than `min_months`."""
    if len(months) < min_months:
        return None
    return float(np.median(list(months.values())))


# --------------------------------------------------------------------------- series


def fetch_yearly_water(
    bbox: Sequence[float],
    start: int,
    end: int,
    client: httpx.Client | None = None,
    cache_dir: Path | None = None,
) -> pd.Series:
    """Open-water area (km²) per kept year over bbox, indexed on Jan 1.

    Completed years from FIRST_YEAR only. `attrs`: temporal "annual", clear_months per kept
    year, dropped_years (too few clear months), no_scene_years (no scene in the product),
    missing_years (a request failed). Raises WaterExtentError when no year is usable.
    """
    cache = cache_dir_default if cache_dir is None else cache_dir
    bbox = tuple(float(c) for c in bbox)
    years = list(range(max(start, FIRST_YEAR), min(end, last_complete_year()) + 1))
    size = grid_size(bbox)
    area = pixel_area_km2(bbox, (size[1], size[0]))
    paths = {y: _cache_path(cache, bbox, y) for y in years}
    months_of: dict[int, dict[int, float]] = {}
    for year in years:
        hit = _read_cache(paths[year])
        if hit is not None:
            months_of[year] = hit
    failed: list[int] = []
    no_scene: list[int] = []
    todo = [y for y in years if y not in months_of]
    if todo:
        own = client is None
        client = client or httpx.Client(timeout=TIMEOUT_S)
        try:
            for year in todo:
                got = _fetch_year(client, bbox, year, size, area)
                if got.failed:
                    failed.append(year)  # a gap, asked again next time
                    continue
                if got.no_scene:
                    no_scene.append(year)
                    continue
                months_of[year] = got.months
                if got.scene_months < 12:
                    continue  # the product does not cover the whole year (2020): a reprocessing may fill it
                try:
                    _write_atomic(paths[year], json.dumps({"months": {str(m): v for m, v in got.months.items()}}))
                except OSError as exc:  # a cache that cannot be written must not lose the data
                    logger.warning("water extent cache write failed: %s", exc)
        finally:
            if own:
                client.close()
    values = {y: year_value(months_of[y]) for y in years if y in months_of}
    kept = [y for y in years if values.get(y) is not None]
    if years and not kept:
        why = "requests failed" if failed else "no year with enough clear scenes"
        raise WaterExtentError(f"OPERA DSWx-HLS: {why} in {start}-{end}", failed=bool(failed))
    series = pd.Series(
        [values[y] for y in kept], index=pd.to_datetime([f"{y}-01-01" for y in kept]), dtype=float, name="water_extent"
    )
    series.attrs = {
        "temporal": "annual",
        "clear_months": {y: len(months_of[y]) for y in kept},
        "dropped_years": [y for y in years if y in months_of and values.get(y) is None],
        "no_scene_years": no_scene,
        "missing_years": failed,
    }
    return series
