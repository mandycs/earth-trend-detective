"""Yearly vegetation and ground-temperature layers for each site, read from NASA GIBS.

GIBS serves MODIS monthly products as coloured PNGs with a published colormap that maps
every colour to a value interval. We request the site box at about the product's own
resolution, turn colours back into values (interval midpoints: NDVI to 0.01, LST to about
0.6 K), average the season's months for each year and write:

- layers/<id>/<YYYY>.png         coloured on one fixed range for all years (comparable)
- layers/<id>/<YYYY>_values.png  16-bit values: value = offset + scale * pixel, 0 = no data
- layers/<id>/meta.json          legend, unit, range, months, scale/offset, source

These are measured values (status "observed"); the site layers are not trend-tested. The
detective reads the same values at any point (`yearly_values`, via `extractors/gibs_values`)
and tests them on the annual path. Pixels stay at their real size: no smoothing into detail
that is not there.

Usage (from backend/, venv active):
    python -m app.assets.gibs_layers [site_id ...]
"""

from __future__ import annotations

import io
import json
import logging
import re
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import httpx
import matplotlib
import numpy as np
from PIL import Image

from app.assets.composite import native_width
from app.assets.gibs import GIBS_WMS_URL
from app.assets.relief import pixel_size_m
from app.sites import load_sites

logger = logging.getLogger(__name__)

SITES_DIR = Path(__file__).resolve().parents[3] / "sites"
COLORMAP_URL = "https://gibs.earthdata.nasa.gov/colormaps/v1.3/{name}.xml"
YEARS = range(2003, 2025)
TIMEOUT_S = 60.0
MIN_PX = 64
MIN_VALID_SHARE = 0.2  # a year needs at least this share of pixels with a value, else it is dropped
MIN_SEEN_MONTHS = 6  # layers with `transparent_value`: months with a coloured pixel a year needs
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
RETRIES = 2  # extra tries after the first, on RETRY_STATUS or a network error
BACKOFF_S = 1.0
_sleep = time.sleep  # patched in tests
_ENTRY_RE = re.compile(r"<ColorMapEntry\s+([^>]*)/>")
_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')
_NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")  # also "1.06e+14" (OMI NO2)


@dataclass(frozen=True)
class GibsLayer:
    id: str
    title: str
    gibs_layer: str
    colormap: str
    native_m: float
    unit: str
    to_unit: float  # value in colormap units + to_unit -> display unit (K -> °C: -273.15)
    offset: float  # 16-bit encoding
    scale: float
    palette: str
    legend: Mapping[str, str]
    source: Mapping[str, str]
    seasons: Mapping[str, tuple[int, ...]]  # site id -> months averaged each year
    # Value of a transparent pixel when GIBS paints a real value transparent (snow: 0 % is
    # transparent); None = transparent means no data.
    transparent_value: float | None = None
    # Days of each month read: (1,) for a monthly layer; a daily layer is sampled on these days.
    days: tuple[int, ...] = (1,)
    # Pictures with a coloured pixel a year needs (0: MIN_SEEN_MONTHS with `transparent_value`, else none).
    min_seen: int = 0
    min_months: int = 0  # months with a seen picture a year needs
    first_year: int = 0  # first complete year of the product; earlier years are never asked
    caveat: str = ""  # said with every value read from this layer


LAYERS: tuple[GibsLayer, ...] = (
    GibsLayer(
        id="ndvi_gibs",
        title="Green vegetation (NDVI)",
        gibs_layer="MODIS_Terra_L3_NDVI_Monthly",
        colormap="MODIS_L3_NDVI",
        native_m=1000.0,
        unit="NDVI (0 = bare, 1 = dense green)",
        to_unit=0.0,
        offset=-1.0,
        scale=0.0001,
        palette="YlGn",
        legend={"more": "Greener", "less": "Barer", "transparent": "Transparent = no clear view that season"},
        source={"name": "MODIS Terra monthly NDVI (MOD13A3), via NASA GIBS", "url": "https://lpdaac.usgs.gov/products/mod13a3v061/"},
        seasons={"lake_mead": (3, 4), "aletsch": (7, 8), "donana": (3, 4)},
    ),
    GibsLayer(
        id="lst_gibs",
        title="Daytime ground temperature",
        gibs_layer="MODIS_Terra_L3_Land_Surface_Temp_Monthly_Day",
        colormap="MODIS_Land_Surface_Temp",
        native_m=5600.0,  # monthly LST on GIBS is the 0.05° climate-modelling grid
        unit="°C",
        to_unit=-273.15,
        offset=-100.0,
        scale=0.01,
        palette="inferno",
        legend={"more": "Hotter ground", "less": "Cooler ground", "transparent": "Transparent = no clear view that season"},
        source={"name": "MODIS Terra monthly land surface temperature (MOD11C3), via NASA GIBS", "url": "https://lpdaac.usgs.gov/products/mod11c3v061/"},
        seasons={"lake_mead": (6, 7, 8), "aletsch": (7, 8), "donana": (6, 7, 8)},
    ),
)


class ColorTable(dict):
    """rgb -> value, plus the open-ended bins: `top` colours ("[x,+INF)", read as x, a floor)
    and `bottom` colours ("[-INF,x)", read as x, a ceiling); `top_value` is x of the top bin."""

    top: frozenset = frozenset()
    bottom: frozenset = frozenset()
    top_value: float | None = None


def parse_colormap(xml: str) -> ColorTable:
    """rgb -> value (midpoint of the entry's interval); transparent / no-data entries left out.
    Open-ended bins are marked on the table (`top`, `bottom`)."""
    table = ColorTable()
    top: set = set()
    bottom: set = set()
    for raw in _ENTRY_RE.findall(xml):
        attrs = dict(_ATTR_RE.findall(raw))
        if attrs.get("transparent") == "true" or attrs.get("nodata") == "true" or "value" not in attrs:
            continue
        nums = [float(x) for x in _NUM_RE.findall(attrs["value"])]
        if not nums:
            continue
        mid = (nums[0] + nums[-1]) / 2 if len(nums) > 1 else nums[0]
        rgb = tuple(int(c) for c in attrs["rgb"].split(","))
        table[rgb] = mid  # type: ignore[index]
        if "+INF" in attrs["value"]:
            top.add(rgb)
            table.top_value = mid if table.top_value is None else min(table.top_value, mid)
        elif "-INF" in attrs["value"]:
            bottom.add(rgb)
    table.top, table.bottom = frozenset(top), frozenset(bottom)
    return table


def decode(rgba: np.ndarray, table: Mapping[tuple[int, int, int], float]) -> np.ndarray:
    """Values per pixel; NaN where transparent or the colour is not in the table."""
    flat = rgba.reshape(-1, rgba.shape[-1]).astype(np.int64)
    keys = (flat[:, 0] << 16) | (flat[:, 1] << 8) | flat[:, 2]
    lut = {(r << 16) | (g << 8) | b: v for (r, g, b), v in table.items()}
    out = np.array([lut.get(int(k), np.nan) for k in keys], dtype=np.float64)
    if rgba.shape[-1] == 4:
        out[flat[:, 3] == 0] = np.nan
    return out.reshape(rgba.shape[:2])


def season_mean(months: Sequence[np.ndarray]) -> np.ndarray:
    stack = np.stack(months)
    with np.errstate(all="ignore"):
        return np.nanmean(stack, axis=0) if np.isfinite(stack).any() else stack[0]


def encode_values(values: np.ndarray, offset: float, scale: float) -> np.ndarray:
    code = np.round((values - offset) / scale)
    code = np.where(np.isfinite(code), np.clip(code, 1, 65535), 0)
    return code.astype(np.uint16)


def colorize(values: np.ndarray, vmin: float, vmax: float, palette: str) -> np.ndarray:
    norm = np.clip((values - vmin) / (vmax - vmin), 0, 1)
    rgba = (matplotlib.colormaps[palette](np.nan_to_num(norm)) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(np.isfinite(values), 230, 0)
    return rgba


class TileFailed(RuntimeError):
    """GIBS did not answer a GetMap (5xx, 429 or a network error after the retries)."""


def _fetch(client: httpx.Client, layer: GibsLayer, bbox: Sequence[float], date: str, size: tuple[int, int]) -> np.ndarray | None:
    """The month's picture; None when GIBS answers but serves no picture for that date.

    A busy or failing server (RETRY_STATUS, network error) is retried RETRIES times with a
    short backoff, then `TileFailed` is raised: a failure is never read as "no clear view".
    """
    w, s, e, n = bbox
    params = {
        "SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": "1.3.0", "LAYERS": layer.gibs_layer,
        "CRS": "EPSG:4326", "BBOX": f"{s},{w},{n},{e}", "WIDTH": str(size[0]), "HEIGHT": str(size[1]),
        "FORMAT": "image/png", "TIME": date,
    }
    for attempt in range(RETRIES + 1):
        try:
            r = client.get(GIBS_WMS_URL, params=params)
        except httpx.HTTPError as exc:
            problem = type(exc).__name__
        else:
            if r.status_code not in RETRY_STATUS:
                break
            problem = f"HTTP {r.status_code}"
        if attempt == RETRIES:
            raise TileFailed(f"GIBS {layer.gibs_layer} {date}: {problem}")
        _sleep(BACKOFF_S * (attempt + 1))
    if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
        return None
    return np.asarray(Image.open(io.BytesIO(r.content)).convert("RGBA"))


def layer_size(bbox: Sequence[float], layer: GibsLayer) -> tuple[int, int]:
    """(width, height) in pixels: about the product's own resolution, metric aspect."""
    width = max(MIN_PX, native_width(bbox, layer.native_m))
    dx, dy = pixel_size_m(bbox, (1, 1))  # metric aspect, like the other overlays
    return width, max(1, round(width * dy / dx))


def load_colormap(client: httpx.Client, layer: GibsLayer) -> ColorTable:
    return parse_colormap(client.get(COLORMAP_URL.format(name=layer.colormap)).text)


def _seen(rgba: np.ndarray) -> bool:
    """At least one coloured (not transparent) pixel."""
    return rgba.shape[-1] < 4 or bool((rgba[..., 3] > 0).any())


def _count_colours(rgba: np.ndarray, colours: Iterable[tuple[int, int, int]]) -> int:
    """Coloured (not transparent) pixels drawn in one of `colours`."""
    if not colours:
        return 0
    flat = rgba.reshape(-1, rgba.shape[-1]).astype(np.int64)
    keys = (flat[:, 0] << 16) | (flat[:, 1] << 8) | flat[:, 2]
    hit = np.isin(keys, [(r << 16) | (g << 8) | b for r, g, b in colours])
    if rgba.shape[-1] == 4:
        hit &= flat[:, 3] > 0
    return int(hit.sum())


def _decode_tile(rgba: np.ndarray, table: Mapping[tuple[int, int, int], float], layer: GibsLayer) -> np.ndarray:
    vals = decode(rgba, table)
    if layer.transparent_value is not None and rgba.shape[-1] == 4:
        if not _seen(rgba):  # a wholly transparent box was not seen this month: missing, not 0
            return np.full(rgba.shape[:2], np.nan)
        vals = np.where(rgba[..., 3] == 0, layer.transparent_value, vals)
    return vals + layer.to_unit


def yearly_values(
    layer: GibsLayer,
    bbox: Sequence[float],
    years: Iterable[int],
    client: httpx.Client,
    months: Sequence[int],
    size: tuple[int, int] | None = None,
    table: Mapping[tuple[int, int, int], float] | None = None,
    workers: int = 1,
    failed: set[int] | None = None,
    saturated: dict[int, float] | None = None,
) -> dict[int, np.ndarray]:
    """Season mean grid (display units) per year over `bbox`, for the years with enough pixels.

    One GetMap per month (per sampled day, `layer.days`, for a daily layer); a date GIBS does
    not serve is skipped. A year keeps its grid when at least MIN_VALID_SHARE of the pixels
    have a value (transparent years are dropped) and it has `layer.min_seen` pictures with a
    coloured pixel. With `layer.transparent_value` set, a wholly transparent month is missing
    and a year needs MIN_SEEN_MONTHS seen months. A date GIBS failed on (`TileFailed`) is
    skipped and its year added to `failed` when given; a caller that cannot accept partial
    years leaves them out.

    A daily layer (several `layer.days`) averages each month's seen days first, then the
    months, so a cloudy season weighs as much as a clear one; a year needs `layer.min_months`
    months with a seen day. When `saturated` is given it gets, per year, the share of seen
    pixels drawn in the colormap's open top bin (a value at or above the top of the scale).
    """
    size = layer_size(bbox, layer) if size is None else size
    table = load_colormap(client, layer) if table is None else table
    jobs = [(year, m, d) for year in years for m in months for d in layer.days]
    need_seen = layer.min_seen or (MIN_SEEN_MONTHS if layer.transparent_value is not None else 0)

    def get(job: tuple[int, int, int]) -> np.ndarray | None:
        year, m, d = job
        try:
            return _fetch(client, layer, bbox, f"{year}-{m:02d}-{d:02d}", size)
        except TileFailed as exc:
            logger.warning("%s", exc)
            if failed is not None:
                failed.add(year)
            return None

    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            tiles = list(pool.map(get, jobs))
    else:
        tiles = [get(job) for job in jobs]
    by_month: dict[int, dict[int, list[np.ndarray]]] = {}
    seen: dict[int, int] = {}
    seen_months: dict[int, set[int]] = {}
    coloured: dict[int, int] = {}
    on_top: dict[int, int] = {}
    top = getattr(table, "top", frozenset())
    for (year, m, _), rgba in zip(jobs, tiles):
        if rgba is None:
            continue
        if _seen(rgba):
            seen[year] = seen.get(year, 0) + 1
            seen_months.setdefault(year, set()).add(m)
        coloured[year] = coloured.get(year, 0) + (int((rgba[..., 3] > 0).sum()) if rgba.shape[-1] == 4 else rgba[..., 0].size)
        on_top[year] = on_top.get(year, 0) + _count_colours(rgba, top)
        by_month.setdefault(year, {}).setdefault(m, []).append(_decode_tile(rgba, table, layer))
    if saturated is not None:
        saturated.update({y: on_top[y] / coloured[y] for y in coloured if coloured[y]})
    yearly: dict[int, np.ndarray] = {}
    for year, months_grids in by_month.items():
        if seen.get(year, 0) < need_seen or len(seen_months.get(year, ())) < layer.min_months:
            continue  # too few pictures seen to stand for the whole year
        if len(layer.days) > 1:  # each month weighs the same, however many of its days were seen
            vals = season_mean([season_mean(g) for g in months_grids.values()])
        else:
            vals = season_mean([g for grids in months_grids.values() for g in grids])
        if np.isfinite(vals).mean() >= MIN_VALID_SHARE:
            yearly[year] = vals
    return yearly


def build_layer(site_id: str, layer: GibsLayer, sites_dir: Path = SITES_DIR) -> dict | None:
    site = load_sites().get(site_id)
    months = layer.seasons.get(site_id)
    if site is None or months is None:
        return None
    out = sites_dir / site_id / "layers" / layer.id
    out.mkdir(parents=True, exist_ok=True)
    width, height = layer_size(site.bbox, layer)
    with httpx.Client(timeout=TIMEOUT_S) as client:
        failed: set[int] = set()
        yearly = yearly_values(layer, site.bbox, YEARS, client, months, size=(width, height), failed=failed)
    # A year with a month GIBS failed on would be partial: left out and listed as missing.
    yearly = {year: vals for year, vals in yearly.items() if year not in failed}
    if not yearly:
        logger.warning("%s/%s: no usable months", site_id, layer.id)
        return None
    every = np.concatenate([v[np.isfinite(v)] for v in yearly.values()])
    vmin, vmax = (round(float(x), 3) for x in np.percentile(every, [2, 98]))
    for year, vals in yearly.items():
        Image.fromarray(colorize(vals, vmin, vmax, layer.palette)).save(out / f"{year}.png")
        Image.fromarray(encode_values(vals, layer.offset, layer.scale)).save(out / f"{year}_values.png")
    stops = [matplotlib.colors.to_hex(matplotlib.colormaps[layer.palette](t)) for t in np.linspace(0, 1, 9)]
    meta = {
        "id": layer.id,
        "title": layer.title,
        "unit": layer.unit,
        "range": [vmin, vmax],
        "stops": stops,
        "legend": dict(layer.legend),
        "months": list(months),
        "years": sorted(yearly),
        "size_px": [width, height],
        "pixel_m": layer.native_m,
        "value_scale": layer.scale,
        "value_offset": layer.offset,
        "file_pattern": f"layers/{layer.id}/{{YYYY}}.png",
        "value_pattern": f"layers/{layer.id}/{{YYYY}}_values.png",
        "method": (
            f"Mean of months {', '.join(str(m) for m in months)} of each year; values read back from the "
            "NASA GIBS colormap (interval midpoints)."
        ),
        "source": dict(layer.source),
    }
    if failed:  # only when something failed, so a clean run writes the same file as before
        meta["missing_years"] = sorted(failed)
    (out / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("%s/%s: %d years, %dx%d px, range %s %s", site_id, layer.id, len(yearly), width, height, meta["range"], layer.unit)
    return meta


def main(argv: Sequence[str]) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    for site_id in argv or [s.id for s in load_sites().sites]:
        for layer in LAYERS:
            build_layer(site_id, layer)


if __name__ == "__main__":
    main(sys.argv[1:])
