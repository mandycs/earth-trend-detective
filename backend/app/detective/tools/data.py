"""First tools of the detective: profile the place, list variables, fetch a series, trend-test it.

Every tool goes through the session ledger: an identical call returns the cached result with
its evidence id instead of re-running (and never logs a second test).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Mapping
from dataclasses import replace

import pandas as pd

from app import gather
from app.catalog import Variable, variables_for_site
from app.detective.ledger import TestRecord
from app.detective.session import Session
from app.investigate import landcover
from app.investigate.runner import LAND_COVER_YEARS
from app.stats.deseason import monthly_anomalies
from app.stats.trend import trend_test as mk_trend_test
from app.stats.years import years_needed

logger = logging.getLogger(__name__)

APPEEARS_SOURCES = frozenset({"appeears", "appeears_water"})
OFF_CASE_REASON = "not_available_here: only precomputed for the solved cases"
EXTRA_DRIVER_REASON = "not_available_here: only set up for the solved cases that need it"
RESOLUTION: Mapping[str, str] = {
    "power": "~50 km",
    "grace": "~300 km",
    "gldas": "~25 km",
    "appeears": "~250 m to 1 km",
    "appeears_water": "~500 m",
}
DATA_CELLS = {"grace": RESOLUTION["grace"], "power": RESOLUTION["power"]}


def _num(x: float | None, ndigits: int = 4) -> float | None:
    if x is None or not math.isfinite(x):
        return None
    return round(float(x), ndigits)


def _through_ledger(session: Session, tool: str, args: Mapping, compute: Callable[[], dict]) -> dict:
    key = session.ledger.call_key(tool, args)
    hit = session.ledger.cached(key)
    if hit is not None:
        return hit
    result = compute()
    eid = session.ledger.remember(key, result)
    return {**result, "evidence_id": eid}


def _variable(session: Session, var_id: str) -> Variable | None:
    return next((v for v in session.catalog if v.id == var_id), None)


def _unavailable_reason(session: Session, var: Variable) -> str | None:
    if var.source in APPEEARS_SOURCES and session.place.site_id is None:
        return OFF_CASE_REASON
    return None


# --------------------------------------------------------------------------- profile_place


def profile_place(session: Session) -> dict:
    place = session.place
    args = {"lat": place.lat, "lon": place.lon, "site_id": place.site_id}
    return _through_ledger(session, "profile_place", args, lambda: _profile(session))


def _profile(session: Session) -> dict:
    place = session.place
    try:
        cover = landcover.fetch_land_cover(place.lat, place.lon, LAND_COVER_YEARS[-1])
    except Exception as exc:  # noqa: BLE001 - the place can still be investigated without land cover
        logger.warning("land cover failed at %s,%s: %s: %s", place.lat, place.lon, type(exc).__name__, exc)
        return {
            "tags": list(place.tags),
            "land_cover": {},
            "dominant": None,
            "data_cells": dict(DATA_CELLS),
            "land_cover_status": "not_available",
        }
    new_tags = landcover.tags_for(cover.shares)
    tags = tuple(dict.fromkeys(place.tags + tuple(new_tags)))
    session.place = replace(place, tags=tags)
    return {
        "tags": list(tags),
        "land_cover": {k: _num(v, 3) for k, v in cover.shares.items()},
        "dominant": cover.dominant,
        "land_cover_year": cover.year,
        "data_cells": dict(DATA_CELLS),
    }


# --------------------------------------------------------------------------- list_variables


def list_variables(session: Session) -> dict:
    args = {"tags": list(session.place.tags), "site_id": session.place.site_id}
    return _through_ledger(session, "list_variables", args, lambda: {"variables": _rows(session)})


def _rows(session: Session) -> list[dict]:
    site = session.place.as_site()
    applicable = variables_for_site(session.catalog, session.place.tags)
    extra = gather.site_extra_drivers(site, session.catalog)
    extra_ids = {v.id for v in extra}
    # Opt-in drivers (upstream, snow) the place does not have are listed as unavailable.
    opt_in = tuple(v for v in session.catalog if not v.applies_to and v.role == "driver" and v.id not in extra_ids)
    rows = []
    for var in applicable + extra + opt_in:
        reason = EXTRA_DRIVER_REASON if var in opt_in else _unavailable_reason(session, var)
        row = {
            "id": var.id,
            "label": var.label,
            "definition": var.definition,
            "role": var.role,
            "source": var.source,
            "resolution": RESOLUTION.get(var.source, "unknown"),
            "available": reason is None,
        }
        if reason is not None:
            row["reason"] = reason
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- get_series


def get_series(session: Session, var_id: str, start: int | None = None, end: int | None = None) -> dict:
    start = session.start if start is None else int(start)
    end = session.end if end is None else int(end)
    args = {"var_id": var_id, "start": start, "end": end}
    return _through_ledger(session, "get_series", args, lambda: _fetch(session, var_id, start, end))


def _not_available(reason: str, **extra) -> dict:
    return {"status": "not_available", "reason": reason, **extra}


def _fetch(session: Session, var_id: str, start: int, end: int) -> dict:
    var = _variable(session, var_id)
    if var is None:
        return _not_available(f"unknown variable {var_id!r}; call list_variables", var_id=var_id)
    if start > end:
        return _not_available("start year is after end year", var_id=var_id)
    reason = _unavailable_reason(session, var)
    if reason is not None:
        return _not_available(reason, var_id=var_id)
    fetcher = gather.FETCHERS.get(var.source)
    if fetcher is None:
        return _not_available(f"source {var.source!r} is not supported", var_id=var_id)
    try:
        raw = fetcher(session.place.as_site(), (var,), session.catalog, start, end)
    except Exception as exc:  # noqa: BLE001 - a failing source is a result, not a crash
        logger.warning("get_series %s failed: %s: %s", var_id, type(exc).__name__, exc)
        source = gather.SOURCES.get(var.source)
        return _not_available(source.failure if source else "the data source did not answer", var_id=var_id)
    series = raw.get(var_id)
    if series is None or series.dropna().empty:
        return _not_available(f"no data for {var.label} here in {start}-{end}", var_id=var_id)
    series = gather.conform(series, start, end).rename(var_id)
    series_id = f"{var_id}:{start}-{end}"
    session.series[series_id] = series
    annual = series.groupby(series.index.year).mean().dropna()
    return {
        "status": "ok",
        "series_id": series_id,
        "var_id": var_id,
        "label": var.label,
        "unit": var.units,
        "n_months": int(series.notna().sum()),
        "years": [start, end],
        "chart": [{"year": int(y), "value": _num(v)} for y, v in annual.items()],
    }


# --------------------------------------------------------------------------- trend_test


def trend_test(session: Session, series_id: str, start: int | None = None, end: int | None = None) -> dict:
    series = session.series.get(series_id)
    if series is None:
        return _not_available(f"unknown series_id {series_id!r}; call get_series first")
    first, last = int(series.index.year.min()), int(series.index.year.max())
    start = first if start is None else max(int(start), first)
    end = last if end is None else min(int(end), last)
    args = {"series_id": series_id, "start": start, "end": end}
    return _through_ledger(session, "trend_test", args, lambda: _trend(session, series, series_id, start, end))


def _trend(session: Session, series: pd.Series, series_id: str, start: int, end: int) -> dict:
    if start > end:
        return _not_available("start year is after end year")
    var_id = str(series.name or series_id.split(":")[0])
    var = _variable(session, var_id)
    window = series.loc[f"{start}-01-01":f"{end}-12-01"]
    anomalies = monthly_anomalies(window)
    res = mk_trend_test(anomalies)
    test_id = f"t{session.ledger.n_tests + 1}"
    session.ledger.add_test(
        TestRecord(
            id=test_id,
            var_id=var_id,
            label=var.label if var else var_id,
            kind="trend",
            p_value=res.p_value,
            slope=None if res.too_short else res.sen_slope_per_decade,
            too_short=res.too_short,
            result=res,
        )
    )
    q, verdict, direction = session.ledger.corrected()[test_id]
    unit = f"{var.units} per decade" if var else "per decade"
    slope = None if res.too_short else res.sen_slope_per_decade
    return {
        "test_id": test_id,
        "series_id": series_id,
        "var_id": var_id,
        "years": [start, end],
        "n_months": res.n_months,
        "too_short": res.too_short,
        "slope_per_decade": _num(slope),
        "ci_low": _num(res.ci_low),
        "ci_high": _num(res.ci_high),
        "unit": unit,
        "p_value": _num(res.p_value),
        "q_session": _num(q),
        "verdict": str(verdict),
        "direction": str(direction),
        "years_needed": years_needed(anomalies, slope),
        "n_tests_so_far": session.ledger.n_tests,
    }
