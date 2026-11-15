"""Yearly values at any point from NASA GIBS layers (no auth): the `gibs` source.

GIBS serves MODIS monthly NDVI, land surface temperature and snow cover, AIRS monthly carbon
monoxide and OMI daily nitrogen dioxide as coloured PNGs with a published colormap. For the
place's box we read every month of each year (a daily layer: 4 sampled days a month, OMI NO2
has no monthly layer on GIBS) at the product's own resolution
(`assets/gibs_layers.yearly_values`), turn colours back into values (interval midpoints),
average the pictures of the year, and keep the box mean: one value per year, for the annual
trend path. Precision is one palette step (`attrs["palette_step"]`).

A year whose pictures are transparent (no clear view) is dropped and listed in
`attrs["dropped_years"]`; a year with a request GIBS failed on (after retries) is a gap in
`attrs["missing_years"]` instead. The unfinished current year is never asked. Completed years
are cached on disk (`data/cache/gibs_values/<layer>/<hash>.json`, written atomically) except
years with a failure. If nothing usable comes back, `GibsError` is raised.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from app.assets.gibs_layers import LAYERS, GibsLayer, load_colormap, yearly_values
from app.catalog import Variable

logger = logging.getLogger(__name__)

TIMEOUT_S = 30.0
WORKERS = 4  # parallel GetMap requests
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "gibs_values"
cache_dir_default: Path = DEFAULT_CACHE_DIR  # patched in tests
YEAR_MONTHS = tuple(range(1, 13))  # every month: the yearly mean, no season picked per climate
SNOW_CAVEAT = (
    "Months the satellite could not see (cloud, polar night) are left out; "
    "a decrease can still come from fewer clear months."
)

SNOW_LAYER = GibsLayer(
    id="snow_gibs",
    title="Snow cover",
    gibs_layer="MODIS_Terra_L3_Snow_Cover_Monthly_Average_Pct",
    colormap="MODIS_NDSI_Snow_Cover",
    native_m=5600.0,  # MOD10CM: 0.05° climate-modelling grid
    unit="%",
    to_unit=0.0,
    offset=0.0,
    scale=0.01,
    palette="Blues",
    legend={"more": "More snow", "less": "Less snow", "transparent": "Transparent = no snow or no clear view"},
    source={"name": "MODIS Terra monthly snow cover (MOD10CM), via NASA GIBS", "url": "https://nsidc.org/data/mod10cm"},
    seasons={},
    transparent_value=0.0,
)
OMI_CAVEAT = "OMI has a known sensor defect since 2007 (row anomaly); gaps are filled by neighbouring rows."
NO2_DAYS = (1, 9, 17, 25)  # OMI NO2 is daily on GIBS: 4 days a month, every 8 days or so
NO2_LAYER = GibsLayer(
    id="no2_omi",
    title="Nitrogen dioxide in the lower air",
    gibs_layer="OMI_Nitrogen_Dioxide_Tropo_Column",  # OMNO2d v004, 0.25°, cloud-screened
    colormap="OMI_Nitrogen_Dioxide_Tropo_Column",
    native_m=27800.0,  # 0.25° grid
    unit="molecules/cm²",
    to_unit=0.0,
    offset=0.0,
    scale=1.0e13,
    palette="YlOrRd",
    legend={"more": "More nitrogen dioxide", "less": "Less", "transparent": "Transparent = no clear view that day"},
    source={"name": "NASA OMI/Aura daily NO2 (OMNO2d), via NASA GIBS", "url": "https://disc.gsfc.nasa.gov/datasets/OMNO2d_004/summary"},
    seasons={},
    days=NO2_DAYS,
    min_months=10,  # months with a seen day; each month weighs the same in the year
    first_year=2005,  # OMI data start in October 2004
    caveat=OMI_CAVEAT,
)
CO_LAYER = GibsLayer(
    id="co_airs",
    title="Carbon monoxide at 500 hPa",
    gibs_layer="AIRS_L3_Carbon_Monoxide_500hPa_Volume_Mixing_Ratio_Monthly_Day",  # AIRS3STM v006, 1°
    colormap="AIRS_Carbon_Monoxide_Volume_Mixing_Ratio",
    native_m=111000.0,  # 1° grid
    unit="ppbv",
    to_unit=0.0,
    offset=0.0,
    scale=0.01,
    palette="Purples",
    legend={"more": "More carbon monoxide", "less": "Less", "transparent": "Transparent = no data that month"},
    source={"name": "NASA AIRS/Aqua monthly carbon monoxide (AIRS3STM), via NASA GIBS", "url": "https://disc.gsfc.nasa.gov/datasets/AIRS3STM_006/summary"},
    seasons={},
    min_seen=12,  # every month: carbon monoxide has a strong season, a missing month tilts the year
    first_year=2003,  # AIRS data start in September 2002
)
POINT_LAYERS: tuple[GibsLayer, ...] = (*LAYERS, SNOW_LAYER, NO2_LAYER, CO_LAYER)
MONTHLY_SUFFIX = "annual mean of monthly values"
SATURATED_LIMIT = 0.01  # a year with more seen pixels than this on the open top bin: say so
SATURATION_CAVEAT = "Some days exceed the colour scale (≥ {top} {unit}); yearly values and the trend are understated."


class GibsError(RuntimeError):
    """GIBS gave no usable picture for this box."""


def _this_year() -> int:
    return dt.date.today().year


def layer_for(var: Variable) -> GibsLayer:
    """The GIBS layer a catalog variable reads (`dataset` = GIBS layer name)."""
    for layer in POINT_LAYERS:
        if layer.gibs_layer == var.dataset:
            return layer
    raise GibsError(f"no GIBS layer {var.dataset!r} set up")


def annual_suffix(layer: GibsLayer) -> str:
    """What one yearly value of this layer is, in words for the user."""
    if layer.days == (1,):
        return MONTHLY_SUFFIX
    return f"annual mean of daily values on {len(layer.days)} days a month, each month weighted equally"


def saturation_caveat(attrs: dict, scale: float, unit: str) -> str | None:
    """The caveat when any year has more than SATURATED_LIMIT of its seen pixels on the top bin
    (read as the top of the scale, so the value is a floor); `scale` turns it into `unit`."""
    shares = attrs.get("saturated_share") or {}
    top = attrs.get("scale_top")
    if top is None or not any(share > SATURATED_LIMIT for share in shares.values()):
        return None
    return SATURATION_CAVEAT.format(top=f"{top * scale:.3g}", unit=unit)


def palette_step(table: dict[tuple[int, int, int], float]) -> float:
    """Typical distance between neighbouring colormap values: the precision of a decoded value."""
    values = np.unique(np.round(np.array(sorted(table.values()), dtype=float), 9))
    if values.size < 2:
        return float("nan")
    return float(np.median(np.diff(values)))


def last_complete_year() -> int:
    return _this_year() - 1


def _cache_path(cache_dir: Path, layer: GibsLayer, bbox: Sequence[float], year: int) -> Path:
    parts: list = [layer.gibs_layer, [round(float(c), 6) for c in bbox], list(YEAR_MONTHS), year]
    if layer.days != (1,):  # monthly layers keep the keys they were cached under
        parts += [list(layer.days), "months-weighted-equally"]
    key = json.dumps(parts)
    return cache_dir / layer.id / f"{hashlib.sha256(key.encode()).hexdigest()[:20]}.json"


def _read_cache(path: Path) -> dict | None:
    """The cached year ({"mean": float | None, "palette_step": float}); a corrupt file is deleted."""
    if not path.exists():
        return None
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
        mean, step = entry["mean"], float(entry["palette_step"])
        out = {"mean": None if mean is None else float(mean), "palette_step": step}
        if entry.get("saturated_share") is not None:  # older entries predate the count
            out["saturated_share"] = float(entry["saturated_share"])
        if entry.get("scale_top") is not None:
            out["scale_top"] = float(entry["scale_top"])
        return out
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.warning("GIBS cache %s unreadable (%s), fetching again", path.name, exc)
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


def fetch_annual(
    layer: GibsLayer,
    bbox: Sequence[float],
    start: int,
    end: int,
    client: httpx.Client | None = None,
    cache_dir: Path | None = None,
) -> pd.Series:
    """Box mean of the yearly mean, one value per kept year, indexed on Jan 1 (display units).

    Completed years only (an empty series when none is in range). Each year is cached on
    disk, also a year GIBS showed no clear picture for; a year with a failed request is a gap
    in `attrs["missing_years"]` and never cached.
    """
    cache = cache_dir_default if cache_dir is None else cache_dir
    years = list(range(max(start, layer.first_year), min(end, last_complete_year()) + 1))
    entries: dict[int, dict] = {}
    paths = {y: _cache_path(cache, layer, bbox, y) for y in years}
    for year in years:
        hit = _read_cache(paths[year])
        if hit is not None:
            entries[year] = hit
    todo = [y for y in years if y not in entries]
    failed: set[int] = set()
    if todo:
        own = client is None
        client = client or httpx.Client(timeout=TIMEOUT_S)
        try:
            try:
                table = load_colormap(client, layer)
            except httpx.HTTPError as exc:
                raise GibsError(f"GIBS colormap {layer.colormap!r}: {type(exc).__name__}") from exc
            if not table:
                raise GibsError(f"GIBS colormap {layer.colormap!r} unreadable")
            saturated: dict[int, float] = {}
            grids = yearly_values(
                layer, bbox, todo, client, YEAR_MONTHS, table=table, workers=WORKERS, failed=failed, saturated=saturated
            )
        finally:
            if own:
                client.close()
        step = palette_step(table)
        for year in todo:
            if year in failed:
                continue  # partial: a gap, and asked again next time
            with np.errstate(all="ignore"):
                mean = float(np.nanmean(grids[year])) if year in grids else None
            entries[year] = {"mean": mean, "palette_step": step, "saturated_share": saturated.get(year, 0.0)}
            if getattr(table, "top_value", None) is not None:
                entries[year]["scale_top"] = table.top_value
            if year < _this_year():
                try:
                    _write_atomic(paths[year], json.dumps(entries[year]))
                except OSError as exc:  # a cache that cannot be written must not lose the data
                    logger.warning("GIBS cache write failed: %s", exc)
    kept = [y for y in years if y in entries and entries[y]["mean"] is not None]
    if years and not kept:
        why = "requests failed" if failed else "no usable picture for this box"
        raise GibsError(f"GIBS {layer.gibs_layer}: {why} in {start}-{end}")
    series = pd.Series(
        [entries[y]["mean"] for y in kept], index=pd.to_datetime([f"{y}-01-01" for y in kept]), dtype=float, name=layer.id
    )
    steps = [entries[y]["palette_step"] for y in entries]
    series.attrs = {
        "temporal": "annual",
        "palette_step": steps[0] if steps else float("nan"),
        "months": list(YEAR_MONTHS),
        "dropped_years": [y for y in years if y in entries and entries[y]["mean"] is None],
        "missing_years": sorted(failed),
    }
    shares = {y: entries[y]["saturated_share"] for y in kept if "saturated_share" in entries[y]}
    if shares:
        series.attrs["saturated_share"] = shares
    tops = [entries[y]["scale_top"] for y in entries if "scale_top" in entries[y]]
    if tops:
        series.attrs["scale_top"] = tops[0]
    if layer.days != (1,):
        series.attrs["days"] = list(layer.days)
    if layer.caveat:
        series.attrs["caveat"] = layer.caveat
    elif layer.transparent_value is not None:
        series.attrs["caveat"] = SNOW_CAVEAT
    return series


# --------------------------------------------------------------------------- yearly grids (trend maps)

GRID_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "gibs_grids"
grid_cache_dir_default: Path = GRID_CACHE_DIR  # patched in tests


def _grid_cache_path(cache_dir: Path, layer: GibsLayer, bbox: Sequence[float], size: tuple[int, int], year: int) -> Path:
    parts: list = [layer.gibs_layer, [round(float(c), 6) for c in bbox], list(size), list(YEAR_MONTHS), list(layer.days), year]
    key = json.dumps(parts)
    return cache_dir / layer.id / f"{hashlib.sha256(key.encode()).hexdigest()[:20]}.npz"


def _read_grid(path: Path, size: tuple[int, int]) -> dict | None:
    """The cached year ({"grid": array | None, "palette_step", "saturated_share", "scale_top"});
    a corrupt or wrongly shaped file is deleted."""
    if not path.exists():
        return None
    try:
        with np.load(path, allow_pickle=False) as npz:
            has = bool(npz["has_grid"])
            grid = np.array(npz["grid"], dtype=float) if has else None
            out = {"grid": grid, "palette_step": float(npz["palette_step"]), "saturated_share": float(npz["saturated_share"])}
            top = float(npz["scale_top"])
        if grid is not None and grid.shape != (size[1], size[0]):
            raise ValueError(f"shape {grid.shape} != {size[1]}x{size[0]}")
        if np.isfinite(top):
            out["scale_top"] = top
        return out
    except (OSError, ValueError, KeyError, TypeError, EOFError) as exc:
        logger.warning("GIBS grid cache %s unreadable (%s), fetching again", path.name, exc)
        path.unlink(missing_ok=True)
        return None


def _write_grid(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    grid = entry["grid"]
    try:
        with os.fdopen(fd, "wb") as fh:
            np.savez_compressed(
                fh,
                has_grid=np.array(grid is not None),
                grid=np.zeros((0, 0)) if grid is None else grid.astype(np.float32),
                palette_step=np.array(entry["palette_step"]),
                saturated_share=np.array(entry["saturated_share"]),
                scale_top=np.array(entry.get("scale_top", float("nan"))),
            )
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def fetch_annual_grids(
    layer: GibsLayer,
    bbox: Sequence[float],
    start: int,
    end: int,
    size: tuple[int, int],
    client: httpx.Client | None = None,
    cache_dir: Path | None = None,
) -> tuple[dict[int, np.ndarray], dict]:
    """Yearly mean grid (display units, rows north first, shape (height, width)) per kept year.

    Same years, rules and failures as `fetch_annual`, but the whole grid is kept: each completed
    year is cached on disk (`data/cache/gibs_grids/`, atomic), also a year with no clear picture;
    a year with a failed request is a gap in `attrs["missing_years"]` and never cached. Raises
    `GibsError` when nothing usable comes back.
    """
    cache = grid_cache_dir_default if cache_dir is None else cache_dir
    years = list(range(max(start, layer.first_year), min(end, last_complete_year()) + 1))
    paths = {y: _grid_cache_path(cache, layer, bbox, size, y) for y in years}
    entries: dict[int, dict] = {}
    for year in years:
        hit = _read_grid(paths[year], size)
        if hit is not None:
            entries[year] = hit
    todo = [y for y in years if y not in entries]
    failed: set[int] = set()
    if todo:
        own = client is None
        client = client or httpx.Client(timeout=TIMEOUT_S)
        try:
            try:
                table = load_colormap(client, layer)
            except httpx.HTTPError as exc:
                raise GibsError(f"GIBS colormap {layer.colormap!r}: {type(exc).__name__}") from exc
            if not table:
                raise GibsError(f"GIBS colormap {layer.colormap!r} unreadable")
            saturated: dict[int, float] = {}
            grids = yearly_values(
                layer, bbox, todo, client, YEAR_MONTHS, size=size, table=table, workers=WORKERS,
                failed=failed, saturated=saturated,
            )
        finally:
            if own:
                client.close()
        step = palette_step(table)
        for year in todo:
            if year in failed:
                continue  # partial: a gap, and asked again next time
            entries[year] = {"grid": grids.get(year), "palette_step": step, "saturated_share": saturated.get(year, 0.0)}
            if getattr(table, "top_value", None) is not None:
                entries[year]["scale_top"] = float(table.top_value)
            if year < _this_year():
                try:
                    _write_grid(paths[year], entries[year])
                except OSError as exc:  # a cache that cannot be written must not lose the data
                    logger.warning("GIBS grid cache write failed: %s", exc)
    kept = {y: entries[y]["grid"] for y in years if y in entries and entries[y]["grid"] is not None}
    if years and not kept:
        why = "requests failed" if failed else "no usable picture for this box"
        raise GibsError(f"GIBS {layer.gibs_layer}: {why} in {start}-{end}")
    steps = [entries[y]["palette_step"] for y in entries]
    attrs: dict = {
        "palette_step": steps[0] if steps else float("nan"),
        "dropped_years": [y for y in years if y in entries and entries[y]["grid"] is None],
        "missing_years": sorted(failed),
        "saturated_share": {y: entries[y]["saturated_share"] for y in kept},
    }
    tops = [entries[y]["scale_top"] for y in entries if "scale_top" in entries[y]]
    if tops:
        attrs["scale_top"] = tops[0]
    if layer.caveat:
        attrs["caveat"] = layer.caveat
    elif layer.transparent_value is not None:
        attrs["caveat"] = SNOW_CAVEAT
    return kept, attrs
