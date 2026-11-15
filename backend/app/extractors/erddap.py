"""Sea data from NOAA CoastWatch ERDDAP griddap (no auth): point series and small grids.

Access facts (tested live, 2026-11-15): brackets in the query must be URL-encoded
(%5B/%5D) or the answer is empty; long time ranges answer 502/503, so every request
covers one year, and requests are serialized process-wide (parallel calls get 408).
A window past the dataset's time axis answers 404 "no matching results": the window is
clamped to the axis bound ERDDAP reports and asked again; a year wholly outside is a gap.

Each year's CSV is cached on disk (`data/cache/erddap/<dataset>/<hash>.csv`); past years
forever, the current year never (it still grows). A year that fails after its retries is a
gap listed in `attrs["missing_years"]`; if the first three requested years all fail, the
source is down and `ErddapError` is raised.

Datasets: MUR SST `jplMURSST41mday` and MODIS Aqua chlorophyll `erdMH1chlamday_R2022SQ`
on the CoastWatch West Coast node; NOAA Coral Reef Watch degree heating weeks
`noaacrwdhwDaily` on the CoastWatch central node.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import math
import os
import re
import tempfile
import threading
import time
from collections.abc import Callable, Sequence
from io import StringIO
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import xarray as xr

logger = logging.getLogger(__name__)

ERDDAP_BASE = "https://coastwatch.pfeg.noaa.gov/erddap/griddap"
DATASET_BASES = {"noaacrwdhwDaily": "https://coastwatch.noaa.gov/erddap/griddap"}
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "erddap"
TIMEOUT_S = 30.0
RETRY_STATUS = frozenset({408, 502, 503, 504})
RETRIES = 2
PAUSE_S = 5.0
FAIL_FAST_YEARS = 3  # the first N requested years all failing = the source is down
MAX_CELL_OFFSET = 0.1  # degrees: how far a masked coastal cell may move to a valid one
YEARLY_MAX_MONTHS = (1, 6)  # DHW: January to June (a whole year in one call answers 502)
NORTH_WARM_MONTHS = (7, 12)  # the warm half of the year north of the equator
GEBCO_CELLS_PER_DEGREE = 240  # GEBCO 2020: 15 arc-second grid
GEBCO_MAX_SIDE = 200  # points per side of one bathymetry request
NO_RESULTS = "Your query produced no matching results"
# ERDDAP's 404 names the real axis bound: "... axis maximum=<asked> (and even <bound>)."
_AXIS_BOUND = re.compile(r"axis (maximum|minimum)=\S+ \(and even (\d{4}-\d\d-\d\dT[\d:]+Z)\)")
_TIME_FMT = "%Y-%m-%dT%H:%M:%SZ"

_sleep = time.sleep  # patched in tests
_REQUEST_LOCK = threading.Lock()  # one ERDDAP request at a time in this process
cache_dir_default: Path = DEFAULT_CACHE_DIR  # patched in tests


def _today() -> dt.date:
    return dt.date.today()


class ErddapError(RuntimeError):
    """ERDDAP answered with an error, an HTML page, or not at all."""


class _NoResults(Exception):
    """404 "no matching results"; the message may carry the time axis bound."""


def new_client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_S, follow_redirects=True)


# --------------------------------------------------------------------------- URLs and parsing


def _axis(start: str | float, stop: str | float | None = None, stride: int = 1) -> str:
    if stop is None:
        return f"%5B({start})%5D"
    return f"%5B({start}):{stride}:({stop})%5D"


def griddap_url(dataset: str, variable: str, axes: Sequence[str]) -> str:
    base = DATASET_BASES.get(dataset, ERDDAP_BASE)
    return f"{base}/{dataset}.csv?{variable}{''.join(axes)}"


def _window(year: int, months: tuple[int, int]) -> tuple[pd.Timestamp, pd.Timestamp]:
    first = pd.Timestamp(year=year, month=months[0], day=1)
    last = pd.Timestamp(year=year, month=months[1], day=1) + pd.offsets.MonthEnd(1)
    return first, last + pd.Timedelta(hours=23, minutes=59, seconds=59)


def parse_csv(text: str, variable: str) -> pd.DataFrame:
    """griddap CSV -> columns time (UTC-naive), latitude, longitude, value (float).

    Row 2 of an ERDDAP CSV holds the units and is skipped.
    """
    head = text.lstrip()[:200].lower()
    if head.startswith("<!doctype") or head.startswith("<html") or head.startswith("error"):
        raise ErddapError("ERDDAP answered with an error page instead of CSV")
    try:
        frame = pd.read_csv(StringIO(text), skiprows=[1])
    except Exception as exc:  # noqa: BLE001 - any unreadable body is a source failure
        raise ErddapError(f"unreadable ERDDAP CSV: {exc}") from exc
    if not {"time", "latitude", "longitude", variable} <= set(frame.columns):
        raise ErddapError(f"ERDDAP CSV without the expected columns: {list(frame.columns)}")
    times = pd.to_datetime(frame["time"], utc=True).dt.tz_localize(None)
    return pd.DataFrame(
        {
            "time": times,
            "latitude": frame["latitude"].astype(float),
            "longitude": frame["longitude"].astype(float),
            "value": pd.to_numeric(frame[variable], errors="coerce").astype(float),
        }
    )


# --------------------------------------------------------------------------- requests and cache


def _request(client: httpx.Client, url: str) -> str:
    """One request (serialized process-wide) with retries on a busy server."""
    for attempt in range(1, RETRIES + 1):
        try:
            with _REQUEST_LOCK:
                response = client.get(url)
        except httpx.HTTPError as exc:
            if attempt == RETRIES:
                raise ErddapError(f"ERDDAP did not answer: {type(exc).__name__}") from exc
            _sleep(PAUSE_S)
            continue
        if response.status_code in RETRY_STATUS:
            if attempt == RETRIES:
                raise ErddapError(f"ERDDAP busy: HTTP {response.status_code}")
            _sleep(PAUSE_S)
            continue
        if response.status_code == 404 and NO_RESULTS in response.text:
            raise _NoResults(response.text)
        if response.status_code != 200:
            raise ErddapError(f"ERDDAP HTTP {response.status_code}")
        return response.text
    raise ErddapError("ERDDAP did not answer")  # pragma: no cover - loop always returns or raises


def _cache_path(cache_dir: Path, dataset: str, url: str) -> Path:
    return cache_dir / dataset / f"{hashlib.sha256(url.encode()).hexdigest()[:20]}.csv"


def _write_atomic(path: Path, text: str) -> None:
    """Write `text` to `path` through a temp file in the same directory, then rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _cached_frame(
    client: httpx.Client, dataset: str, variable: str, url: str, year: int, cache_dir: Path, cacheable: bool = True
) -> pd.DataFrame:
    path = _cache_path(cache_dir, dataset, url)
    if path.exists():
        try:
            return parse_csv(path.read_text(encoding="utf-8"), variable)
        except (ErddapError, OSError, UnicodeDecodeError) as exc:  # corrupt entry: drop it, fetch once more
            logger.warning("ERDDAP %s: cache file %s unreadable (%s), fetching again", dataset, path.name, exc)
            path.unlink(missing_ok=True)
    text = _request(client, url)
    frame = parse_csv(text, variable)  # validate before caching
    # The current year still grows and a clamped window is partial: neither is cached.
    if cacheable and year < _today().year:
        try:
            _write_atomic(path, text)
        except OSError as exc:  # a cache that cannot be written must not lose the data
            logger.warning("ERDDAP %s: cache write failed: %s", dataset, exc)
    return frame


def _year_frame(
    client: httpx.Client,
    dataset: str,
    variable: str,
    space: Sequence[str],
    year: int,
    months: tuple[int, int],
    cache_dir: Path,
) -> pd.DataFrame | None:
    """One year (window `months`) of data; None when the year is wholly outside the dataset.

    A window that runs past the time axis is clamped to the bound ERDDAP reports and asked
    again, so a partial first or last year is kept. Rows ERDDAP snaps outside the window
    (the 12-31 stop lands on next January) are dropped.
    """
    first, last = _window(year, months)
    lo, hi = first, last
    for _ in range(2):
        url = griddap_url(dataset, variable, [_axis(lo.strftime(_TIME_FMT), hi.strftime(_TIME_FMT)), *space])
        try:
            frame = _cached_frame(client, dataset, variable, url, year, cache_dir, cacheable=(lo, hi) == (first, last))
            return frame[(frame["time"] >= first) & (frame["time"] <= last)]
        except _NoResults as exc:
            bounds = {kind: pd.Timestamp(stamp).tz_localize(None) for kind, stamp in _AXIS_BOUND.findall(str(exc))}
            new_lo = max(lo, bounds.get("minimum", lo))
            new_hi = min(hi, bounds.get("maximum", hi))
            if (new_lo, new_hi) == (lo, hi) or new_lo > new_hi:
                logger.info("ERDDAP %s: no data in %s (outside the dataset's time axis)", dataset, year)
                return None
            logger.info("ERDDAP %s: %s clamped to the time axis %s..%s", dataset, year, new_lo, new_hi)
            lo, hi = new_lo, new_hi
    logger.warning("ERDDAP %s: %s dropped, still outside the time axis after clamping", dataset, year)
    return None


class _YearFailures:
    """Years that failed after their retries; raises once the first N requested all failed."""

    def __init__(self, dataset: str, years: Sequence[int]):
        self.dataset = dataset
        self.years = list(years)
        self.failed: list[int] = []

    def add(self, year: int, exc: Exception) -> None:
        logger.warning("ERDDAP %s: year %s failed, kept as a gap: %s", self.dataset, year, exc)
        self.failed.append(year)
        head = self.years[: min(FAIL_FAST_YEARS, len(self.years))]
        if self.failed[: len(head)] == head:
            raise ErddapError(f"ERDDAP {self.dataset}: the first {len(head)} years all failed") from exc


def warm_season(lat: float) -> tuple[int, int]:
    """Months of the sea's warm half of the year: January-June south of the equator,
    July-December north of it (heat stress on corals peaks there)."""
    return YEARLY_MAX_MONTHS if lat < 0 else NORTH_WARM_MONTHS


# --------------------------------------------------------------------------- point series


def _point_space(cell: tuple[float, float]) -> list[str]:
    return [_axis(cell[0]), _axis(cell[1])]


def _nearest_valid_cell(
    fetch_year: Callable[[Sequence[str]], pd.DataFrame | None], lat: float, lon: float
) -> tuple[float, float] | None:
    """The valid cell nearest to (lat, lon) within MAX_CELL_OFFSET, over one year of data.

    Only cells within the offset are candidates; among them a cell needs at least half as
    many valid values as the best one, so a mostly-land cell with one stray value is not
    picked over a sea cell.
    """
    d = MAX_CELL_OFFSET
    frame = fetch_year([_axis(round(lat - d, 6), round(lat + d, 6)), _axis(round(lon - d, 6), round(lon + d, 6))])
    if frame is None or frame.empty:
        return None
    counts = frame.groupby(["latitude", "longitude"])["value"].count()
    counts = counts[[c > 0 and math.dist(cell, (lat, lon)) <= d + 1e-9 for cell, c in counts.items()]]
    if counts.empty:
        return None
    good = counts[counts >= counts.max() / 2]
    best = min(good.index, key=lambda c: (math.dist(c, (lat, lon)), -int(good[c]), c))
    return float(best[0]), float(best[1])


def _point_frames(
    dataset: str,
    variable: str,
    lat: float,
    lon: float,
    start: int,
    end: int,
    months: tuple[int, int],
    client: httpx.Client | None,
    cache_dir: Path | None,
) -> tuple[list[pd.DataFrame], tuple[float, float], list[int]]:
    cache = cache_dir_default if cache_dir is None else cache_dir
    own = client is None
    client = client or new_client()
    years = list(range(start, end + 1))
    failures = _YearFailures(dataset, years)
    try:
        cell = (float(lat), float(lon))
        probed = False
        frames: list[pd.DataFrame] = []
        for year in years:  # one year per call, sequentially

            def fetch_year(space: Sequence[str], year: int = year) -> pd.DataFrame | None:
                return _year_frame(client, dataset, variable, space, year, months, cache)

            try:
                frame = fetch_year(_point_space(cell))
                if frame is None or frame.empty:
                    continue
                if not probed and frame["value"].notna().sum() == 0:
                    try:
                        moved = _nearest_valid_cell(fetch_year, lat, lon)
                    except ErddapError as exc:  # probe again next year
                        logger.warning("ERDDAP %s: nearest-cell probe failed: %s", dataset, exc)
                    else:
                        probed = True
                        if moved is not None:
                            logger.info("ERDDAP %s: cell %s masked, using %s", dataset, cell, moved)
                            cell = moved
                            frame = fetch_year(_point_space(cell))
                            if frame is None or frame.empty:
                                continue
                else:
                    probed = True
            except ErddapError as exc:
                failures.add(year, exc)
                continue
            if frame["value"].notna().any():
                rows = frame[["latitude", "longitude"]].iloc[0]
                cell = (float(rows["latitude"]), float(rows["longitude"]))  # the grid cell ERDDAP used
            frames.append(frame)
        return frames, cell, failures.failed
    finally:
        if own:
            client.close()


def fetch_point_monthly(
    dataset: str,
    variable: str,
    lat: float,
    lon: float,
    start: int,
    end: int,
    client: httpx.Client | None = None,
    cache_dir: Path | None = None,
) -> tuple[pd.Series, tuple[float, float]]:
    """Monthly series at the grid cell nearest (lat, lon), indexed by month start.

    A cell masked for the whole first year (coast seen as land) moves to the nearest valid
    cell within 0.1°. Returns the series (raw dataset units, NaN gaps) and the cell used,
    also stored in `series.attrs["cell"]`; failed years in `attrs["missing_years"]`.
    """
    frames, cell, missing = _point_frames(dataset, variable, lat, lon, start, end, (1, 12), client, cache_dir)
    if frames:
        data = pd.concat(frames)
        months = data["time"].dt.to_period("M").dt.to_timestamp()
        series = data["value"].groupby(months.to_numpy()).mean()
    else:
        series = pd.Series(dtype=float)
    series.index = pd.DatetimeIndex(series.index)
    series = series.sort_index().astype(float).rename(variable)
    series.attrs["cell"] = cell
    series.attrs["missing_years"] = missing
    return series, cell


def fetch_point_yearly_peaks(
    dataset: str,
    variable: str,
    lat: float,
    lon: float,
    start: int,
    end: int,
    months: tuple[int, int] = YEARLY_MAX_MONTHS,
    client: httpx.Client | None = None,
    cache_dir: Path | None = None,
) -> tuple[dict[int, tuple[float | None, str | None]], tuple[float, float], list[int]]:
    """Yearly peak of a daily product over `months`: {year: (value, "YYYY-MM-DD")}, the grid cell
    used and the years whose fetch failed (absent from the dict). A year with no valid day is
    (None, None), never 0; the value is not rounded."""
    frames, cell, missing = _point_frames(dataset, variable, lat, lon, start, end, months, client, cache_dir)
    peaks: dict[int, tuple[float | None, str | None]] = {}
    for frame in frames:
        year = int(frame["time"].dt.year.iloc[0])
        valid = frame.dropna(subset=["value"])
        if valid.empty:
            peaks[year] = (None, None)
            continue
        top = valid.loc[valid["value"].idxmax()]
        peaks[year] = (float(top["value"]), top["time"].strftime("%Y-%m-%d"))
    return peaks, cell, missing


def fetch_point_yearly_max(
    dataset: str,
    variable: str,
    lat: float,
    lon: float,
    start: int,
    end: int,
    months: tuple[int, int] = YEARLY_MAX_MONTHS,
    client: httpx.Client | None = None,
    cache_dir: Path | None = None,
) -> tuple[pd.Series, tuple[float, float]]:
    """Yearly maximum of a daily product over `months` (one value per year, indexed Jan 1).

    A year with no valid day is NaN, never 0. `series.attrs["temporal"] == "annual"`.
    """
    peaks, cell, missing = fetch_point_yearly_peaks(dataset, variable, lat, lon, start, end, months, client, cache_dir)
    values = {
        pd.Timestamp(year=year, month=1, day=1): (np.nan if value is None else value)
        for year, (value, _date) in peaks.items()
    }
    series = pd.Series(values, dtype=float).sort_index().rename(variable)
    series.index = pd.DatetimeIndex(series.index)
    series.attrs["cell"] = cell
    series.attrs["temporal"] = "annual"
    series.attrs["missing_years"] = missing
    return series, cell


# --------------------------------------------------------------------------- bathymetry


def fetch_min_elevation(
    bbox: tuple[float, float, float, float],
    client: httpx.Client | None = None,
    cache_dir: Path | None = None,
    stride: int = 4,
) -> float:
    """Lowest GEBCO_2020 elevation (m, negative below sea level) in bbox (west, south, east, north).

    Static data, so the answer is cached forever. Raises `ErddapError` if it cannot be read.
    A box wider than about 2° gets a larger stride, so one request stays under about
    GEBCO_MAX_SIDE x GEBCO_MAX_SIDE points.
    """
    text = _gebco_text(bbox, stride, client, cache_dir)
    return _min_elevation(text)


def _gebco_text(
    bbox: tuple[float, float, float, float], stride: int, client: httpx.Client | None, cache_dir: Path | None
) -> str:
    """The GEBCO_2020 CSV for bbox (west, south, east, north), cached forever once valid."""
    west, south, east, north = bbox
    side = max(abs(east - west), abs(north - south))
    stride = max(stride, math.ceil(side * GEBCO_CELLS_PER_DEGREE / GEBCO_MAX_SIDE))
    url = griddap_url("GEBCO_2020", "elevation", [_axis(south, north, stride), _axis(west, east, stride)])
    path = _cache_path(cache_dir_default if cache_dir is None else cache_dir, "GEBCO_2020", url)
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8")
            _min_elevation(text)
            return text
        except (ErddapError, OSError, UnicodeDecodeError):
            path.unlink(missing_ok=True)
    own = client is None
    client = client or new_client()
    try:
        text = _request(client, url)
    except _NoResults as exc:
        raise ErddapError("GEBCO has no data for this box") from exc
    finally:
        if own:
            client.close()
    _min_elevation(text)  # validate before caching
    try:
        _write_atomic(path, text)
    except OSError as exc:
        logger.warning("ERDDAP GEBCO: cache write failed: %s", exc)
    return text


def fetch_elevation_grid(
    bbox: tuple[float, float, float, float],
    stride: int = 2,
    client: httpx.Client | None = None,
    cache_dir: Path | None = None,
) -> xr.DataArray:
    """GEBCO_2020 elevation (m, negative below sea level) over bbox (west, south, east, north).

    Dims `latitude, longitude`, latitude ascending (south first, as ERDDAP answers); callers
    that draw it flip it to north -> south. Same cache and stride rules as `fetch_min_elevation`.
    """
    text = _gebco_text(bbox, stride, client, cache_dir)
    frame = pd.read_csv(StringIO(text), skiprows=[1])
    frame["elevation"] = pd.to_numeric(frame["elevation"], errors="coerce")
    grid = frame.groupby(["latitude", "longitude"])["elevation"].mean().to_xarray()
    return grid.rename("elevation").transpose("latitude", "longitude")


def _min_elevation(text: str) -> float:
    head = text.lstrip()[:200].lower()
    if head.startswith("<!doctype") or head.startswith("<html") or head.startswith("error"):
        raise ErddapError("ERDDAP answered with an error page instead of CSV")
    try:
        frame = pd.read_csv(StringIO(text), skiprows=[1])
        values = pd.to_numeric(frame["elevation"], errors="coerce").dropna()
    except Exception as exc:  # noqa: BLE001 - any unreadable body is a source failure
        raise ErddapError(f"unreadable GEBCO CSV: {exc}") from exc
    if values.empty:
        raise ErddapError("GEBCO CSV without elevation values")
    return float(values.min())


# --------------------------------------------------------------------------- grid


def fetch_grid(
    dataset: str,
    variable: str,
    bbox: tuple[float, float, float, float],
    start: int,
    end: int,
    stride: int,
    client: httpx.Client | None = None,
    cache_dir: Path | None = None,
) -> xr.DataArray:
    """Monthly grid over bbox (west, south, east, north), one request per year.

    Dims `time, latitude, longitude`; time at month start; latitude in the order ERDDAP
    returns it (ascending for MUR: south first); raw dataset units, NaN for masked cells.
    Failed years are gaps listed in `attrs["missing_years"]`.
    """
    west, south, east, north = bbox
    space = [_axis(south, north, stride), _axis(west, east, stride)]
    cache = cache_dir_default if cache_dir is None else cache_dir
    years = list(range(start, end + 1))
    failures = _YearFailures(dataset, years)
    own = client is None
    client = client or new_client()
    try:
        frames = []
        for year in years:
            try:
                frame = _year_frame(client, dataset, variable, space, year, (1, 12), cache)
            except ErddapError as exc:
                failures.add(year, exc)
                continue
            if frame is not None and not frame.empty:
                frames.append(frame)
    finally:
        if own:
            client.close()
    if not frames:
        raise ErddapError(f"ERDDAP {dataset} has no data in {start}-{end} for this box")
    data = pd.concat(frames)
    data = data.assign(time=data["time"].dt.to_period("M").dt.to_timestamp())
    cube = data.groupby(["time", "latitude", "longitude"])["value"].mean().to_xarray()
    out = cube.rename(variable).transpose("time", "latitude", "longitude")
    out.attrs["missing_years"] = failures.failed
    return out


def fetch_day_grid(
    dataset: str,
    variable: str,
    bbox: tuple[float, float, float, float],
    day: dt.date,
    stride: int = 1,
    client: httpx.Client | None = None,
    cache_dir: Path | None = None,
) -> xr.DataArray:
    """One day of a daily product (DHW at 12:00 UTC) over bbox (west, south, east, north).

    Dims `latitude, longitude`, latitude ascending, raw units, NaN for masked cells. Cached
    for past years only. Raises `ErddapError` when the day cannot be read or is not in the dataset.
    """
    west, south, east, north = bbox
    stamp = f"{day.isoformat()}T12:00:00Z"
    url = griddap_url(dataset, variable, [_axis(stamp), _axis(south, north, stride), _axis(west, east, stride)])
    cache = cache_dir_default if cache_dir is None else cache_dir
    own = client is None
    client = client or new_client()
    try:
        frame = _cached_frame(client, dataset, variable, url, day.year, cache)
    except _NoResults as exc:
        raise ErddapError(f"ERDDAP {dataset} has no data for {day}") from exc
    finally:
        if own:
            client.close()
    cube = frame.groupby(["latitude", "longitude"])["value"].mean().to_xarray()
    return cube.rename(variable).transpose("latitude", "longitude")
