"""Context tools of the detective: what the ground looks like and what solved cases found.

- `land_cover_change`: how the land-cover shares moved between two years (MODIS, 500 m).
- `satellite_picture`: a clear before/after picture of the place (visual only, no figures).
- `solved_case`: the precomputed result of one of the solved cases (no new tests logged).

Results that fail because a source failed are not remembered, so a retry can succeed.
"""

from __future__ import annotations

import json
import logging
import re

from app import layers
from app.detective.session import Session
from app.detective.tools import data
from app.investigate import landcover, thennow
from app.sites import load_sites

logger = logging.getLogger(__name__)

LAND_COVER_CAVEAT = "At 500 m, orchards and tree crops may be classed as savanna or woody vegetation, not cropland."
SITE_ID_RE = re.compile(r"^[a-z0-9_]+$")
CASE_VARIABLE_FIELDS = (
    "id",
    "label",
    "verdict",
    "direction",
    "sen_slope_per_decade",
    "ci_low",
    "ci_high",
    "residual_pct_non_climate",
    "residual_pct_range",
    "note",
)

_not_available = data._not_available


def land_cover_change(session: Session, year_a: int = 2003, year_b: int = 2023) -> dict:
    return data._through_ledger(
        session, "land_cover_change", {"year_a": year_a, "year_b": year_b}, lambda: _land_cover(session, year_a, year_b)
    ) | {"caveat": LAND_COVER_CAVEAT}


def _land_cover(session: Session, year_a: int, year_b: int) -> dict:
    if year_a == year_b:
        return _not_available("the two years are the same", caveat=LAND_COVER_CAVEAT)
    p = session.place
    try:
        before, after = landcover.land_cover_pair(p.lat, p.lon, (year_a, year_b))
    except Exception as exc:  # network / GIBS: a source failure, shown but not remembered
        logger.warning("land cover failed: %s", exc)
        return _not_available("the land cover source could not be reached", transient=True, caveat=LAND_COVER_CAVEAT)
    if not before.shares or not after.shares:
        return _not_available("no land cover data for this place and years", caveat=LAND_COVER_CAVEAT)
    session.map.append({"op": "show_layer", "layer_id": "land_cover", "year": year_b})
    return {
        "status": "ok",
        "year_a": year_a,
        "year_b": year_b,
        "dominant_before": before.dominant,
        "dominant_after": after.dominant,
        "changes": landcover.share_changes(before, after),
        "layer": "land_cover",
        "source": landcover.SOURCE,
        "caveat": LAND_COVER_CAVEAT,
    }


def satellite_picture(session: Session, year_a: int = 2003, year_b: int = 2024) -> dict:
    return data._through_ledger(
        session, "satellite_picture", {"year_a": year_a, "year_b": year_b}, lambda: _picture(session, year_a, year_b)
    )


def _picture(session: Session, year_a: int, year_b: int) -> dict:
    p = session.place
    try:
        pair = thennow.then_and_now(p.lat, p.lon, (year_a, year_b), p.tags)
    except Exception as exc:
        logger.warning("satellite picture failed: %s", exc)
        return _not_available("the satellite imagery source could not be reached", transient=True)
    before, after = pair.get("before"), pair.get("after")
    if before and after:
        session.map.append(
            {
                "op": "show_before_after",
                "layer_id": pair["layer"],
                "year_a": year_a,
                "year_b": year_b,
                "before_url": before["url"],
                "after_url": after["url"],
                "bbox": pair["bbox"],
            }
        )
    out = {**pair, "status": "visual_only"}
    out["note"] = "A picture to look at, not a measurement: no figure comes from it."
    return out


def solved_case(session: Session, site_id: str) -> dict:
    """Precomputed findings of a solved case; its tests were corrected inside the case, so none is logged."""
    return data._through_ledger(session, "solved_case", {"site_id": site_id}, lambda: _case(site_id))


def _case(site_id: str) -> dict:
    real = SITE_ID_RE.fullmatch(site_id or "") and load_sites().get(site_id) is not None
    path = layers.SITES_DIR / site_id / "site.json" if real else None
    if path is None or not path.is_file():
        return _not_available(f"no solved case {site_id!r}. Not a solved case.", site_id=site_id)
    try:
        site = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("solved case %s unreadable: %s", site_id, exc)
        return _not_available(f"solved case {site_id!r} could not be read", site_id=site_id)
    variables = [{k: v.get(k) for k in CASE_VARIABLE_FIELDS} for v in site.get("variables", [])]
    return {
        "status": "ok",
        "site_id": site_id,
        "name": site.get("name"),
        "headline": site.get("headline"),
        "variables": variables,
        "caveats": site.get("caveats", []),
        "precomputed": True,
    }
