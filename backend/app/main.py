"""Earth Trend Detective API."""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.catalog import load_catalog
from app.extractors.power import DEFAULT_CACHE_DIR, fetch_monthly
from app.gather import SOURCES, gather_site_series
from app.sites import load_sites
from app.stats import compute_residuals, run_sweep

logger = logging.getLogger(__name__)
# httpx logs full request URLs at INFO; signed Earthdata download links carry the user id.
logging.getLogger("httpx").setLevel(logging.WARNING)

POWER_FIRST_YEAR = 1981
# Only observed impacts can carry a human signal in the residual. GLDAS is a land model
# without irrigation or pumping, so its residual is not reported as "non-climate %".
OBSERVED_SOURCES = frozenset({"grace", "appeears"})

app = FastAPI(title="Earth Trend Detective API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/variables")
def variables() -> list[dict]:
    return [
        {"id": v.id, "label": v.label, "role": v.role, "units": v.units, "dataset": v.dataset}
        for v in load_catalog()
    ]


def get_power_cache_dir() -> Path:
    """Where raw POWER responses are cached (overridden in tests)."""
    return DEFAULT_CACHE_DIR


def _validate_sweep_query(lat: float, lon: float, start: int, end: int) -> None:
    last_year = dt.date.today().year
    if not -90 <= lat <= 90:
        raise HTTPException(422, "Latitude must be between -90 and 90. Pick a point on the map and try again.")
    if not -180 <= lon <= 180:
        raise HTTPException(422, "Longitude must be between -180 and 180. Pick a point on the map and try again.")
    if not POWER_FIRST_YEAR <= start <= end <= last_year:
        raise HTTPException(
            422,
            f"Years must satisfy {POWER_FIRST_YEAR} <= start <= end <= {last_year}. "
            "Choose a valid period and try again.",
        )


@app.get("/sweep")
def sweep(
    lat: float,
    lon: float,
    start: int = 2003,
    end: int = 2024,
    cache_dir: Path = Depends(get_power_cache_dir),
) -> dict:
    """Trend sweep of the NASA POWER climate variables at one point."""
    _validate_sweep_query(lat, lon, start, end)
    catalog = load_catalog()
    bands = {v.id: v.band for v in catalog if v.source == "power"}
    try:
        series = fetch_monthly(lat, lon, bands, start, end, cache_dir=cache_dir)
    except httpx.TimeoutException:
        logger.warning("POWER timeout lat=%s lon=%s", lat, lon)
        raise HTTPException(504, "NASA POWER took too long to answer. Wait a minute and try again.") from None
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.warning("POWER failure lat=%s lon=%s: %s", lat, lon, exc)
        raise HTTPException(
            502,
            "We could not get climate data from NASA POWER for this point. "
            "Try again in a minute, or pick a different point.",
        ) from None
    results = run_sweep(series, catalog)
    return {
        "lat": lat,
        "lon": lon,
        "start": start,
        "end": end,
        "source": "NASA POWER monthly (power.larc.nasa.gov)",
        "variables": [r.to_dict() for r in results],
    }


@app.get("/sites")
def sites() -> list[dict]:
    """Story-mode sites."""
    return [
        {"id": s.id, "name": s.name, "bbox": list(s.bbox), "point": list(s.point), "tags": list(s.tags)}
        for s in load_sites().sites
    ]


@app.get("/sites/{site_id}/sweep")
def site_sweep(site_id: str, start: int | None = None, end: int | None = None) -> dict:
    """Trend sweep of every NASA variable that applies to a story-mode site."""
    site_catalog = load_sites()
    site = site_catalog.get(site_id)
    if site is None:
        known = ", ".join(s.id for s in site_catalog.sites)
        raise HTTPException(404, f"We don't know a site called '{site_id}'. Pick one of: {known}.")
    first, last = site_catalog.study_period
    start = first if start is None else start
    end = last if end is None else end
    last_year = dt.date.today().year
    if not POWER_FIRST_YEAR <= start <= end <= last_year:
        raise HTTPException(
            422,
            f"Years must satisfy {POWER_FIRST_YEAR} <= start <= end <= {last_year}. "
            "Choose a valid period and try again.",
        )
    catalog = load_catalog()
    gathered = gather_site_series(site, catalog, start, end)
    results = run_sweep(gathered.series, catalog) if gathered.series else []
    residuals = compute_residuals(gathered.series, catalog) if gathered.series else {}
    sources_by_var = {v.id: v.source for v in catalog}
    variables_out = []
    for r in results:
        row = r.to_dict()
        res = residuals.get(r.id)
        if res is not None:
            observed = sources_by_var.get(r.id) in OBSERVED_SOURCES
            row["residual_pct_non_climate"] = res.pct_non_climate if observed else None
            row["residual"] = res.to_dict() | {"observed": observed}
        variables_out.append(row)
    return {
        "site": {"id": site.id, "name": site.name, "bbox": list(site.bbox), "tags": list(site.tags)},
        "start": start,
        "end": end,
        "variables": variables_out,
        "missing": dict(gathered.missing),
        "sources": [{"id": k, "title": SOURCES[k].title, "url": SOURCES[k].url} for k in gathered.sources],
    }
