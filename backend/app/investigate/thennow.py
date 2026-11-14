"""Quick then-and-now pictures for any point: the clearest MODIS day of the same season,
at the start and end of the period, as GIBS image URLs the browser loads directly.

Lighter than `assets/beforeafter.py` (one clear day, no median, nothing written to disk)
so it fits in a live investigation. Pictures only: `visual_only`.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor

import httpx

from app.assets.composite import THUMB_WIDTH, _get, bad_share
from app.assets.gibs import DEFAULT_LAYER, GIBS_WMS_URL, wms_params
from app.investigate.landcover import box_around

HALF_BOX_DEG = 0.2
DAY_STEP = 3
PICTURE_WIDTH = 1024
WORKERS = 8
TIMEOUT_S = 20.0
SNOW_TAGS = frozenset({"snow", "glacier"})


def season(lat: float, tags: Sequence[str]) -> tuple[tuple[int, int], tuple[int, int]]:
    """Local summer (least snow, fewest clouds in most places); late summer for ice."""
    north = lat >= 0
    if SNOW_TAGS & set(tags):
        return ((8, 1), (9, 30)) if north else ((2, 1), (3, 31))
    return ((6, 1), (8, 31)) if north else ((12, 1), (12, 31))


def candidate_dates(year: int, start: tuple[int, int], end: tuple[int, int], step: int = DAY_STEP) -> list[str]:
    d0, d1 = dt.date(year, *start), dt.date(year, *end)
    return [(d0 + dt.timedelta(days=i)).isoformat() for i in range(0, (d1 - d0).days + 1, step)]


def picture_url(bbox: Sequence[float], date: str, width: int = PICTURE_WIDTH, layer: str = DEFAULT_LAYER) -> str:
    return str(httpx.URL(GIBS_WMS_URL, params=wms_params(bbox, date, width, layer)))


def clearest_day(client: httpx.Client, bbox: Sequence[float], dates: Sequence[str]) -> tuple[str, float] | None:
    def score(date: str) -> tuple[float, str] | None:
        thumb = _get(client, bbox, date, THUMB_WIDTH // 4, DEFAULT_LAYER)
        return None if thumb is None else (bad_share(thumb), date)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        scored = [s for s in pool.map(score, dates) if s is not None]
    if not scored:
        return None
    best_score, best_date = min(scored)
    return best_date, best_score


def then_and_now(lat: float, lon: float, years: tuple[int, int], tags: Sequence[str]) -> dict:
    bbox = box_around(lat, lon, HALF_BOX_DEG)
    start, end = season(lat, tags)
    out: dict = {"layer": DEFAULT_LAYER, "bbox": list(bbox), "status": "visual_only"}
    with httpx.Client(timeout=TIMEOUT_S) as client:
        for side, year in zip(("before", "after"), years):
            best = clearest_day(client, bbox, candidate_dates(year, start, end))
            if best is None:
                out[side] = None
                continue
            date, bad = best
            out[side] = {"year": year, "date": date, "cloud_or_gap_share": round(bad, 2), "url": picture_url(bbox, date)}
    return out
