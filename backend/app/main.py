"""Alibi API."""

from __future__ import annotations

import os
import datetime as dt
import logging
import math
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pandas as pd
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.catalog import load_catalog
from app.extractors.power import DEFAULT_CACHE_DIR, fetch_monthly
from app.gather import gather_site_series
from app.site_report import OBSERVED_SOURCES, build_site_report  # noqa: F401 - re-export
from app.sites import load_sites
from app.stats import run_sweep
from app.stats.deseason import monthly_anomalies

logger = logging.getLogger(__name__)
# httpx logs full request URLs at INFO; signed Earthdata download links carry the user id.
logging.getLogger("httpx").setLevel(logging.WARNING)

POWER_FIRST_YEAR = 1981

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # The detective's checkpointer and store: one SQLite pair per process.
    from app.detective.router import shutdown_persistence, startup_persistence

    try:
        startup_persistence()
    except Exception as exc:  # noqa: BLE001 - the rest of the API must still start; /detective answers 503
        logger.error("detective persistence failed to open: %s", type(exc).__name__)
    try:
        yield
    finally:
        shutdown_persistence()


app = FastAPI(title="Alibi API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # Comma-separated list, e.g. "http://localhost:3000,https://earth-trend-detective.example".
    # The dev server runs on :5180 and is often opened as 127.0.0.1, so both hosts are
    # allowed by default: without them the narrator, the map sweep and the investigator
    # fail in the browser with no visible reason. Production must set CORS_ORIGINS.
    allow_origins=[
        o.strip()
        for o in os.environ.get(
            "CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5180,http://127.0.0.1:5180",
        ).split(",")
        if o.strip()
    ],
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


def _finite_or_none(value: float) -> float | None:
    return float(value) if pd.notna(value) and math.isfinite(value) else None


def _series_payload(series: dict[str, pd.Series]) -> dict[str, list[dict]]:
    """Monthly value + anomaly per variable for the explore-mode charts (NaN -> null)."""
    payload: dict[str, list[dict]] = {}
    for var_id, values in series.items():
        anomalies = monthly_anomalies(values)
        payload[var_id] = [
            {
                "date": ts.strftime("%Y-%m"),
                "value": _finite_or_none(value),
                "anomaly": _finite_or_none(anomalies.loc[ts]),
            }
            for ts, value in values.items()
        ]
    return payload


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
    include_series: bool = False,
    cache_dir: Path = Depends(get_power_cache_dir),
) -> dict:
    """Trend sweep of the NASA POWER climate variables at one point.

    With `include_series=true` the response also carries the monthly series
    (`series: {var_id: [{date, value, anomaly}]}`) for charts.
    """
    _validate_sweep_query(lat, lon, start, end)
    catalog = load_catalog()
    # Only point variables that apply anywhere; site-only derived ones (upstream means,
    # degree-days) would just repeat the raw band at the clicked point.
    bands = {v.id: v.band for v in catalog if v.source == "power" and "any" in v.applies_to}
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
    body = {
        "lat": lat,
        "lon": lon,
        "start": start,
        "end": end,
        "source": "NASA POWER monthly (power.larc.nasa.gov)",
        "variables": [r.to_dict() for r in results],
    }
    if include_series:
        body["series"] = _series_payload(series)
    return body


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
    # Looked up here (not bound at import) so tests can monkeypatch app.main.gather_site_series.
    return build_site_report(site, load_catalog(), start, end, gather=gather_site_series)


# /explain: question routing + verified narrative (app/explain/).
from app.explain.router import router as explain_router  # noqa: E402

app.include_router(explain_router)

# /investigate: LLM-planned investigation streamed as Server-Sent Events (app/investigate/).
from app.investigate.router import router as investigate_router  # noqa: E402

app.include_router(investigate_router)

# /detective: the LangGraph investigator streamed as Server-Sent Events (app/detective/).
from app.detective.router import router as detective_router  # noqa: E402

app.include_router(detective_router)

# /layers/suggest: LLM-picked map layer stack for a question (app/layer_suggest.py).
from app.layer_suggest import router as layers_router  # noqa: E402

app.include_router(layers_router)
