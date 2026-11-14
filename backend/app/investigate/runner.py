"""Run an investigation: place -> land cover -> plan -> steps -> verified summary.

`investigate()` is a generator of events ({"event": name, "data": {...}}) so the API can
stream progress as Server-Sent Events. Every step is independent: one failing step sends
`step_failed` with a plain-English message and the investigation goes on.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field

import pandas as pd

from app.catalog import Variable, load_catalog
from app.explain.llm import LLM
from app.explain.narrative import explain_report
from app.gather import GatherResult, gather_site_series
from app.investigate import landcover, thennow
from app.investigate.menu import FINAL_STEP, PlannedStep
from app.investigate.planner import make_plan
from app.site_export import variable_rows
from app.site_report import report_from_gathered
from app.site_story import round_floats
from app.sites import Site, load_sites

logger = logging.getLogger(__name__)

LAND_COVER_YEARS = (2003, 2023)  # MCD12Q1 on GIBS ends in 2023
GRACE_FOOTPRINT_KM = 300
STEP_SOURCES: Mapping[str, frozenset[str]] = {
    "climate": frozenset({"power"}),
    "water_storage": frozenset({"grace"}),
    "soil_and_runoff": frozenset({"gldas"}),
}
FAILED = {
    "land_cover": "We could not read NASA land cover for this point. The rest of the investigation goes on.",
    "climate": "NASA POWER did not answer. Try again in a few minutes.",
    "water_storage": "We could not read the GRACE water-storage data. Try again in a few minutes.",
    "soil_and_runoff": "NASA GES DISC (GLDAS) did not answer. Try again later.",
    "then_and_now": "NASA GIBS did not send usable pictures for this point.",
    FINAL_STEP: "We could not write the summary.",
}

Event = dict
GatherFn = Callable[[Site, Sequence[Variable], int, int], GatherResult]


@dataclass
class _State:
    site: Site
    start: int
    end: int
    catalog: tuple[Variable, ...]
    series: dict[str, pd.Series] = field(default_factory=dict)
    missing: dict[str, str] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)
    land_cover: dict | None = None

    def merged(self) -> GatherResult:
        return GatherResult(series=dict(self.series), missing=dict(self.missing), sources=tuple(self.sources))

    def report(self) -> dict:
        return report_from_gathered(self.site, self.catalog, self.start, self.end, self.merged())


def _event(kind: str, **data: object) -> Event:
    return {"event": kind, "data": data}


def point_site(lat: float, lon: float, tags: Sequence[str]) -> Site:
    return Site(
        id="point",
        name=f"Point {lat:.3f}, {lon:.3f}",
        bbox=landcover.box_around(lat, lon),
        point=(lon, lat),
        tags=tuple(tags),
    )


def _land_cover(lat: float, lon: float) -> dict:
    before, after = landcover.land_cover_pair(lat, lon, LAND_COVER_YEARS)
    return {
        "before": before.to_dict(),
        "after": after.to_dict(),
        "changes": landcover.share_changes(before, after),
        "tags": list(landcover.tags_for(after.shares)),
        "source": landcover.SOURCE,
        "status": "analysed",
        "layer": {
            "kind": "wms",
            "layer": landcover.LAYER,
            "bbox": list(landcover.box_around(lat, lon)),
            "years": list(LAND_COVER_YEARS),
        },
    }


def _gather_step(state: _State, step_id: str, gather: GatherFn) -> dict:
    wanted = STEP_SOURCES[step_id]
    subset = tuple(v for v in state.catalog if v.source in wanted)
    got = gather(state.site, subset, state.start, state.end)
    state.series.update(got.series)
    state.missing.update(got.missing)
    state.sources.extend(s for s in got.sources if s not in state.sources)
    report = state.report()
    ids = {v.id for v in subset}
    rows = [r for r in report["variables"] if r["id"] in ids]
    payload: dict = {
        "variables": round_floats(variable_rows(rows, state.series)),
        "missing": {k: v for k, v in got.missing.items() if k in ids},
        "status": "analysed",
        "sources": [s for s in report["sources"] if s["id"] in wanted],
    }
    if step_id == "water_storage":
        payload["layer"] = {"kind": "footprint", "center": [state.site.lon, state.site.lat], "width_km": GRACE_FOOTPRINT_KM}
    else:
        payload["layer"] = {"kind": "point", "center": [state.site.lon, state.site.lat]}
    return payload


def _run_step(
    planned: PlannedStep, state: _State, lat: float, lon: float, llm: LLM | None, gather: GatherFn
) -> dict:
    sid = planned.id
    if sid == "land_cover":
        return state.land_cover or _land_cover(lat, lon)
    if sid in STEP_SOURCES:
        return _gather_step(state, sid, gather)
    if sid == "then_and_now":
        return thennow.then_and_now(lat, lon, (state.start, state.end), state.site.tags)
    if sid == FINAL_STEP:
        report = state.report()
        if not report["variables"]:
            return {"text": None, "source": None, "note": "No measured trend to summarise for this point."}
        return explain_report(report, llm).to_dict()
    raise KeyError(sid)


def investigate(
    question: str,
    lat: float | None = None,
    lon: float | None = None,
    site_id: str | None = None,
    llm: LLM | None = None,
    gather: GatherFn = gather_site_series,
    land_cover_fn: Callable[[float, float], dict] = _land_cover,
) -> Iterator[Event]:
    """Yield the investigation events. Exactly one of (lat, lon) or site_id is used."""
    catalog_sites = load_sites()
    start, end = catalog_sites.study_period
    site = catalog_sites.get(site_id) if site_id else None
    if site is not None:
        lat, lon = site.lat, site.lon
    if lat is None or lon is None:
        raise ValueError("give a site_id or a lat/lon")

    # 1. What kind of place: drives the plan and which variables apply.
    land: dict | None = None
    try:
        land = land_cover_fn(lat, lon)
    except Exception as exc:  # noqa: BLE001 - the plan falls back to a generic one
        logger.warning("land cover failed at %s,%s: %s: %s", lat, lon, type(exc).__name__, exc)
    tags = tuple(site.tags) if site is not None else tuple((land or {}).get("tags", ()))
    site = site or point_site(lat, lon, tags)
    yield _event("place", id=site.id, name=site.name, lat=lat, lon=lon, tags=list(tags), years=[start, end])

    # 2. Plan.
    plan = make_plan(question, site.name, tags, llm)
    yield _event("plan", **plan.to_dict())

    # 3. Steps.
    state = _State(site=site, start=start, end=end, catalog=load_catalog(), land_cover=land)
    for i, planned in enumerate(plan.steps):
        yield _event("step_start", index=i, id=planned.id, title=planned.step.title)
        t0 = time.monotonic()
        try:
            result = _run_step(planned, state, lat, lon, llm, gather)
        except Exception as exc:  # noqa: BLE001 - one failing step must not end the investigation
            logger.warning("step %s failed: %s: %s", planned.id, type(exc).__name__, exc)
            yield _event("step_failed", index=i, id=planned.id, message=FAILED.get(planned.id, "This step failed."))
            continue
        yield _event("step_done", index=i, id=planned.id, seconds=round(time.monotonic() - t0, 1), result=result)
    yield _event("done", site=site.id)
