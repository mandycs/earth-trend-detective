"""Gather every NASA series that applies to a site, one source at a time.

Shared series contract: month-start DatetimeIndex covering [start, end] fully,
values in catalog units, NaN for months without data. A source that fails is
logged and its variables land in `missing` with a plain-English reason; the
other sources still return.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from types import MappingProxyType

import pandas as pd

from app.catalog import Variable, variables_for_site
from app.extractors import appeears, gldas, grace, power
from app.sites import Site

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceInfo:
    title: str
    url: str
    failure: str  # shown when the source raised


SOURCES: Mapping[str, SourceInfo] = MappingProxyType(
    {
        "power": SourceInfo(
            "NASA POWER monthly climate (MERRA-2, IMERG, CERES)",
            "https://power.larc.nasa.gov",
            "NASA POWER did not answer. Try again in a few minutes.",
        ),
        "grace": SourceInfo(
            "GRACE/GRACE-FO JPL mascons RL06.3 (NASA PO.DAAC)",
            "https://podaac.jpl.nasa.gov/dataset/TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4",
            "We could not read the GRACE water-storage data. Try again in a few minutes.",
        ),
        "gldas": SourceInfo(
            "GLDAS Noah 0.25° monthly v2.1 (NASA GES DISC)",
            "https://disc.gsfc.nasa.gov/datasets/GLDAS_NOAH025_M_2.1/summary",
            "NASA GES DISC (GLDAS soil and runoff data) did not answer. Try again in a few minutes.",
        ),
        "appeears": SourceInfo(
            "MODIS land products via NASA AppEEARS",
            "https://appeears.earthdatacloud.nasa.gov",
            "We could not read the satellite data downloaded from NASA AppEEARS. Try again later.",
        ),
    }
)

APPEEARS_PENDING = (
    "Satellite data still being processed by NASA AppEEARS. Check back later."
)
APPEEARS_NOT_REQUESTED = (
    "Satellite data for this site has not been requested from NASA AppEEARS yet."
)


@dataclass(frozen=True)
class GatherResult:
    series: Mapping[str, pd.Series] = field(default_factory=dict)
    missing: Mapping[str, str] = field(default_factory=dict)
    sources: tuple[str, ...] = ()  # source keys that returned at least one series


Fetcher = Callable[
    [Site, Sequence[Variable], Sequence[Variable], int, int], dict[str, pd.Series]
]


# --------------------------------------------------------------------------- per-source fetchers


def _fetch_power(
    site: Site,
    variables: Sequence[Variable],
    _: Sequence[Variable],
    start: int,
    end: int,
) -> dict[str, pd.Series]:
    bands = {v.id: v.band for v in variables}
    return power.fetch_monthly(site.lat, site.lon, bands, start, end)


def _fetch_grace(
    site: Site,
    variables: Sequence[Variable],
    _: Sequence[Variable],
    start: int,
    end: int,
) -> dict[str, pd.Series]:
    series = grace.fetch_grace_series(site.bbox, start, end)
    return {v.id: series.rename(v.id) for v in variables}


def _fetch_gldas(
    site: Site,
    variables: Sequence[Variable],
    _: Sequence[Variable],
    start: int,
    end: int,
) -> dict[str, pd.Series]:
    return gldas.fetch_monthly(site.lat, site.lon, variables, start, end)


def _fetch_appeears(
    site: Site,
    variables: Sequence[Variable],
    catalog: Sequence[Variable],
    start: int,
    end: int,
) -> dict[str, pd.Series]:
    return appeears.fetch_site_series(site.id, catalog=catalog)


FETCHERS: Mapping[str, Fetcher] = MappingProxyType(
    {
        "power": _fetch_power,
        "grace": _fetch_grace,
        "gldas": _fetch_gldas,
        "appeears": _fetch_appeears,
    }
)


# --------------------------------------------------------------------------- helpers


def conform(series: pd.Series, start: int, end: int) -> pd.Series:
    """Month-start index, trimmed and reindexed to [start-01, end-12]; returns a new series."""
    index = pd.DatetimeIndex(series.index).to_period("M").to_timestamp()
    values = pd.Series(series.to_numpy(dtype=float), index=index)
    values = values.groupby(level=0).mean()
    full = pd.date_range(f"{start}-01-01", f"{end}-12-01", freq="MS")
    return values.reindex(full).rename(series.name)


def _appeears_reason(site_id: str) -> str:
    try:
        tasks = appeears.load_tasks()
    except Exception:  # noqa: BLE001 - a broken tasks file only changes the wording
        logger.warning("could not read AppEEARS tasks file", exc_info=True)
        return APPEEARS_PENDING
    submitted = any(t.site_id == site_id for t in tasks.values())
    return APPEEARS_PENDING if submitted else APPEEARS_NOT_REQUESTED


def _empty_reason(
    source: str, var: Variable, site_id: str, start: int, end: int
) -> str:
    if source == "appeears":
        return _appeears_reason(site_id)
    return f"{var.dataset} has no {var.label.lower()} values for this site in {start}-{end}."


def _run_source(
    source: str,
    site: Site,
    variables: Sequence[Variable],
    catalog: Sequence[Variable],
    start: int,
    end: int,
) -> tuple[dict[str, pd.Series], dict[str, str]]:
    try:
        raw = FETCHERS[source](site, variables, catalog, start, end)
    except Exception as exc:  # noqa: BLE001 - one failing source must not kill the sweep
        logger.warning(
            "source %s failed for site %s: %s: %s",
            source,
            site.id,
            type(exc).__name__,
            exc,
        )
        reason = SOURCES[source].failure
        return {}, {v.id: reason for v in variables}

    series: dict[str, pd.Series] = {}
    missing: dict[str, str] = {}
    for var in variables:
        got = raw.get(var.id)
        trimmed = conform(got, start, end) if got is not None else None
        if trimmed is None or trimmed.notna().sum() == 0:
            missing[var.id] = _empty_reason(source, var, site.id, start, end)
        else:
            series[var.id] = trimmed.rename(var.id)
    return series, missing


# --------------------------------------------------------------------------- public


def gather_site_series(
    site: Site, catalog: Sequence[Variable], start: int, end: int
) -> GatherResult:
    """Every applicable variable for `site` over [start, end], from all NASA sources in parallel."""
    applicable = variables_for_site(catalog, site.tags)
    by_source: dict[str, list[Variable]] = {}
    for var in applicable:
        by_source.setdefault(var.source, []).append(var)

    series: dict[str, pd.Series] = {}
    missing: dict[str, str] = {}
    unsupported = [s for s in by_source if s not in FETCHERS]
    for source in unsupported:
        logger.warning("no fetcher for source %s", source)
        missing.update(
            {v.id: "This data source is not connected yet." for v in by_source[source]}
        )

    jobs = {s: tuple(vs) for s, vs in by_source.items() if s in FETCHERS}
    with ThreadPoolExecutor(max_workers=max(1, len(jobs))) as pool:
        futures = {
            s: pool.submit(_run_source, s, site, vs, catalog, start, end)
            for s, vs in jobs.items()
        }
        outcomes = {s: f.result() for s, f in futures.items()}

    contributing: list[str] = []
    for source in jobs:
        got, lost = outcomes[source]
        series.update(got)
        missing.update(lost)
        if got:
            contributing.append(source)

    order = [v.id for v in applicable]
    return GatherResult(
        series={k: series[k] for k in order if k in series},
        missing={k: missing[k] for k in order if k in missing},
        sources=tuple(contributing),
    )
