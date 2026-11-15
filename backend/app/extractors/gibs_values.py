"""Yearly values at any point from NASA GIBS monthly layers (no auth): the `gibs` source.

GIBS serves MODIS monthly NDVI, land surface temperature and snow cover as coloured PNGs
with a published colormap. For the place's box we read every month of each year at the
product's own resolution (`assets/gibs_layers.yearly_values`), turn colours back into values
(interval midpoints), average the months of the year, and keep the box mean: one value per
year, for the annual trend path. Precision is one palette step (`attrs["palette_step"]`).

A year whose pictures are transparent (no clear view) is dropped and listed in
`attrs["dropped_years"]`. The unfinished current year is never asked. If no year at all
comes back, `GibsError` is raised (GIBS down, or nothing to see here).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

import httpx
import numpy as np
import pandas as pd

from app.assets.gibs_layers import LAYERS, GibsLayer, load_colormap, yearly_values
from app.catalog import Variable

TIMEOUT_S = 30.0
WORKERS = 8  # parallel GetMap requests (GIBS serves tiles from a CDN)
YEAR_MONTHS = tuple(range(1, 13))  # every month: the yearly mean, no season picked per climate
SNOW_CAVEAT = (
    "GIBS draws snow-free ground and ground it could not see (night, cloud) the same way; "
    "both count as no snow."
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


def fetch_annual(
    layer: GibsLayer,
    bbox: Sequence[float],
    start: int,
    end: int,
    client: httpx.Client | None = None,
) -> pd.Series:
    """Box mean of the yearly mean, one value per kept year, indexed on Jan 1 (display units)."""
    years = list(range(start, min(end, _this_year() - 1) + 1))
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT_S, transport=httpx.HTTPTransport(retries=2))
    try:
        table = load_colormap(client, layer)
        if not table:
            raise GibsError(f"GIBS colormap {layer.colormap!r} unreadable")
        grids = yearly_values(layer, bbox, years, client, YEAR_MONTHS, table=table, workers=WORKERS)
    finally:
        if own:
            client.close()
    if not grids:
        raise GibsError(f"GIBS {layer.gibs_layer}: no usable picture in {start}-{end} for this box")
    kept = sorted(grids)
    with np.errstate(all="ignore"):
        means = [float(np.nanmean(grids[y])) for y in kept]
    series = pd.Series(means, index=pd.to_datetime([f"{y}-01-01" for y in kept]), dtype=float, name=layer.id)
    series.attrs = {
        "temporal": "annual",
        "palette_step": palette_step(table),
        "months": list(YEAR_MONTHS),
        "dropped_years": [y for y in years if y not in grids],
    }
    if layer.transparent_value is not None:
        series.attrs["caveat"] = SNOW_CAVEAT
    return series
