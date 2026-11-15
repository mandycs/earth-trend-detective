"""First tools of the detective: profile the place, list variables, fetch a series, trend-test it.

Every tool goes through the session ledger: an identical call returns the cached result with
its evidence id instead of re-running (and never logs a second test). Failures caused by a
source that did not answer are returned but not cached, so a retry can succeed. No tool
raises: anything unexpected becomes `status: not_available` with a plain reason.
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
from app.detective.place import Place
from app.detective.session import Session
from app.extractors import erddap, gibs_values
from app.investigate import landcover
from app.investigate.runner import LAND_COVER_YEARS
from app.stats.annual import annual_trend, annual_years_needed, n_years, to_annual
from app.stats.deseason import monthly_anomalies
from app.stats.trend import trend_test as mk_trend_test
from app.stats.years import years_needed

logger = logging.getLogger(__name__)

APPEEARS_SOURCES = frozenset({"appeears", "appeears_water"})
OFF_CASE_REASON = "not_available_here: only precomputed for the solved cases"
EXTRA_DRIVER_REASON = "not_available_here: only set up for the solved cases that need it"
UNKNOWN_CASE_REASON = "not_available_here: this solved case is not in the site list"
SOURCE_DOWN_REASON = "The data source did not answer. Try again in a few minutes."
NOT_SEA_REASON = "not_available_here: a sea variable; this place is on land"
NOT_REEF_REASON = "not_available_here: heat stress on corals; only offered on reef coasts (within 30° of the equator)"
ON_CASE_TWIN_REASON = "not_available_here: this solved case has the monthly series of this variable"
# AppEEARS variables (solved cases only) and their GIBS yearly twin, offered everywhere else.
# No snow twin: GIBS draws no-snow and unseen ground with the same transparent pixel.
GIBS_TWINS: Mapping[str, str] = {"ndvi": "ndvi_gibs", "lst_day": "lst_gibs"}
SNOW_GIBS_REASON = (
    "not_available_here: GIBS shows no-snow and unseen ground the same way, "
    "so a snow trend can't be measured honestly from it"
)
# Catalog variables kept (fetcher code stays) but never offered, with the reason why.
WITHDRAWN: Mapping[str, str] = {"snow_gibs": SNOW_GIBS_REASON}
TWIN_OF: Mapping[str, str] = {twin: base for base, twin in GIBS_TWINS.items()}
SEA_TAGS = frozenset({"ocean", "coast", "reef"})
ANNUAL = "annual"
NOT_THIS_PLACE_REASON = "not_available_here: this variable does not apply to this kind of place (see profile_place tags)"
NO_COMPLETED_YEAR_REASON = "no completed year in this range"
GRACE_AT_SEA_REASON = "measures water stored on land; over open sea it is not meaningful"
LAND_AT_SEA_REASON = "not_available_here: a land-only source; this place is open sea"
SEA_MAX_ELEVATION_M = -5.0  # a box whose lowest point is at or below this is sea; lakes sit above it
OPEN_SEA_WATER_SHARE = 0.95  # at least this much water: land-only sources are hidden
LAND_ONLY_SOURCES = APPEEARS_SOURCES | {"gldas", "gibs"}
# Native grid of each catalog dataset (matched on the `dataset` prefix in variables.yaml).
DATASET_RESOLUTION: tuple[tuple[str, str], ...] = (
    ("NASA POWER", "~50 km"),
    ("TELLUS_GRAC", "~300 km"),
    ("GLDAS_NOAH025", "~25 km"),
    ("MOD13A3", "~1 km"),
    ("MOD11A2", "~1 km"),
    ("MOD09A1", "~500 m"),
    ("MOD10A1", "~500 m"),
)
NATIVE_RESOLUTION = "dataset native resolution"
DATA_CELLS = {"grace": "~300 km", "power": "~50 km"}
_TRANSIENT = "_transient"  # marks a failure that must not be cached


def _num(x: float | None, ndigits: int = 4) -> float | None:
    if x is None or not math.isfinite(x):
        return None
    return round(float(x), ndigits)


def resolution_of(var: Variable) -> str:
    if var.resolution:
        return var.resolution
    return next((r for prefix, r in DATASET_RESOLUTION if var.dataset.startswith(prefix)), NATIVE_RESOLUTION)


def _through_ledger(
    session: Session,
    tool: str,
    args: Mapping,
    compute: Callable[[], dict],
    on_hit: Callable[[dict], dict] | None = None,
) -> dict:
    key = session.ledger.call_key(tool, args)
    hit = session.ledger.cached(key)
    if hit is not None:
        return on_hit(hit) if on_hit else hit
    before = set(session.ledger.test_ids())
    result = compute()
    session.ledger.claim_tests(key, before)  # the tests this call logged get a key stable across branches
    if result.pop(_TRANSIENT, False):
        # A source failure: shown, never cached, so a retry can succeed. The public flag lets
        # tools built on top (residual, compare) also skip caching their own result.
        return {**result, "transient": True}
    eid = session.ledger.remember(key, result)
    return {**result, "evidence_id": eid}


def _not_available(reason: str, transient: bool = False, **extra) -> dict:
    out = {"status": "not_available", "reason": reason, **extra}
    if transient:
        out[_TRANSIENT] = True
    return out


def _variable(session: Session, var_id: str) -> Variable | None:
    return next((v for v in session.catalog if v.id == var_id), None)


def _extra_driver_ids(session: Session) -> frozenset[str]:
    """Opt-in drivers (upstream, snow) the place has; raises ValueError for an unknown case."""
    return frozenset(v.id for v in gather.site_extra_drivers(session.place.as_site(), session.catalog))


def _is_opt_in(var: Variable) -> bool:
    return var.role == "driver" and not var.applies_to


def _open_sea_reason(session: Session, var: Variable) -> str | None:
    """Why `var` makes no sense over open sea (None when it does): one predicate for the
    listing and for fetching, so they cannot disagree."""
    if not _open_sea(session):
        return None
    if var.source in LAND_ONLY_SOURCES:
        return LAND_AT_SEA_REASON
    if var.source == "grace":
        return GRACE_AT_SEA_REASON
    return None


def _sea_reason(session: Session, var: Variable) -> str | None:
    """A sea variable whose zone tags the place lacks: on land, or at sea but off a reef."""
    if var.source != "erddap" or not var.applies_to or set(var.applies_to) & set(session.place.tags):
        return None
    return NOT_REEF_REASON if SEA_TAGS & set(session.place.tags) else NOT_SEA_REASON


def _hidden_twin(session: Session, var: Variable) -> bool:
    """One of a pair is never listed: the GIBS twin inside a solved case, the AppEEARS
    variable outside one."""
    if session.place.site_id is not None:
        return var.id in TWIN_OF
    return var.id in GIBS_TWINS


def _unavailable_reason(session: Session, var: Variable, extra_ids: frozenset[str]) -> str | None:
    at_sea = _open_sea_reason(session, var)
    if at_sea is not None:
        return at_sea
    if var.id in WITHDRAWN:
        return WITHDRAWN[var.id]
    sea = _sea_reason(session, var)
    if sea is not None:
        return sea
    if var.id in TWIN_OF and session.place.site_id is not None:
        return ON_CASE_TWIN_REASON
    if var.source in APPEEARS_SOURCES and session.place.site_id is None:
        return OFF_CASE_REASON
    if _is_opt_in(var) and var.id not in extra_ids:
        return EXTRA_DRIVER_REASON
    if var.applies_to and not variables_for_site((var,), session.place.tags):
        return NOT_THIS_PLACE_REASON
    return None


# --------------------------------------------------------------------------- profile_place


def profile_place(session: Session) -> dict:
    place = session.place
    args = {"lat": place.lat, "lon": place.lon, "site_id": place.site_id}
    return _through_ledger(session, "profile_place", args, lambda: _profile(session))


def _is_sea(place: Place) -> bool:
    """True only with evidence: a free place (not a curated case) whose box has ground at or
    below -5 m (GEBCO). A lake or reservoir sits above sea level; a failed call means no sea tags."""
    if place.site_id is not None:
        return False
    try:
        return erddap.fetch_min_elevation(tuple(place.bbox)) <= SEA_MAX_ELEVATION_M
    except Exception as exc:  # noqa: BLE001 - never claim sea without evidence
        logger.warning("GEBCO failed at %s,%s: %s: %s", place.lat, place.lon, type(exc).__name__, exc)
        return False


def _profile(session: Session) -> dict:
    place = session.place
    try:
        cover = landcover.fetch_land_cover(place.lat, place.lon, LAND_COVER_YEARS[-1])
        sea = _is_sea(place)
        new_tags = tuple(
            dict.fromkeys(landcover.tags_for(cover.shares, lat=place.lat) + landcover.zone_tags(cover.shares, place.lat, sea=sea))
        )
        # Only a confirmed sea gets a water share. No classified pixel at all means open sea
        # (GIBS paints no land cover there), so that counts as 100 % water.
        water_share = (float(cover.shares.get(landcover.WATER_CLASS, 0.0)) if cover.shares else 1.0) if sea else None
    except Exception as exc:  # noqa: BLE001 - the place can still be investigated without land cover
        logger.warning("land cover failed at %s,%s: %s: %s", place.lat, place.lon, type(exc).__name__, exc)
        return {
            "tags": list(place.tags),
            "land_cover": {},
            "dominant": None,
            "data_cells": dict(DATA_CELLS),
            "land_cover_status": "not_available",
            _TRANSIENT: True,
        }
    tags = tuple(dict.fromkeys(place.tags + new_tags))
    session.place = replace(place, tags=tags, water_share=water_share)
    return {
        "tags": list(tags),
        "land_cover": {k: _num(v, 3) for k, v in cover.shares.items()},
        "dominant": cover.dominant,
        "land_cover_year": cover.year,
        "data_cells": dict(DATA_CELLS),
    }


# --------------------------------------------------------------------------- list_variables


def list_variables(session: Session) -> dict:
    args = {"tags": list(session.place.tags), "site_id": session.place.site_id, "open_sea": _open_sea(session)}
    return _through_ledger(session, "list_variables", args, lambda: _list(session))


def _list(session: Session) -> dict:
    try:
        return {"variables": _rows(session)}
    except ValueError as exc:  # unknown solved case: an input error, safe to cache
        logger.warning("list_variables: %s", exc)
        return _not_available(UNKNOWN_CASE_REASON)
    except Exception as exc:  # noqa: BLE001 - never a stack trace to the model
        logger.warning("list_variables failed: %s: %s", type(exc).__name__, exc)
        return _not_available(SOURCE_DOWN_REASON, transient=True)


def _open_sea(session: Session) -> bool:
    share = session.place.water_share
    return share is not None and share >= OPEN_SEA_WATER_SHARE


def _rows(session: Session) -> list[dict]:
    extra_ids = _extra_driver_ids(session)
    open_sea = _open_sea(session)
    applicable = variables_for_site(session.catalog, session.place.tags)
    opt_in = tuple(v for v in session.catalog if _is_opt_in(v) and v not in applicable)
    off_sea = tuple(v for v in session.catalog if v.source == "erddap" and v.applies_to and v not in applicable)
    rows = []
    for var in applicable + opt_in + off_sea:
        if open_sea and var.source in LAND_ONLY_SOURCES:
            continue  # land models and land sensors say nothing over open sea
        if _hidden_twin(session, var):
            continue  # the other one of the pair is listed instead (get_series refuses this one)
        reason = _unavailable_reason(session, var, extra_ids)
        row = {
            "id": var.id,
            "label": var.label,
            "definition": var.definition,
            "role": var.role,
            "source": var.source,
            "resolution": resolution_of(var),
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
    return _through_ledger(
        session,
        "get_series",
        args,
        lambda: _fetch(session, var_id, start, end),
        on_hit=lambda hit: _ensure_loaded(session, hit, var_id, start, end),
    )


def _ensure_loaded(session: Session, hit: dict, var_id: str, start: int, end: int) -> dict:
    """A cached `ok` whose series is gone (a restored thread without it in the store): fetch it
    again under the same evidence id. A failed re-fetch is returned as is, never cached."""
    series_id = hit.get("series_id")
    if hit.get("status") != "ok" or series_id is None or series_id in session.series:
        return hit
    again = _fetch(session, var_id, start, end)
    if again.pop(_TRANSIENT, False):
        return {**again, "transient": True}
    if again.get("status") != "ok" or series_id not in session.series:
        return again
    return hit


def _fetch(session: Session, var_id: str, start: int, end: int) -> dict:
    var = _variable(session, var_id)
    if var is None:
        return _not_available(f"unknown variable {var_id!r}; call list_variables", var_id=var_id)
    if start > end:
        return _not_available("start year is after end year", var_id=var_id)
    try:
        extra_ids = _extra_driver_ids(session)
    except ValueError:
        return _not_available(UNKNOWN_CASE_REASON, var_id=var_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_series %s: site setup failed: %s: %s", var_id, type(exc).__name__, exc)
        return _not_available(SOURCE_DOWN_REASON, transient=True, var_id=var_id)
    reason = _unavailable_reason(session, var, extra_ids)
    if reason is not None:
        twin = GIBS_TWINS.get(var_id) if reason == OFF_CASE_REASON else None
        return _not_available(reason, var_id=var_id, **({"use_instead": twin} if twin else {}))
    if var.source == "gibs" and start > gibs_values.last_complete_year():
        return _not_available(NO_COMPLETED_YEAR_REASON, var_id=var_id)  # a plain answer, not a failure
    fetcher = gather.FETCHERS.get(var.source)
    if fetcher is None:
        return _not_available(f"source {var.source!r} is not supported", var_id=var_id)
    try:
        raw = fetcher(session.place.as_site(), (var,), session.catalog, start, end)
        series = raw.get(var_id) if isinstance(raw, Mapping) else None
        attrs = dict(series.attrs) if isinstance(series, pd.Series) else {}
        yearly = var.temporal == ANNUAL or attrs.get("temporal") == ANNUAL
        if series is not None:
            series = (to_annual(series, start, end) if yearly else gather.conform(series, start, end)).rename(var_id)
            if yearly:  # kept with the series (and its store copy) for the annual trend path
                series.attrs = {"temporal": ANNUAL, **{k: attrs[k] for k in ("precision", "caveat") if attrs.get(k)}}
    except Exception as exc:  # noqa: BLE001 - a failing source is a result, not a crash
        logger.warning("get_series %s failed: %s: %s", var_id, type(exc).__name__, exc)
        source = gather.SOURCES.get(var.source)
        return _not_available(source.failure if source else SOURCE_DOWN_REASON, transient=True, var_id=var_id)
    if series is None or series.dropna().empty:
        return _not_available(f"no data for {var.label} here in {start}-{end}", var_id=var_id)
    series_id = f"{var_id}:{start}-{end}"
    session.series[series_id] = series
    annual = series.groupby(series.index.year).mean().dropna()
    extra: dict = {}
    if yearly:
        extra["basis"] = ANNUAL
        extra |= {k: attrs[k] for k in ("precision", "caveat") if attrs.get(k)}
        if attrs.get("dropped_years"):  # years GIBS showed no clear picture for
            extra["dropped_years"] = [int(y) for y in attrs["dropped_years"]]
    if attrs.get("cell") is not None:  # the grid cell actually used (ERDDAP may move a masked one)
        extra["cell"] = [_num(c) for c in attrs["cell"]]
    if attrs.get("missing_years"):  # years the source failed on, kept as gaps
        extra["missing_years"] = [int(y) for y in attrs["missing_years"]]
    return {
        "status": "ok",
        "series_id": series_id,
        "var_id": var_id,
        "label": var.label,
        "unit": var.units,
        **({"n_years": n_years(series)} if yearly else {"n_months": int(series.notna().sum())}),
        "years": [start, end],
        "chart": [{"year": int(y), "value": _num(v)} for y, v in annual.items()],
        **extra,
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
    return _through_ledger(
        session,
        "trend_test",
        args,
        lambda: _trend_safe(session, series, series_id, start, end),
        on_hit=lambda hit: _refresh(session, hit),
    )


def _corrected_fields(session: Session, test_id: str) -> dict:
    q, verdict, direction = session.ledger.corrected()[test_id]
    return {
        "q_session": _num(q),
        "verdict": str(verdict),
        "direction": str(direction),
        "n_tests_so_far": session.ledger.n_finite(),
    }


def _refresh(session: Session, hit: dict) -> dict:
    """A repeated call: same test, but q and verdict reflect every test logged since."""
    test_id = hit.get("test_id")
    if test_id is None:
        return hit
    return {**hit, **_corrected_fields(session, test_id)}


def _trend_safe(session: Session, series: pd.Series, series_id: str, start: int, end: int) -> dict:
    try:
        return _trend(session, series, series_id, start, end)
    except Exception as exc:  # noqa: BLE001 - never a stack trace to the model
        logger.warning("trend_test %s failed: %s: %s", series_id, type(exc).__name__, exc)
        return _not_available("the trend test could not run on this series", transient=True)


def is_annual(session: Session, series: pd.Series, series_id: str) -> bool:
    """One value per year: the catalog says so, or the stored series does."""
    var = _variable(session, str(series.name or series_id.split(":")[0]))
    return (var is not None and var.temporal == ANNUAL) or series.attrs.get("temporal") == ANNUAL


def _trend(session: Session, series: pd.Series, series_id: str, start: int, end: int) -> dict:
    if start > end:
        return _not_available("start year is after end year")
    var_id = str(series.name or series_id.split(":")[0])
    var = _variable(session, var_id)
    if is_annual(session, series, series_id):
        return _annual_trend(session, series, series_id, start, end, var_id, var)
    window = series.loc[f"{start}-01-01":f"{end}-12-01"]
    anomalies = monthly_anomalies(window)
    res = mk_trend_test(anomalies)
    slope = None if res.too_short else res.sen_slope_per_decade
    needed = years_needed(anomalies, slope)
    test_id = f"t{session.ledger.n_tests + 1}"
    session.ledger.add_test(
        TestRecord(
            id=test_id,
            var_id=var_id,
            label=var.label if var else var_id,
            kind="trend",
            p_value=res.p_value,
            slope=slope,
            too_short=res.too_short,
            result=res,
        )
    )
    return {
        "test_id": test_id,
        "series_id": series_id,
        "var_id": var_id,
        "basis": "monthly",
        "years": [start, end],
        "n_months": res.n_months,
        "too_short": res.too_short,
        "slope_per_decade": _num(slope),
        "ci_low": _num(res.ci_low),
        "ci_high": _num(res.ci_high),
        "unit": f"{var.units} per decade" if var else "per decade",
        "p_value": _num(res.p_value),
        "years_needed": needed,
        **_corrected_fields(session, test_id),
    }


def _annual_trend(
    session: Session, series: pd.Series, series_id: str, start: int, end: int, var_id: str, var: Variable | None
) -> dict:
    """Plain MK + Sen on one value per year. Counted in the session family like every test;
    marked `basis: "annual"` so it is never read together with monthly-anomaly tests."""
    window = series.loc[f"{start}-01-01":f"{end}-12-31"]
    res = annual_trend(window)
    slope = None if res.too_short else res.sen_slope_per_decade
    label = var.label if var else var_id
    if var is not None and var.source == "gibs":
        suffix = gibs_values.annual_suffix(gibs_values.layer_for(var))
    else:
        suffix = "yearly values"  # DHW: a yearly peak
    test_id = f"t{session.ledger.n_tests + 1}"
    session.ledger.add_test(
        TestRecord(
            id=test_id,
            var_id=var_id,
            label=label if suffix in label else f"{label} ({suffix})",
            kind="trend",
            p_value=res.p_value,
            slope=slope,
            too_short=res.too_short,
            result=res,
        )
    )
    extra = {k: series.attrs[k] for k in ("precision", "caveat") if series.attrs.get(k)}
    return {
        "test_id": test_id,
        "series_id": series_id,
        "var_id": var_id,
        "basis": ANNUAL,
        "status": "observed",
        "years": [start, end],
        "n_years": n_years(window),
        "too_short": res.too_short,
        "slope_per_decade": _num(slope),
        "ci_low": _num(res.ci_low),
        "ci_high": _num(res.ci_high),
        "unit": f"{var.units} per decade" if var else "per decade",
        "p_value": _num(res.p_value),
        "years_needed": annual_years_needed(window, res),
        **extra,
        **_corrected_fields(session, test_id),
    }
