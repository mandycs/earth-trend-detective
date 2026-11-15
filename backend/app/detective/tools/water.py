"""`water_extent`: yearly open-water area of the place's box at 30 m (OPERA DSWx-HLS, via GIBS).

The series is stored in the session like a `get_series` result (`water_extent:<start>-<end>`,
one value per year, `temporal: "annual"`), so `trend_test` reads it on the annual path. The
area counts every lake, reservoir and river in the box, so a box that reaches the sea is
refused: the number would be mostly sea.
"""

from __future__ import annotations

import logging

from app.detective.session import Session
from app.detective.tools import data
from app.extractors import water_extent as wx
from app.stats.annual import n_years

logger = logging.getLogger(__name__)

VAR_ID = "water_extent"
LABEL = "Open water in the box"
UNIT = "km²"
DEFINITION = (
    "Area of open water in the place's box (OPERA open water, plus partial surface water at its edge), "
    "from 30 m Landsat and Sentinel-2 scenes; one clear scene a month, yearly median."
)
CAVEAT = (
    "Counts every lake, reservoir and river in the box; a partial-water pixel at the shore counts as a whole "
    "30 m pixel, scattered partial-water pixels away from open water are left out. "
    "OPERA has no scenes from mid-August 2020 to the end of 2022."
)
AT_SEA_REASON = "not_available_here: the box reaches the sea, so its water area would be mostly sea"
NO_YEARS_REASON = f"OPERA water maps start in {wx.FIRST_YEAR}; no completed year in this range"
FAILED_REASON = "The water maps (NASA GIBS / CMR) did not answer. Try again in a few minutes."


def water_extent(session: Session, year_a: int | None = None, year_b: int | None = None) -> dict:
    start = max(session.start, wx.FIRST_YEAR) if year_a is None else int(year_a)
    end = min(session.end, wx.last_complete_year()) if year_b is None else int(year_b)
    args = {"start": start, "end": end, "bbox": [round(float(c), 6) for c in session.place.bbox]}
    return data._through_ledger(
        session,
        "water_extent",
        args,
        lambda: _safe(session, start, end),
        on_hit=lambda hit: _ensure_loaded(session, hit, start, end),
    )


def _ensure_loaded(session: Session, hit: dict, start: int, end: int) -> dict:
    """A cached `ok` whose series is gone from the store: fetched again under the same evidence id."""
    series_id = hit.get("series_id")
    if hit.get("status") != "ok" or series_id is None or series_id in session.series:
        return hit
    again = _safe(session, start, end)
    if again.pop(data._TRANSIENT, False):
        return {**again, "transient": True}
    return hit if series_id in session.series else again


def _safe(session: Session, start: int, end: int) -> dict:
    try:
        return _water(session, start, end)
    except Exception as exc:  # noqa: BLE001 - never a stack trace to the model
        logger.warning("water_extent failed: %s: %s", type(exc).__name__, exc)
        return data._not_available("the water area could not be measured", transient=True, var_id=VAR_ID)


def _water(session: Session, start: int, end: int) -> dict:
    if start > end:
        return data._not_available("start year is after end year", var_id=VAR_ID)
    if data.SEA_TAGS & set(session.place.tags) or data._open_sea(session):
        return data._not_available(AT_SEA_REASON, var_id=VAR_ID)
    if max(start, wx.FIRST_YEAR) > min(end, wx.last_complete_year()):
        return data._not_available(NO_YEARS_REASON, var_id=VAR_ID)
    try:
        series = wx.fetch_yearly_water(session.place.bbox, start, end)
    except wx.WaterExtentError as exc:
        if exc.failed:
            return data._not_available(FAILED_REASON, transient=True, var_id=VAR_ID)
        return data._not_available(f"no year with enough clear scenes here in {start}-{end}", var_id=VAR_ID)
    attrs = dict(series.attrs)
    stored = series.rename(VAR_ID)
    stored.attrs = {"temporal": data.ANNUAL, "caveat": CAVEAT, "units": UNIT, "label": LABEL, "suffix": wx.METHOD}
    series_id = f"{VAR_ID}:{start}-{end}"
    session.series[series_id] = stored
    clear = attrs.get("clear_months") or {}
    yearly = [
        {"year": int(t.year), "area_km2": data._num(float(v), 2), "clear_months": int(clear.get(int(t.year), 0))}
        for t, v in series.items()
    ]
    out: dict = {
        "status": "ok",
        "series_id": series_id,
        "var_id": VAR_ID,
        "label": LABEL,
        "definition": DEFINITION,
        "unit": UNIT,
        "source": wx.SOURCE,
        "resolution": wx.RESOLUTION,
        "basis": data.ANNUAL,
        "method": wx.METHOD,
        "years": [start, end],
        "n_years": n_years(stored),
        "yearly": yearly,
        "chart": [{"year": row["year"], "value": row["area_km2"]} for row in yearly],
        "caveat": CAVEAT,
    }
    for key in ("no_scene_years", "dropped_years", "missing_years"):
        if attrs.get(key):
            out[key] = [int(y) for y in attrs[key]]
    if attrs.get("missing_years"):  # a partial answer is never cached: a retry can fill the gap
        out[data._TRANSIENT] = True
    return out
