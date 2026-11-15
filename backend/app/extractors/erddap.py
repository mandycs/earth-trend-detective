"""Sea data from NOAA CoastWatch ERDDAP griddap (no auth): point series and small grids.

Access facts (tested live, 2026-11-15): brackets in the query must be URL-encoded
(%5B/%5D) or the answer is empty; long time ranges answer 502/503, so every request
covers one year and requests run one after another (parallel calls get 408). A year
outside the dataset's time axis answers 404 "no matching results": that year is a gap,
not a failure. Any other error, or an HTML page instead of CSV, raises `ErddapError`.

Datasets: MUR SST `jplMURSST41mday` and MODIS Aqua chlorophyll `erdMH1chlamday_R2022SQ`
on the CoastWatch West Coast node; NOAA Coral Reef Watch degree heating weeks
`noaacrwdhwDaily` on the CoastWatch central node.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Sequence
from io import StringIO

import httpx
import numpy as np
import pandas as pd
import xarray as xr

logger = logging.getLogger(__name__)

ERDDAP_BASE = "https://coastwatch.pfeg.noaa.gov/erddap/griddap"
DATASET_BASES = {"noaacrwdhwDaily": "https://coastwatch.noaa.gov/erddap/griddap"}
TIMEOUT_S = 120.0
RETRY_STATUS = frozenset({408, 502, 503, 504})
RETRIES = 3
PAUSE_S = 5.0
MAX_CELL_OFFSET = 0.1  # degrees: how far a masked coastal cell may move to a valid one
YEARLY_MAX_MONTHS = (1, 6)  # DHW: January to June (a whole year in one call answers 502)
NO_RESULTS = "Your query produced no matching results"

_sleep = time.sleep  # patched in tests


class ErddapError(RuntimeError):
    """ERDDAP answered with an error, an HTML page, or not at all."""


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


def _time_axis(year: int, months: tuple[int, int]) -> str:
    first, last = _window(year, months)
    return _axis(first.strftime("%Y-%m-%dT%H:%M:%SZ"), last.strftime("%Y-%m-%dT%H:%M:%SZ"))


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


def _get(client: httpx.Client, url: str, variable: str) -> pd.DataFrame | None:
    """One request with retries on a busy server; None when the query matches no data."""
    for attempt in range(1, RETRIES + 1):
        try:
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
            return None
        if response.status_code != 200:
            raise ErddapError(f"ERDDAP HTTP {response.status_code}")
        return parse_csv(response.text, variable)
    raise ErddapError("ERDDAP did not answer")  # pragma: no cover - loop always returns or raises


# --------------------------------------------------------------------------- point series


def _point_year(
    client: httpx.Client, dataset: str, variable: str, cell: tuple[float, float], year: int, months: tuple[int, int]
) -> pd.DataFrame | None:
    url = griddap_url(dataset, variable, [_time_axis(year, months), _axis(cell[0]), _axis(cell[1])])
    frame = _get(client, url, variable)
    if frame is None:
        return None
    first, last = _window(year, months)
    # ERDDAP snaps each bound to the nearest stamp, which can fall in the next year
    return frame[(frame["time"] >= first) & (frame["time"] <= last)]


def _nearest_valid_cell(
    client: httpx.Client, dataset: str, variable: str, lat: float, lon: float, year: int, months: tuple[int, int]
) -> tuple[float, float] | None:
    """The valid cell nearest to (lat, lon) within MAX_CELL_OFFSET, over one year of data.

    Cells need at least half as many valid values as the best cell in the box, so a
    mostly-land cell with one stray value is not picked over a sea cell.
    """
    d = MAX_CELL_OFFSET
    url = griddap_url(
        dataset,
        variable,
        [_time_axis(year, months), _axis(round(lat - d, 6), round(lat + d, 6)), _axis(round(lon - d, 6), round(lon + d, 6))],
    )
    frame = _get(client, url, variable)
    if frame is None or frame.empty:
        return None
    counts = frame.groupby(["latitude", "longitude"])["value"].count()
    counts = counts[counts > 0]
    if counts.empty:
        return None
    good = counts[counts >= counts.max() / 2]
    ranked = sorted(
        good.index,
        key=lambda c: (math.dist(c, (lat, lon)), -int(good[c]), c),
    )
    best = ranked[0]
    if math.dist(best, (lat, lon)) > d + 1e-9:
        return None
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
) -> tuple[list[pd.DataFrame], tuple[float, float]]:
    own = client is None
    client = client or new_client()
    try:
        cell = (float(lat), float(lon))
        probed = False
        frames: list[pd.DataFrame] = []
        for year in range(start, end + 1):  # one year per call, sequentially
            frame = _point_year(client, dataset, variable, cell, year, months)
            if frame is None or frame.empty:
                continue
            if not probed:
                probed = True
                if frame["value"].notna().sum() == 0:
                    moved = _nearest_valid_cell(client, dataset, variable, lat, lon, year, months)
                    if moved is not None:
                        logger.info("ERDDAP %s: cell %s masked, using %s", dataset, cell, moved)
                        cell = moved
                        frame = _point_year(client, dataset, variable, cell, year, months)
                        if frame is None:
                            continue
            if frame["value"].notna().any():
                rows = frame[["latitude", "longitude"]].iloc[0]
                cell = (float(rows["latitude"]), float(rows["longitude"]))  # the grid cell ERDDAP used
            frames.append(frame)
        return frames, cell
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
) -> tuple[pd.Series, tuple[float, float]]:
    """Monthly series at the grid cell nearest (lat, lon), indexed by month start.

    A cell masked for the whole first year (coast seen as land) moves to the nearest valid
    cell within 0.1°. Returns the series (raw dataset units, NaN gaps) and the cell used,
    also stored in `series.attrs["cell"]`.
    """
    frames, cell = _point_frames(dataset, variable, lat, lon, start, end, (1, 12), client)
    if frames:
        data = pd.concat(frames)
        months = data["time"].dt.to_period("M").dt.to_timestamp()
        series = data["value"].groupby(months.to_numpy()).mean()
    else:
        series = pd.Series(dtype=float)
    series.index = pd.DatetimeIndex(series.index)
    series = series.sort_index().astype(float).rename(variable)
    series.attrs["cell"] = cell
    return series, cell


def fetch_point_yearly_max(
    dataset: str,
    variable: str,
    lat: float,
    lon: float,
    start: int,
    end: int,
    months: tuple[int, int] = YEARLY_MAX_MONTHS,
    client: httpx.Client | None = None,
) -> tuple[pd.Series, tuple[float, float]]:
    """Yearly maximum of a daily product over `months` (one value per year, indexed Jan 1).

    A year with no valid day is NaN, never 0. `series.attrs["temporal"] == "annual"`.
    """
    frames, cell = _point_frames(dataset, variable, lat, lon, start, end, months, client)
    values: dict[pd.Timestamp, float] = {}
    for frame in frames:
        year = int(frame["time"].dt.year.iloc[0])
        peak = frame["value"].max(skipna=True)
        values[pd.Timestamp(year=year, month=1, day=1)] = float(peak) if np.isfinite(peak) else np.nan
    series = pd.Series(values, dtype=float).sort_index().rename(variable)
    series.index = pd.DatetimeIndex(series.index)
    series.attrs["cell"] = cell
    series.attrs["temporal"] = "annual"
    return series, cell


# --------------------------------------------------------------------------- grid


def fetch_grid(
    dataset: str,
    variable: str,
    bbox: tuple[float, float, float, float],
    start: int,
    end: int,
    stride: int,
    client: httpx.Client | None = None,
) -> xr.DataArray:
    """Monthly grid over bbox (west, south, east, north), one request per year.

    Dims `time, latitude, longitude`; time at month start; latitude in the order ERDDAP
    returns it (ascending for MUR: south first); raw dataset units, NaN for masked cells.
    """
    west, south, east, north = bbox
    own = client is None
    client = client or new_client()
    try:
        frames = []
        for year in range(start, end + 1):
            url = griddap_url(
                dataset,
                variable,
                [_time_axis(year, (1, 12)), _axis(south, north, stride), _axis(west, east, stride)],
            )
            frame = _get(client, url, variable)
            if frame is None:
                continue
            first, last = _window(year, (1, 12))
            frames.append(frame[(frame["time"] >= first) & (frame["time"] <= last)])
    finally:
        if own:
            client.close()
    if not frames:
        raise ErddapError(f"ERDDAP {dataset} has no data in {start}-{end} for this box")
    data = pd.concat(frames)
    data = data.assign(time=data["time"].dt.to_period("M").dt.to_timestamp())
    cube = data.groupby(["time", "latitude", "longitude"])["value"].mean().to_xarray()
    return cube.rename(variable).transpose("time", "latitude", "longitude")
