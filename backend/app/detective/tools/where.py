"""`trend_map`: WHERE a variable changes around the place, as a per-pixel trend overlay.

Grid sources:
- ERDDAP monthly variables (sea temperature, chlorophyll): `erddap.fetch_grid`, one cached
  request per year; per pixel, annual means of deseasonalized monthly anomalies.
- GIBS yearly variables (NDVI, ground temperature, NO2, CO): `gibs_values.fetch_annual_grids`
  (the same `yearly_values` reading as the point series, cached per year).
Everything else answers "no gridded source for this variable".

Per pixel: Sen slope per decade and Mann-Kendall p on the yearly values (`assets/maps.sen_mk_grid`),
coloured with the site trend maps' rules (`style_for`, `colorize`); pixels with p >= 0.05 are
faded. Pixel significance is a picture, never corrected over the area and never a verdict.
The tool logs ONE trend test, on the median over the map area of each time step, on the
variable's own basis (monthly anomalies for ERDDAP, yearly values for GIBS), so it is never
mixed with the other basis. `share_significant` and `median_slope_per_decade` are computed here;
the answer may quote the share only as "share of the area with a clear trend".
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from typing import NamedTuple

import numpy as np
import pandas as pd

from app import gather
from app.assets import maps as site_maps
from app.assets.gibs_layers import layer_size
from app.catalog import Variable
from app.detective import maps
from app.detective.ledger import TestRecord
from app.detective.session import Session
from app.detective.tools import data
from app.extractors import erddap, gibs_values
from app.stats import annual as annual_stats
from app.stats.annual import annual_trend, n_years
from app.stats.deseason import monthly_anomalies
from app.stats.trend import trend_test as mk_trend_test

logger = logging.getLogger(__name__)

NO_GRID_REASON = "no gridded source for this variable"
SHARE_WORDING = "share of the area with a clear trend"
MAX_SIDE = 200  # pixels per side of one map request: keeps the request and the test grid small
MIN_RENDER_SIDE = 512  # the PNG is upscaled (nearest, whole factor) to at least this many pixels
MAX_RENDER_SIDE = 1024
# ERDDAP grid cells per degree of each dataset (for the stride that keeps a request <= MAX_SIDE).
ERDDAP_CELLS_PER_DEGREE = {"jplMURSST41mday": 100, "erdMH1chlamday_R2022SQ": 24}
DEFAULT_CELLS_PER_DEGREE = 24
ERDDAP_SOURCE_NAMES = {
    "jplMURSST41mday": "NASA JPL MUR sea surface temperature (GHRSST L4), via NOAA CoastWatch ERDDAP",
    "erdMH1chlamday_R2022SQ": "NASA MODIS Aqua chlorophyll-a (L3SMI, R2022), via NOAA CoastWatch ERDDAP",
}
NOTE = (
    "Faded pixels have no clear trend on their own (p >= 0.05, not corrected over the area); "
    f"quote share_significant only as the '{SHARE_WORDING}'. The verdict is the test on the "
    "median over the map area."
)

_not_available = data._not_available


def _num(x: float | None, ndigits: int = 4) -> float | None:
    return data._num(x, ndigits)


def has_grid(var: Variable) -> bool:
    if var.source == "erddap":
        return var.temporal != data.ANNUAL  # DHW is daily: a yearly peak grid is not set up
    if var.source == "gibs":
        try:
            gibs_values.layer_for(var)
        except gibs_values.GibsError:
            return False
        return True
    return False


# --------------------------------------------------------------------------- tool


def trend_map(session: Session, var_id: str) -> dict:
    args = {"var_id": var_id, "start": session.start, "end": session.end}
    return data._through_ledger(
        session, "trend_map", args, lambda: _safe(session, var_id), on_hit=lambda hit: _ensure_png(session, hit)
    )


def _ensure_png(session: Session, hit: dict) -> dict:
    """A cached map whose PNG is gone (cleaned up after MAX_AGE_DAYS): drawn again under the same
    name from the grid caches. No test is logged and no op added; a failure leaves the hit as is."""
    url = hit.get("url")
    if hit.get("status") != "ok" or not isinstance(url, str):
        return hit
    name = url.rsplit("/", 1)[-1]
    if not maps.NAME_RE.fullmatch(name) or (maps.maps_dir() / name).is_file():
        return hit
    try:
        var = data._variable(session, str(hit.get("var_id")))
        grid = _grid_for(var, session.start, session.end, tuple(float(c) for c in session.place.bbox)) if var else None
        picture = _picture(var, grid) if grid is not None else None
        if picture is not None:
            maps.write_png(picture.rgba, picture.size, name=name)
    except Exception as exc:  # noqa: BLE001 - the cached result still stands
        logger.warning("trend_map %s: redraw failed: %s: %s", hit.get("var_id"), type(exc).__name__, exc)
    return hit


def _safe(session: Session, var_id: str) -> dict:
    try:
        return _trend_map(session, var_id)
    except Exception as exc:  # noqa: BLE001 - never a stack trace to the model
        logger.warning("trend_map %s failed: %s: %s", var_id, type(exc).__name__, exc)
        return _not_available("the trend map could not be made", transient=True, var_id=var_id)


def _trend_map(session: Session, var_id: str) -> dict:
    var = data._variable(session, var_id)
    if var is None:
        return _not_available(f"unknown variable {var_id!r}; call list_variables", var_id=var_id)
    if not has_grid(var):
        return _not_available(NO_GRID_REASON, var_id=var_id)
    try:
        extra_ids = data._extra_driver_ids(session)
    except ValueError:
        return _not_available(data.UNKNOWN_CASE_REASON, var_id=var_id)
    reason = data._unavailable_reason(session, var, extra_ids)  # the same predicate as get_series
    if reason is not None:
        return _not_available(reason, var_id=var_id)
    start, end = session.start, session.end
    bbox = tuple(float(c) for c in session.place.bbox)
    if var.source == "gibs" and start > gibs_values.last_complete_year():
        return _not_available(data.NO_COMPLETED_YEAR_REASON, var_id=var_id)
    try:
        grid = _grid_for(var, start, end, bbox)
    except Exception as exc:  # noqa: BLE001 - a failing source is a result, not a crash
        logger.warning("trend_map %s: source failed: %s: %s", var_id, type(exc).__name__, exc)
        source = gather.SOURCES.get(var.source)
        return _not_available(source.failure if source else data.SOURCE_DOWN_REASON, transient=True, var_id=var_id)
    if grid is None or not np.isfinite(grid.annual).any():
        return _not_available(f"no data for {var.label} here in {start}-{end}", var_id=var_id)
    return _render(session, var, bbox, grid)


def _grid_for(var: Variable, start: int, end: int, bbox: tuple[float, ...]) -> _Grid | None:
    if var.source == "erddap":
        return _erddap_grid(var, bbox, start, end)
    return _gibs_grid(var, bbox, start, end)


# --------------------------------------------------------------------------- grids


class _Grid:
    """Yearly values per pixel (Y, ny, nx), rows north first, plus the area-median series."""

    def __init__(self, years: list[int], annual: np.ndarray, area: pd.Series, basis: str, attrs: dict):
        self.years = years
        self.annual = annual
        self.area = area  # monthly (ERDDAP) or yearly (GIBS) median over the pixels
        self.basis = basis
        self.attrs = attrs


def stride_for(bbox: Sequence[float], cells_per_degree: float, max_side: int = MAX_SIDE) -> int:
    west, south, east, north = bbox
    side = max(abs(east - west), abs(north - south)) * cells_per_degree
    return max(1, math.ceil(side / max_side))


def capped_size(size: tuple[int, int], max_side: int = MAX_SIDE) -> tuple[int, int]:
    width, height = size
    longest = max(width, height)
    if longest <= max_side:
        return width, height
    k = max_side / longest
    return max(1, round(width * k)), max(1, round(height * k))


def _step(coords: np.ndarray, fallback: float) -> float:
    diffs = np.abs(np.diff(np.sort(coords)))
    diffs = diffs[diffs > 0]
    return float(np.median(diffs)) if diffs.size else fallback


def cell_edges(lat: np.ndarray, lon: np.ndarray, fallback_step: float) -> list[float]:
    """[west, south, east, north] of the outer cell edges: centres min - step/2 ... max + step/2."""
    lat, lon = np.asarray(lat, dtype=float), np.asarray(lon, dtype=float)
    dy, dx = _step(lat, fallback_step), _step(lon, fallback_step)
    return [
        max(float(lon.min()) - dx / 2, -180.0),
        max(float(lat.min()) - dy / 2, -90.0),
        min(float(lon.max()) + dx / 2, 180.0),
        min(float(lat.max()) + dy / 2, 90.0),
    ]


def _area_median(cube: np.ndarray) -> np.ndarray:
    flat = cube.reshape(cube.shape[0], -1)
    out = np.full(cube.shape[0], np.nan)
    for k, row in enumerate(flat):
        finite = row[np.isfinite(row)]
        if finite.size:
            out[k] = float(np.median(finite))
    return out


def _erddap_grid(var: Variable, bbox: tuple[float, ...], start: int, end: int) -> _Grid | None:
    cells = ERDDAP_CELLS_PER_DEGREE.get(var.dataset, DEFAULT_CELLS_PER_DEGREE)
    stride = stride_for(bbox, cells)
    raw = erddap.fetch_grid(var.dataset, var.band, bbox, start, end, stride)
    cube = raw.sortby("latitude", ascending=False).sortby("longitude")
    values = cube.values.astype(float) * var.scale + var.offset
    if var.transform == "log10":
        with np.errstate(invalid="ignore", divide="ignore"):
            values = np.where(values > 0, np.log10(np.where(values > 0, values, 1.0)), np.nan)
    times = pd.DatetimeIndex(cube["time"].values).to_period("M").to_timestamp()
    keep = (times.year >= start) & (times.year <= end)  # chlorophyll runs past the study period
    times, values = times[keep], values[keep]
    if values.size == 0:
        return None
    years = list(range(start, end + 1))
    anomalies = site_maps.deseasonalize(times, values)
    annual = site_maps.annual_means(times, anomalies, years)
    area = gather.conform(pd.Series(_area_median(values), index=times, name=var.id), start, end)
    attrs = {
        "missing_years": [int(y) for y in raw.attrs.get("missing_years") or []],
        "stride": stride,
        "bounds": cell_edges(cube["latitude"].values, cube["longitude"].values, stride / cells),
    }
    return _Grid(years, annual, area, "monthly", attrs)


def _gibs_grid(var: Variable, bbox: tuple[float, ...], start: int, end: int) -> _Grid | None:
    layer = gibs_values.layer_for(var)
    size = capped_size(layer_size(bbox, layer))
    grids, attrs = gibs_values.fetch_annual_grids(layer, bbox, start, end, size)
    if not grids:
        return None
    years = list(range(min(grids), max(grids) + 1))
    shape = (size[1], size[0])
    empty = np.full(shape, np.nan)
    annual = np.stack([grids.get(y, empty) * var.scale + var.offset for y in years])
    area = pd.Series(_area_median(annual), index=pd.to_datetime([f"{y}-01-01" for y in years]), name=var.id)
    out = {"missing_years": [int(y) for y in attrs.get("missing_years") or []]}
    if attrs.get("dropped_years"):
        out["dropped_years"] = [int(y) for y in attrs["dropped_years"]]
    caveats = [attrs.get("caveat"), gibs_values.saturation_caveat(attrs, abs(var.scale), var.units)]
    caveat = " ".join(c for c in caveats if c)
    if caveat:
        out["caveat"] = caveat
    step = attrs.get("palette_step")
    if step is not None and np.isfinite(step):
        out["precision"] = f"palette step ≈ {step * abs(var.scale):.2g} {var.units}"
    out["suffix"] = gibs_values.annual_suffix(layer)
    out["source_name"] = layer.source.get("name")
    return _Grid(years, annual, area, data.ANNUAL, out)


# --------------------------------------------------------------------------- test, picture, result


def _area_test(session: Session, var: Variable, grid: _Grid) -> tuple[str, dict]:
    """The one counted test of a trend map: the area-median series on the variable's own basis."""
    if grid.basis == data.ANNUAL:
        suffix = grid.attrs.get("suffix") or "yearly values"
        base = var.label if suffix in var.label else f"{var.label} ({suffix})"
        res = annual_trend(grid.area)
        size = {"n_years": n_years(grid.area)}
    else:
        base = var.label
        res = mk_trend_test(monthly_anomalies(grid.area))
        size = {"n_months": res.n_months}
    slope = None if res.too_short else res.sen_slope_per_decade
    test_id = f"t{session.ledger.n_tests + 1}"
    session.ledger.add_test(
        TestRecord(
            id=test_id,
            var_id=var.id,
            label=f"{base}, median over the map area",
            kind="trend",
            p_value=res.p_value,
            slope=slope,
            too_short=res.too_short,
            result=res,
        )
    )
    corrected = data._corrected_fields(session, test_id)
    # Only the verdict travels at the top; the test's own numbers describe the area median,
    # not the two map findings, so they sit under the non-quotable `map` subtree.
    top = {
        "test_id": test_id,
        "basis": grid.basis,
        "too_short": res.too_short,
        "q_session": corrected["q_session"],
        "verdict": corrected["verdict"],
        "direction": corrected["direction"],
    }
    detail = {
        **size,
        "area_slope_per_decade": _num(slope),
        "ci_low": _num(res.ci_low),
        "ci_high": _num(res.ci_high),
        "p_value": _num(res.p_value),
        "n_tests_so_far": corrected["n_tests_so_far"],
    }
    return top, detail


def _render_size(ny: int, nx: int) -> tuple[int, int]:
    factor = max(1, math.ceil(MIN_RENDER_SIDE / max(ny, nx)))
    while factor > 1 and max(ny, nx) * factor > MAX_RENDER_SIDE:
        factor -= 1
    return nx * factor, ny * factor


class _Picture(NamedTuple):
    rgba: np.ndarray
    size: tuple[int, int]
    slope: np.ndarray
    significant: np.ndarray
    vmax: float


def _picture(var: Variable, grid: _Grid) -> _Picture | None:
    """Per-pixel Sen slope coloured like the site trend maps; None when no pixel has enough years."""
    slope, pval = site_maps.sen_mk_grid(grid.years, grid.annual, min_years=annual_stats.MIN_YEARS)
    if not np.isfinite(slope).any():
        return None
    style = site_maps.style_for(var)
    vmax = site_maps.symmetric_limit(slope)
    significant = np.isfinite(pval) & (pval < site_maps.SIG_LEVEL)
    alpha = np.where(significant, site_maps.ALPHA_SIGNIFICANT, site_maps.ALPHA_FADED).astype(np.uint8)
    rgba = site_maps.colorize(slope, vmax, style.colormap, alpha)
    return _Picture(rgba, _render_size(*slope.shape), slope, significant, vmax)


def _render(session: Session, var: Variable, bbox: tuple[float, ...], grid: _Grid) -> dict:
    picture = _picture(var, grid)
    if picture is None:
        return _not_available(f"fewer than {annual_stats.MIN_YEARS} years with data in any pixel here", var_id=var.id)
    slope, significant = picture.slope, picture.significant
    finite = np.isfinite(slope)
    name = maps.write_png(picture.rgba, picture.size)
    try:
        test, test_detail = _area_test(session, var, grid)
    except BaseException:
        (maps.maps_dir() / name).unlink(missing_ok=True)  # no map without its counted test
        raise
    url = maps.url_for(name)
    style = site_maps.style_for(var)
    unit = f"{var.units} per decade"
    legend = {
        "unit": unit,
        "labels": {
            "more": style.more,
            "less": style.less,
            "faded": f"Faded = not statistically significant (Mann-Kendall p ≥ {site_maps.SIG_LEVEL})",
            "transparent": "Transparent = not enough data",
        },
        "stops": site_maps.legend_stops(style.colormap),
        "range": [-site_maps.round_sig(picture.vmax), site_maps.round_sig(picture.vmax)],
    }
    have = [y for k, y in enumerate(grid.years) if np.isfinite(grid.annual[k]).any()]
    period = [have[0], have[-1]]
    bounds = list(grid.attrs.get("bounds") or bbox)  # ERDDAP: the cells' outer edges; GIBS: the box drawn
    source = grid.attrs.get("source_name") or ERDDAP_SOURCE_NAMES.get(var.dataset) or gather.SOURCES[var.source].title
    resolution = data.resolution_of(var)
    title = f"{var.label}: trend per pixel, {period[0]}–{period[1]}"
    session.map.append(
        {
            "op": "overlay",
            "url": url,
            "bounds": bounds,
            "legend": legend,
            "title": title,
            "source": source,
            "resolution": resolution,
            "period": period,
        }
    )
    words = {k: grid.attrs[k] for k in ("precision", "caveat") if grid.attrs.get(k)}
    details = {
        "bounds": bounds,
        "legend": legend,
        "years": period,
        "pixels": int(finite.sum()),
        "area_test": test_detail,
        **{k: grid.attrs[k] for k in ("missing_years", "dropped_years") if grid.attrs.get(k)},
    }
    # Only the two findings are quotable; everything else numeric sits under `map` (non-figure).
    return {
        "status": "ok",
        "var_id": var.id,
        "label": var.label,
        "url": url,
        "title": title,
        "source": source,
        "resolution": resolution,
        "unit": unit,
        "share_significant": _num(float(significant[finite].mean()), 3),
        "median_slope_per_decade": _num(float(np.median(slope[finite]))),
        **test,
        **words,
        "note": NOTE,
        "map": details,
    }
