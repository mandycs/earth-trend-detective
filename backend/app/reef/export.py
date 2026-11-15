"""The reef `sites/great_barrier_reef/site.json`: sea temperature, the heat-stress record, chlorophyll.

The sweep runs through `site_export.build_site_json` on two series only: the MUR box-mean sea
temperature and the log10 chlorophyll at the Burdekin pixel. Then the reef rules apply:

- no climate / non-climate split (sea temperature is itself climate): every residual is null;
- degree heating weeks are an event record, not a trend test: the `dhw` row (second) has
  `kind: "events"`, null slope/p/q, and counts from `dhw.heat_stress_summary`;
- NOAA Coral Reef Watch SST is never read; MUR is the only sea-temperature record.

`export_reef` reads the cached ERDDAP data only (offline by default) and writes site.json,
then layers.json. Heat stress is heat stress, not bleaching or coral death.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from app import layers, site_export
from app.catalog import Variable, load_catalog
from app.extractors import erddap
from app.gather import GatherResult
from app.reef import dhw, sst
from app.reef.points import CHLOROPHYLL_POINT, REEF_POINTS
from app.site_report import GatherFn
from app.site_story import format_number
from app.sites import Site, load_sites

logger = logging.getLogger(__name__)

CHLOROPHYLL_ID = "chlorophyll"
CHLOROPHYLL_UNITS = "log10(mg/m³)"
KM_PER_DEGREE = 111.32  # one degree of latitude; longitude scaled by cos(latitude)

SST_FOOTPRINT_LABEL = "the whole map, averaged (NASA JPL MUR, sampled about every 5 km)"
CHLOROPHYLL_FOOTPRINT = {"km": 4, "label": "one 4 km MODIS pixel off the Burdekin River mouth"}
CHLOROPHYLL_NOTE = (
    "Read from water colour near the coast, where mud, river water and a shallow sea floor also change the colour."
)
NO_TREND_PREFIX = "No trend detected. "
DHW_FOOTPRINT = {
    "km": 5,
    "label": "five 5 km Coral Reef Watch pixels, north to south; two lie outside this map",
}

REEF_CAVEATS = (
    "Sea temperature is itself part of the climate, so this place has no climate / non-climate split.",
    "Degree heating weeks measure heat stress, not bleaching or coral death: this case does not count corals.",
    "Heat stress comes from NOAA Coral Reef Watch (not NASA). Sea temperature comes from NASA JPL MUR. "
    "The two temperature records are never mixed in one verdict.",
    "Seabed and land heights come from GEBCO (not NASA).",
)

REEF_SOURCES: tuple[Mapping[str, str], ...] = (
    {
        "title": "NASA JPL MUR sea surface temperature (GHRSST L4, monthly), via NOAA CoastWatch ERDDAP",
        "url": "https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST41mday.html",
    },
    {
        "title": "NASA MODIS Aqua chlorophyll-a (R2022), via NOAA CoastWatch ERDDAP",
        "url": "https://coastwatch.pfeg.noaa.gov/erddap/griddap/erdMH1chlamday_R2022SQ.html",
    },
    {"title": dhw.SOURCE["name"], "url": dhw.SOURCE["url"]},
    {
        "title": "GEBCO Compilation Group, GEBCO 2020 Grid (not NASA), via NOAA CoastWatch ERDDAP",
        "url": "https://coastwatch.pfeg.noaa.gov/erddap/griddap/GEBCO_2020.html",
    },
    {"title": layers.GIBS["name"], "url": layers.GIBS["url"]},
)


@dataclass(frozen=True)
class ReefSeries:
    sst: pd.Series  # monthly box mean, °C
    chlorophyll_log10: pd.Series  # monthly, log10(mg/m³)
    sst_missing_years: tuple[int, ...] = ()  # MUR years whose fetch failed
    chlorophyll_missing_years: tuple[int, ...] = ()  # chlorophyll years whose fetch failed


def missing_text(years: Sequence[int]) -> str:
    """Plain sentence for `site.json` `missing`: the years that could not be loaded."""
    return f"no data for {', '.join(str(y) for y in sorted(years))} (fetch failed)"


def reef_missing(series: ReefSeries) -> dict[str, str]:
    """Variables with failed years -> their `missing` text; a variable without any is left out."""
    failed = {sst.SST_VAR_ID: series.sst_missing_years, CHLOROPHYLL_ID: series.chlorophyll_missing_years}
    return {var: missing_text(years) for var, years in failed.items() if years}


def _heat_gaps(heat: Mapping) -> list[tuple[str, list[int]]]:
    """(reef name, years without a value) for every reef point that has any."""
    out = []
    for point in heat["points"]:
        years = [r["year"] for r in point["yearly_max"] if r["value"] is None]
        if years:
            out.append((point["name"], years))
    return out


def heat_missing(heat: Mapping) -> dict[str, str]:
    """`{"dhw": text}` naming the reef-years whose fetch failed; empty when none did."""
    gaps = _heat_gaps(heat)
    if not gaps:
        return {}
    n = sum(len(years) for _name, years in gaps)
    where = "; ".join(f"{name} {', '.join(str(y) for y in years)}" for name, years in gaps)
    return {"dhw": f"no data for {_reef_years(n)} (fetch failed): {where}"}


def _uncounted_text(heat: Mapping) -> str:
    """"N reef-years without data are not counted", or "" when every reef-year was measured."""
    n = sum(int(p.get("reef_years_missing", 0)) for p in heat["periods"])
    if not n:
        return ""
    return f"{_reef_years(n)} without data {'is' if n == 1 else 'are'} not counted"


def reef_catalog(catalog: Sequence[Variable]) -> tuple[Variable, ...]:
    """The catalog with chlorophyll in log10 units (its series is log10); nothing else changes."""
    return tuple(
        dataclasses.replace(v, units=CHLOROPHYLL_UNITS) if v.id == CHLOROPHYLL_ID else v for v in catalog
    )


def reef_gather(series: ReefSeries) -> GatherFn:
    """A gather function handing the already loaded reef series to `build_site_json`."""

    def gather(_site: Site, _catalog: Sequence[Variable], _start: int, _end: int) -> GatherResult:
        return GatherResult(
            series={sst.SST_VAR_ID: series.sst, CHLOROPHYLL_ID: series.chlorophyll_log10},
            missing=reef_missing(series),
            sources=("erddap",),
        )

    return gather


def bbox_width_km(bbox: Sequence[float]) -> int:
    """East-west width of the box at its middle latitude, rounded to the kilometre."""
    west, south, east, north = (float(x) for x in bbox)
    mid = math.radians((south + north) / 2)
    return round((east - west) * KM_PER_DEGREE * math.cos(mid))


def _first_threshold(heat: Mapping) -> tuple[str, str]:
    """The lower threshold as its `reef_years_at_or_above` key ("4") and as shown ("4 °C-weeks")."""
    value = float(heat["thresholds"][0]["value"])
    key = str(int(value)) if value.is_integer() else str(value)
    return key, f"{value:g} {heat['unit']}"


def _counts(heat: Mapping) -> tuple[int, list[int], int, list[int]]:
    key, _shown = _first_threshold(heat)
    first, second = heat["periods"]
    return (
        first["reef_years_at_or_above"][key],
        first["years"],
        second["reef_years_at_or_above"][key],
        second["years"],
    )


def _reef_years(n: int) -> str:
    return f"{n} reef-year" if n == 1 else f"{n} reef-years"


def dhw_note(heat: Mapping) -> str:
    a, (p0, p1), b, (q0, q1) = _counts(heat)
    _key, shown = _first_threshold(heat)
    return (
        f"Not a trend test. Reef-years at or above {shown}, five reefs: "
        f"{a} in {p0}–{p1}, {b} in {q0}–{q1}."
    ) + (f" {gap}." if (gap := _uncounted_text(heat)) else "")


def reef_headline(sst_row: Mapping | None, heat: Mapping) -> str | None:
    """Headline from the sst row and the heat-stress counts; None unless the sst trend is real."""
    if not sst_row or sst_row.get("verdict") != "real" or sst_row.get("sen_slope_per_decade") is None:
        return None
    a, (p0, p1), b, (q0, q1) = _counts(heat)
    _key, shown = _first_threshold(heat)
    slope = format_number(sst_row["sen_slope_per_decade"])
    return (
        f"Sea temperature over the reef is going up for real ({slope} °C per decade). "
        f"Heat stress at or above {shown}: {_reef_years(a)} in {p0}–{p1}, {b} in {q0}–{q1}"
    ) + (f" ({gap})." if (gap := _uncounted_text(heat)) else ".")


def dhw_row(heat: Mapping) -> dict:
    """The heat-stress record as a variable row: an event count, never a trend test."""
    row: dict = {k: None for k in site_export.VARIABLE_FIELDS}
    row |= {
        "id": "dhw",
        "kind": "events",
        "label": "Heat stress, worst of five reefs",
        "unit": dhw.UNIT,
        "series": dhw.worst_reef_series(heat),
        "thresholds": [dict(t) for t in heat["thresholds"]],
        "verdict": "unknown",
        "direction": "flat",
        "badge": "Heat-stress record",
        "footprint": dict(DHW_FOOTPRINT),
        "note": dhw_note(heat),
    }
    return row


def _reef_row(row: Mapping, site: Site) -> dict:
    out = {**row, "residual_pct_non_climate": None, "residual_pct_range": None, "kind": "trend"}
    if out["id"] == sst.SST_VAR_ID:
        out["footprint"] = {"km": bbox_width_km(site.bbox), "label": SST_FOOTPRINT_LABEL}
    elif out["id"] == CHLOROPHYLL_ID:
        out["footprint"] = dict(CHLOROPHYLL_FOOTPRINT)
        prefix = NO_TREND_PREFIX if out.get("verdict") == "unknown" else ""
        out["note"] = prefix + CHLOROPHYLL_NOTE
    return out


def build_reef_site_json(
    site: Site,
    catalog: Sequence[Variable],
    start: int,
    end: int,
    site_dir: Path,
    series: ReefSeries,
    heat: dict,
    today: dt.date | None = None,
) -> dict:
    """The reef site.json document (no file written). Sea temperature leads, heat stress second."""
    doc = site_export.build_site_json(
        site, reef_catalog(catalog), start, end, site_dir, gather=reef_gather(series), validators={}, today=today
    )
    rows = [_reef_row(r, site) for r in doc["variables"]]
    lead = [r for r in rows if r["id"] == sst.SST_VAR_ID]
    rest = [r for r in rows if r["id"] != sst.SST_VAR_ID]
    sst_row = lead[0] if lead else None
    return {
        **doc,
        "missing": {**doc.get("missing", {}), **heat_missing(heat)},
        "variables": [*lead, dhw_row(heat), *rest],
        "heat_stress": heat,
        "headline": reef_headline(sst_row, heat),
        "caveats": list(REEF_CAVEATS),
        "sources": [dict(s) for s in REEF_SOURCES],
    }


# --------------------------------------------------------------------------- loading


def offline_client() -> httpx.Client:
    """An ERDDAP client that never reaches the network: a cache miss raises FileNotFoundError."""

    def refuse(request: httpx.Request) -> httpx.Response:
        raise FileNotFoundError(f"offline: {request.url.path} is not in the ERDDAP cache")

    return httpx.Client(transport=httpx.MockTransport(refuse))


def _client(offline: bool) -> httpx.Client:
    return offline_client() if offline else erddap.new_client()


def _chlorophyll_var() -> Variable:
    return next(v for v in load_catalog() if v.id == CHLOROPHYLL_ID)


def load_series(site: Site, start: int, end: int, cache_dir: Path, offline: bool) -> ReefSeries:
    """MUR box mean (Task 3 loader) and the log10 chlorophyll at the Burdekin pixel, start..end."""
    grid = sst.mur_grid(range(start, end + 1), site.bbox, cache_dir, offline=offline)
    sea = sst.box_mean_series(grid)
    var = _chlorophyll_var()
    point = next(p for p in REEF_POINTS if p.id == CHLOROPHYLL_POINT)
    with _client(offline) as client:
        raw, _cell = erddap.fetch_point_monthly(var.dataset, var.band, point.lat, point.lon, start, end, client, cache_dir)
    values = raw * var.scale + var.offset
    chl = np.log10(values.where(values > 0)).astype(float)
    chl = chl[(chl.index.year >= start) & (chl.index.year <= end)].rename(CHLOROPHYLL_ID)
    return ReefSeries(
        sst=sea,
        chlorophyll_log10=chl,
        sst_missing_years=tuple(grid.missing_years),
        chlorophyll_missing_years=tuple(raw.attrs.get("missing_years", ())),
    )


def load_heat(start: int, end: int, cache_dir: Path, offline: bool) -> dict:
    """Heat-stress summary at the five reef points (Task 4 loader), start..end."""
    years = list(range(start, end + 1))
    with _client(offline) as client:
        yearly = {p.id: dhw.yearly_max(p, years, cache_dir, client) for p in REEF_POINTS}
    return dhw.heat_stress_summary(yearly, list(REEF_POINTS), start, end)


def export_reef(site: Site, sites_dir: Path, cache_dir: Path, offline: bool = True) -> dict:
    """Build and write `sites/<id>/site.json`, then `layers.json`, from cached ERDDAP data."""
    start, end = load_sites().study_period
    site_dir = sites_dir / site.id
    series = load_series(site, start, end, cache_dir, offline)
    heat = load_heat(start, end, cache_dir, offline)
    doc = build_reef_site_json(site, load_catalog(), start, end, site_dir, series, heat)
    path = site_export.write_site_json(doc, site_dir)
    layers.write_layers(site.id, site_dir)
    logger.info("wrote %s", path)
    return doc
