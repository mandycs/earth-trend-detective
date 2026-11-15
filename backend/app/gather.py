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

import numpy as np
import pandas as pd

from app.catalog import Variable, variables_for_site
from app.extractors import appeears, erddap, gldas, grace, power, water
from app.sites import Site
from app.stats.residual import SNOW_DRIVERS, UPSTREAM_DRIVERS, degree_days, winter_precip

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
        "appeears_water": SourceInfo(
            "MODIS MOD09A1 surface reflectance via NASA AppEEARS (open-water NDWI)",
            "https://appeears.earthdatacloud.nasa.gov",
            "We could not read the satellite water data downloaded from NASA AppEEARS. Try again later.",
        ),
        "erddap": SourceInfo(
            "Sea data via NOAA CoastWatch ERDDAP (NASA JPL MUR sea temperature, NASA MODIS Aqua "
            "chlorophyll, NOAA Coral Reef Watch heat stress)",
            "https://coastwatch.pfeg.noaa.gov/erddap/",
            "The NOAA CoastWatch ERDDAP server (sea data) did not answer. Try again in a few minutes.",
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
    upstream = [v for v in variables if v.id in UPSTREAM_DRIVERS]
    local = [v for v in variables if v.id not in UPSTREAM_DRIVERS]
    bands = {v.id: v.band for v in local}
    # Only upstream drivers asked (the detective fetches one variable at a time): no local call,
    # since POWER answers an empty `parameters=` with a 422.
    out = dict(power.fetch_monthly(site.lat, site.lon, bands, start, end)) if bands else {}
    for var_id, derive in SNOW_DERIVATIONS.items():
        if var_id in out:  # fetched as the raw POWER band, turned into the derived driver
            out[var_id] = derive(out[var_id])
    if upstream and site.upstream_climate is not None:
        out.update(_fetch_upstream(site, upstream, start, end))
    return out


SNOW_DERIVATIONS: Mapping[str, Callable[[pd.Series], pd.Series]] = MappingProxyType(
    {"degree_days": degree_days, "winter_precip": winter_precip}
)


def _fetch_upstream(
    site: Site, variables: Sequence[Variable], start: int, end: int
) -> dict[str, pd.Series]:
    """Upstream drivers: POWER at each upstream point, averaged month by month.

    A failure here only loses the upstream drivers (the residual then falls back to the
    local-only model); the local climate drivers are kept.
    """
    bands = {v.id: v.band for v in variables}
    try:
        per_point = [
            power.fetch_monthly(lat, lon, bands, start, end)
            for lon, lat in site.upstream_climate.points
        ]
    except Exception as exc:  # noqa: BLE001 - upstream drivers are optional
        logger.warning("upstream POWER failed for site %s: %s: %s", site.id, type(exc).__name__, exc)
        return {}
    return {
        var_id: pd.concat([p[var_id] for p in per_point], axis=1).mean(axis=1, skipna=False).rename(var_id)
        for var_id in bands
    }


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


def _fetch_appeears_water(
    site: Site,
    variables: Sequence[Variable],
    _: Sequence[Variable],
    start: int,
    end: int,
) -> dict[str, pd.Series]:
    bundle = appeears.water_bundle_dir(site.id)
    if not water.bundle_paths(bundle):
        return {}  # not downloaded yet -> `missing` with the AppEEARS wording
    series = water.fetch_water_area(bundle, start, end)
    return {v.id: series.rename(v.id) for v in variables}


def _fetch_erddap(
    site: Site,
    variables: Sequence[Variable],
    _: Sequence[Variable],
    start: int,
    end: int,
) -> dict[str, pd.Series]:
    """Sea variables at the site point, one variable after another (ERDDAP answers 408 to
    parallel calls). Annual variables (DHW) come as the yearly maximum; `attrs["cell"]` keeps
    the grid cell actually used."""
    out: dict[str, pd.Series] = {}
    for var in variables:
        fetch = erddap.fetch_point_yearly_max if var.temporal == "annual" else erddap.fetch_point_monthly
        raw, cell = fetch(var.dataset, var.band, site.lat, site.lon, start, end)
        values = raw * var.scale + var.offset
        if var.transform == "log10":
            values = np.log10(values.where(values > 0))
        series = values.astype(float).rename(var.id)
        series.attrs = {**raw.attrs, "cell": cell}
        out[var.id] = series
    return out


FETCHERS: Mapping[str, Fetcher] = MappingProxyType(
    {
        "power": _fetch_power,
        "grace": _fetch_grace,
        "gldas": _fetch_gldas,
        "appeears": _fetch_appeears,
        "appeears_water": _fetch_appeears_water,
        "erddap": _fetch_erddap,
    }
)


# Sources read from local NetCDF bundles; kept out of the thread pool (HDF5 not thread-safe).
LOCAL_NETCDF_SOURCES = frozenset({"appeears", "appeears_water"})


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
    if source == "appeears_water":
        return _appeears_reason(f"{site_id}{appeears.WATER_SUFFIX}")
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


def site_extra_drivers(site: Site, catalog: Sequence[Variable]) -> tuple[Variable, ...]:
    """Candidate climate drivers the site opts into in sites.yaml (not picked by tags).

    They feed the residual model selection and are listed like the other drivers.
    """
    wanted: set[str] = set()
    if site.upstream_climate is not None:
        wanted |= set(UPSTREAM_DRIVERS)
    if site.snow_terms:
        wanted |= set(SNOW_DRIVERS)
    return tuple(v for v in catalog if v.id in wanted and v.role == "driver")


def gather_site_series(
    site: Site, catalog: Sequence[Variable], start: int, end: int
) -> GatherResult:
    """Every applicable variable for `site` over [start, end], from all NASA sources in parallel."""
    applicable = variables_for_site(catalog, site.tags) + site_extra_drivers(site, catalog)
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
    remote = {s: vs for s, vs in jobs.items() if s not in LOCAL_NETCDF_SOURCES}
    with ThreadPoolExecutor(max_workers=max(1, len(remote))) as pool:
        futures = {
            s: pool.submit(_run_source, s, site, vs, catalog, start, end)
            for s, vs in remote.items()
        }
        outcomes = {s: f.result() for s, f in futures.items()}
    # Local AppEEARS NetCDF reads run after the pool, one at a time: netCDF4/HDF5 is
    # not thread-safe ("NetCDF: Can't open HDF5 attribute" next to the GRACE read).
    for s, vs in jobs.items():
        if s in LOCAL_NETCDF_SOURCES:
            outcomes[s] = _run_source(s, site, vs, catalog, start, end)

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
