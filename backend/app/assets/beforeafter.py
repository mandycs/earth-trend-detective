"""Then-and-now pictures for a site: the same season at the start and end of the study period.

MODIS Terra true colour (GIBS) is the only true-colour NASA layer that covers 2003, so
both pictures use it, at the same size, built the same way (median of the clearest days
of the season, see `composite.py`). They are pictures, not measurements: the layer is
`visual_only` in layers.json.

Usage (from backend/, venv active):
    python -m app.assets.beforeafter [site_id ...]
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Mapping
from pathlib import Path

from app.assets.composite import build_composite, native_width, season_dates
from app.assets.gibs import DEFAULT_LAYER
from app.sites import load_sites

logger = logging.getLogger(__name__)

SITES_DIR = Path(__file__).resolve().parents[3] / "sites"
MODIS_NATIVE_M = 250.0
MIN_WIDTH = 1024
N_BEST = 5
BEFORE_YEAR = 2003
AFTER_YEAR = 2024
METHOD = "per-pixel median of the clearest MODIS Terra true-colour days of the season (GIBS)"
# Season per site: when the change is easiest to see and clouds are rarest.
SEASONS: Mapping[str, tuple[tuple[int, int], tuple[int, int]]] = {
    "lake_mead": ((6, 1), (8, 31)),  # dry summer, lowest cloud cover
    "aletsch": ((8, 1), (9, 30)),  # least seasonal snow: the ice itself shows
    "donana": ((4, 1), (5, 31)),  # end of the wet season: flooded marsh vs dry marsh
}
DEFAULT_SEASON = ((6, 1), (8, 31))
# Boxes too small for 250 m pixels: the pictures would be a blur, so none are made.
SKIP: Mapping[str, str] = {
    "aletsch": "the 15 km box is about 60 MODIS pixels wide; the glacier tongue is a blur",
    "donana": "at 250 m the marsh is a blur and spring clouds linger in the median",
}


def picture_width(bbox: tuple[float, float, float, float]) -> int:
    return max(MIN_WIDTH, native_width(bbox, MODIS_NATIVE_M))


def build_before_after(
    site_id: str,
    sites_dir: Path = SITES_DIR,
    before_year: int = BEFORE_YEAR,
    after_year: int = AFTER_YEAR,
) -> dict:
    site = load_sites().get(site_id)
    if site is None:
        raise KeyError(f"unknown site {site_id!r}")
    out = sites_dir / site_id
    start, end = SEASONS.get(site_id, DEFAULT_SEASON)
    width = picture_width(site.bbox)
    sides = {}
    for side, year in (("before", before_year), ("after", after_year)):
        meta = build_composite(
            site.bbox,
            out / f"{side}.jpg",
            season_dates(year, start, end),
            n_best=N_BEST,
            width=width,
            layers=(DEFAULT_LAYER,),
            method=METHOD,
        )
        sides[side] = {"year": year, "dates": sorted(d for d, _ in meta["scenes"])}
    doc = {
        "layer": DEFAULT_LAYER,
        "season": [f"{start[0]:02d}-{start[1]:02d}", f"{end[0]:02d}-{end[1]:02d}"],
        "width": width,
        "method": METHOD,
        **sides,
    }
    (out / "before_after.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    logger.info("%s: before %s, after %s", site_id, sides["before"]["dates"], sides["after"]["dates"])
    return doc


def default_site_ids() -> list[str]:
    return [i for i in load_sites().land_ids() if i not in SKIP]


def main(argv: list[str]) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    for site_id in argv or default_site_ids():
        if site_id in SKIP:
            logger.warning("%s: skipped, %s", site_id, SKIP[site_id])
            continue
        try:
            build_before_after(site_id)
        except RuntimeError as exc:
            logger.error("%s: %s", site_id, exc)


if __name__ == "__main__":
    main(sys.argv[1:])
