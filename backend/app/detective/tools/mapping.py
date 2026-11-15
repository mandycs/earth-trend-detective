"""Map tools of the detective: instructions for the MapLibre map, streamed to the front.

Each call appends one op to `session.map` (`show_layer`, `set_year`, `show_before_after`,
`fly_to`, `show_footprint`). They are instructions, not evidence: never cached by the
ledger, they log no tests, and what they return to the model carries no measured figures (legend
ranges go to the front through the layer catalog, not to the model). The only numbers in them are
years: a `show_layer` without a date returns the `year` it chose (with `year_note`), and the ops
carry the years and boxes they were given.

Valid layer ids: `catalog/map_layers.yaml` (GIBS layers, checked against the GIBS
capabilities) plus, inside a solved case, the ids of `sites/<id>/layers.json`.

The map also follows the investigation on its own:
- `auto_fly_to`: when the place is profiled, the camera flies to it (pitch 55) unless it already moved;
- `show_layer` with no date and no year shows the last year of the most recent tested period (else
  the investigation's end year), when the layer has that year;
- `case_layer_rows`: inside a solved case, its own layers (e.g. `trend_lst_day`, `before_after`).
"""

from __future__ import annotations

import json
import math
import re
from datetime import date as Date
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from app import layers
from app.detective.cells import CELL_KM
from app.detective.session import Session

MAP_LAYERS_PATH = Path(__file__).resolve().parents[3] / "catalog" / "map_layers.yaml"
ZONES = frozenset({"any", "farmland", "water", "snow", "city", "fire", "sea"})
DEFAULT_OPACITY = 0.8
MAX_PITCH = 85.0  # MapLibre's limit
FOOTPRINT_KM = CELL_KM
FOOTPRINT_LABEL = {
    "grace": "GRACE water storage approximate data cell",
    "power": "NASA POWER weather approximate data cell",
    "gldas": "GLDAS land model approximate data cell",
}
FOOTPRINT_NOTE = "One value covers this whole cell, not the exact point; the outline is approximate."
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_SITE_ID_RE = re.compile(r"[a-z0-9_]+")
_KM_PER_DEG = 111.32
AUTO_PITCH = 55.0
AUTO_FLY_NOTE = "The map camera flew to the place."
TESTED_YEAR_NOTE = "No date was given: the map shows the last year of the tested period."
_CASE_YEARLY = "yearly"


def _rejected(reason: str) -> dict:
    return {"status": "rejected", "reason": reason}


@cache
def _load(path: Path) -> dict[str, dict]:
    rows = yaml.safe_load(path.read_text(encoding="utf-8"))["layers"]
    return {row["id"]: row for row in rows}


def load_map_layers(path: Path = MAP_LAYERS_PATH) -> dict[str, dict]:
    """Layer catalog by id (a copy: callers may not mutate the cached one)."""
    return {k: dict(v) for k, v in _load(path).items()}


def _case_layers(session: Session) -> dict[str, dict]:
    site_id = session.place.site_id
    if not site_id or not _SITE_ID_RE.fullmatch(site_id):
        return {}
    path = layers.SITES_DIR / site_id / "layers.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8")).get("layers", [])
    except (OSError, ValueError):
        return {}
    return {str(r["id"]): r for r in rows if isinstance(r, dict) and r.get("id")}


def _date_problem(row: dict, date: str | None, year: int | None, today: Date | None = None) -> str | None:
    """Why this day or year is not on the layer (None: it is). An ongoing layer ends today."""
    dates = row.get("dates") or {}
    start, end = Date.fromisoformat(str(dates["start"])), Date.fromisoformat(str(dates["end"]))
    last = (today or Date.today()) if dates.get("ongoing") else end
    covers = f"this layer covers {start.isoformat()} to {'now' if dates.get('ongoing') else end.isoformat()}"
    if date is not None and year is not None:
        return "give a date or a year, not both"
    if date is not None:
        if not _DATE_RE.fullmatch(date):
            return "date must be YYYY-MM-DD"
        try:
            day = Date.fromisoformat(date)
        except ValueError:
            return "date must be YYYY-MM-DD"
        return covers if not start <= day <= last else None
    if year is not None:
        if dates.get("years") and int(year) not in dates["years"]:
            return f"this layer only has the years {', '.join(map(str, dates['years']))}"
        return covers if not start.year <= int(year) <= last.year else None
    return None


def _describe(layer_id: str, row: dict, case: bool) -> dict:
    if case:
        source = row.get("source") or {}
        return {
            "layer_id": layer_id,
            "title": row.get("title", layer_id),
            "source": source.get("name") if isinstance(source, dict) else str(source),
            "status_of_layer": row.get("status"),
        }
    return {
        "layer_id": layer_id,
        "title": row["title"],
        "source": row["source"],
        "resolution": row["resolution"],
        "unit": row["legend"]["unit"],
    }


def _find(session: Session, layer_id: str) -> tuple[dict | None, bool]:
    catalog = load_map_layers()
    if layer_id in catalog:
        return catalog[layer_id], False
    case = _case_layers(session)
    if layer_id in case:
        return case[layer_id], True
    return None, False


def tested_year(session: Session) -> int:
    """Last year of the most recent tested period (a test result with `years`), else the investigation's end."""
    for result in reversed(list(session.ledger.results.values())):
        years = result.get("years")
        if (result.get("test_id") or result.get("test_ids")) and isinstance(years, list) and len(years) == 2:
            try:
                return int(years[1])
            except (TypeError, ValueError):
                continue
    return int(session.end)


def _default_year(session: Session, row: dict, is_case: bool) -> int | None:
    """The tested year when this layer has it (a case layer only when it is yearly)."""
    year = tested_year(session)
    if is_case:
        years = row.get("years") or []
        return year if row.get("kind") == _CASE_YEARLY and year in years else None
    return None if _date_problem(row, None, year) else year


def show_layer(
    session: Session, layer_id: str, date: str | None = None, year: int | None = None, opacity: float = DEFAULT_OPACITY
) -> dict:
    row, is_case = _find(session, layer_id)
    if row is None:
        return _rejected("unknown layer")
    if not is_case:
        problem = _date_problem(row, date, year)
        if problem:
            return _rejected(problem)
    defaulted = False
    if date is None and year is None:
        year = _default_year(session, row, is_case)
        defaulted = year is not None
    try:
        alpha = min(max(float(opacity), 0.0), 1.0)
    except (TypeError, ValueError):
        alpha = DEFAULT_OPACITY
    op: dict[str, Any] = {"op": "show_layer", "layer_id": layer_id}
    if date is not None:
        op["date"] = date
    if year is not None:
        op["year"] = int(year)
    op["opacity"] = alpha
    session.map.append(op)
    out = {"status": "shown", **_describe(layer_id, row, is_case)}
    if defaulted:
        out |= {"year": int(year), "year_note": TESTED_YEAR_NOTE}
    return out


def set_year(session: Session, year: int) -> dict:
    session.map.append({"op": "set_year", "year": int(year)})
    return {"status": "shown", "note": "The year slider of the map moved."}


def show_before_after(session: Session, layer_id: str, year_a: int, year_b: int) -> dict:
    row, is_case = _find(session, layer_id)
    if row is None:
        return _rejected("unknown layer")
    if int(year_a) == int(year_b):
        return _rejected("the two years are the same")
    if not is_case:
        problem = _date_problem(row, None, year_a) or _date_problem(row, None, year_b)
        if problem:
            return _rejected(problem)
    session.map.append({"op": "show_before_after", "layer_id": layer_id, "year_a": int(year_a), "year_b": int(year_b)})
    return {"status": "shown", **_describe(layer_id, row, is_case), "note": "A curtain to compare two years by eye."}


def _bbox(raw: Any) -> list[float] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    try:
        w, s, e, n = (float(v) for v in raw)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in (w, s, e, n)):
        return None
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        return None
    return [w, s, e, n]


def fly_to(session: Session, bbox: list[float], pitch: float = 55, bearing: float = 0) -> dict:
    box = _bbox(bbox)
    if box is None:
        return _rejected("bbox must be [min_lon, min_lat, max_lon, max_lat] with min < max, in degrees")
    tilt = min(max(float(pitch), 0.0), MAX_PITCH)
    session.map.append({"op": "fly_to", "bbox": box, "pitch": tilt, "bearing": float(bearing) % 360.0})
    return {"status": "shown", "note": "The map camera moved."}


def auto_fly_to(session: Session) -> bool:
    """Fly the camera to the place (pitch 55) unless it already moved; True when it flew."""
    if any(op.get("op") == "fly_to" for op in session.map):
        return False
    return fly_to(session, list(session.place.bbox), pitch=AUTO_PITCH).get("status") == "shown"


def case_layer_rows(session: Session) -> list[dict]:
    """The solved case's own layers ({layer_id, title, kind}), empty outside a case."""
    return [
        {"layer_id": layer_id, "title": str(row.get("title") or layer_id), "kind": str(row.get("kind") or "")}
        for layer_id, row in _case_layers(session).items()
    ]


def show_footprint(session: Session, source: str) -> dict:
    km = FOOTPRINT_KM.get(source)
    if km is None:
        return _rejected(f"unknown source; use one of {', '.join(FOOTPRINT_KM)}")
    p = session.place
    half_lat = km / 2 / _KM_PER_DEG
    half_lon = km / 2 / (_KM_PER_DEG * max(math.cos(math.radians(p.lat)), 0.01))
    box = [
        max(p.lon - half_lon, -180.0),
        max(p.lat - half_lat, -90.0),
        min(p.lon + half_lon, 180.0),
        min(p.lat + half_lat, 90.0),
    ]
    size = f"~{km:.0f} km"
    session.map.append(
        {
            "op": "show_footprint",
            "source": source,
            "label": f"{FOOTPRINT_LABEL[source]} ({size})",
            "size": size,
            "bbox": [round(v, 4) for v in box],
            "approximate": True,
        }
    )
    return {"status": "shown", "source": source, "size": size, "note": FOOTPRINT_NOTE}
