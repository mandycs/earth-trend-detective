"""Yearly values at any point from NASA GIBS monthly layers (no auth): the `gibs` source.

GIBS serves MODIS monthly NDVI, land surface temperature and snow cover as coloured PNGs
with a published colormap. For the place's box we read every month of each year at the
product's own resolution (`assets/gibs_layers.yearly_values`), turn colours back into values
(interval midpoints), average the months of the year, and keep the box mean: one value per
year, for the annual trend path. Precision is one palette step (`attrs["palette_step"]`).

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
POINT_LAYERS: tuple[GibsLayer, ...] = (*LAYERS, SNOW_LAYER)


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


def palette_step(table: dict[tuple[int, int, int], float]) -> float:
    """Typical distance between neighbouring colormap values: the precision of a decoded value."""
    values = np.unique(np.round(np.array(sorted(table.values()), dtype=float), 9))
    if values.size < 2:
        return float("nan")
    return float(np.median(np.diff(values)))


def last_complete_year() -> int:
    return _this_year() - 1


def _cache_path(cache_dir: Path, layer: GibsLayer, bbox: Sequence[float], year: int) -> Path:
    key = json.dumps([layer.gibs_layer, [round(float(c), 6) for c in bbox], list(YEAR_MONTHS), year])
    return cache_dir / layer.id / f"{hashlib.sha256(key.encode()).hexdigest()[:20]}.json"


def _read_cache(path: Path) -> dict | None:
    """The cached year ({"mean": float | None, "palette_step": float}); a corrupt file is deleted."""
    if not path.exists():
        return None
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
        mean, step = entry["mean"], float(entry["palette_step"])
        return {"mean": None if mean is None else float(mean), "palette_step": step}
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
    years = list(range(start, min(end, last_complete_year()) + 1))
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
            grids = yearly_values(layer, bbox, todo, client, YEAR_MONTHS, table=table, workers=WORKERS, failed=failed)
        finally:
            if own:
                client.close()
        step = palette_step(table)
        for year in todo:
            if year in failed:
                continue  # partial: a gap, and asked again next time
            with np.errstate(all="ignore"):
                mean = float(np.nanmean(grids[year])) if year in grids else None
            entries[year] = {"mean": mean, "palette_step": step}
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
    if layer.transparent_value is not None:
        series.attrs["caveat"] = SNOW_CAVEAT
    return series
