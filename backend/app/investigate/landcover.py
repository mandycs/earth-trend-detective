"""What covers the ground around a point, from NASA MODIS land cover (MCD12Q1, IGBP classes).

GIBS serves the yearly MCD12Q1 map as a paletted PNG with no login; each colour of its
published colormap is one IGBP class. We read a small box around the point at two years
(start and end of the study period) and count pixels per class: the shares say what kind
of place this is (tags for the catalog) and how the ground cover changed.
"""

from __future__ import annotations

import io
import logging
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import httpx
import numpy as np
from PIL import Image

from app.assets.gibs import GIBS_WMS_URL

logger = logging.getLogger(__name__)

LAYER = "MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual"
SOURCE = {
    "name": "MODIS land cover type (MCD12Q1, IGBP classes), via NASA GIBS",
    "url": "https://lpdaac.usgs.gov/products/mcd12q1v061/",
}
HALF_BOX_DEG = 0.1  # ~20 km box around the point
GRID_PX = 32
TIMEOUT_S = 20.0
TAG_MIN_SHARE = 0.15

# GIBS colormap MODIS_IGBP_Land_Cover_Type (v1.3): rgb -> (IGBP class name, catalog tags).
CLASSES: Mapping[tuple[int, int, int], tuple[str, tuple[str, ...]]] = {
    (33, 138, 33): ("Evergreen needleleaf forest", ("forest", "vegetated")),
    (49, 204, 49): ("Evergreen broadleaf forest", ("forest", "vegetated")),
    (152, 204, 49): ("Deciduous needleleaf forest", ("forest", "vegetated")),
    (150, 250, 150): ("Deciduous broadleaf forest", ("forest", "vegetated")),
    (141, 186, 141): ("Mixed forest", ("forest", "vegetated")),
    (186, 141, 141): ("Closed shrubland", ("vegetated",)),
    (245, 222, 179): ("Open shrubland", ("desert",)),
    (218, 235, 157): ("Woody savanna", ("vegetated",)),
    (255, 213, 0): ("Savanna", ("vegetated",)),
    (240, 185, 103): ("Grassland", ("vegetated",)),
    (71, 131, 181): ("Permanent wetland", ("wetland",)),
    (250, 239, 115): ("Cropland", ("agriculture", "vegetated")),
    (255, 0, 0): ("Urban and built-up land", ("urban",)),
    (153, 147, 86): ("Cropland and natural vegetation mosaic", ("agriculture", "vegetated")),
    (255, 255, 255): ("Permanent snow and ice", ("snow", "glacier")),
    (191, 191, 189): ("Barren", ("desert",)),
    (134, 202, 227): ("Water", ("water_body",)),
}


@dataclass(frozen=True)
class LandCover:
    year: int
    shares: Mapping[str, float]  # class name -> share of classified pixels, largest first

    @property
    def dominant(self) -> str | None:
        return next(iter(self.shares), None)

    def to_dict(self) -> dict:
        return {"year": self.year, "dominant": self.dominant, "shares": dict(self.shares)}


def box_around(lat: float, lon: float, half: float = HALF_BOX_DEG) -> tuple[float, float, float, float]:
    """[min_lon, min_lat, max_lon, max_lat] clipped to valid coordinates."""
    return (max(-180.0, lon - half), max(-90.0, lat - half), min(180.0, lon + half), min(90.0, lat + half))


def class_shares(rgba: np.ndarray) -> dict[str, float]:
    """Share of each known IGBP class among opaque, classified pixels (largest first)."""
    pixels = rgba.reshape(-1, rgba.shape[-1])
    counts: Counter[str] = Counter()
    for px in pixels:
        if px.shape[0] == 4 and px[3] == 0:
            continue
        hit = CLASSES.get((int(px[0]), int(px[1]), int(px[2])))
        if hit is not None:
            counts[hit[0]] += 1
    total = sum(counts.values())
    if total == 0:
        return {}
    return {name: round(n / total, 3) for name, n in counts.most_common()}


def tags_for(shares: Mapping[str, float], min_share: float = TAG_MIN_SHARE) -> tuple[str, ...]:
    """Catalog tags of every class covering at least `min_share` (in first-seen order)."""
    by_name = {name: tags for name, tags in CLASSES.values()}
    out: list[str] = []
    for name, share in shares.items():
        if share >= min_share:
            out.extend(t for t in by_name.get(name, ()) if t not in out)
    return tuple(out)


def share_changes(before: LandCover, after: LandCover, min_change: float = 0.02) -> list[dict]:
    """Classes whose share moved by at least `min_change`, biggest move first."""
    names = set(before.shares) | set(after.shares)
    rows = [
        {"class": n, "before": before.shares.get(n, 0.0), "after": after.shares.get(n, 0.0)}
        for n in names
    ]
    for r in rows:
        r["change"] = round(r["after"] - r["before"], 3)
    return sorted((r for r in rows if abs(r["change"]) >= min_change), key=lambda r: -abs(r["change"]))


def fetch_land_cover(
    lat: float, lon: float, year: int, client: httpx.Client | None = None
) -> LandCover:
    w, s, e, n = box_around(lat, lon)
    params = {
        "SERVICE": "WMS",
        "REQUEST": "GetMap",
        "VERSION": "1.3.0",
        "LAYERS": LAYER,
        "CRS": "EPSG:4326",
        "BBOX": f"{s},{w},{n},{e}",
        "WIDTH": str(GRID_PX),
        "HEIGHT": str(GRID_PX),
        "FORMAT": "image/png",
        "TIME": f"{year}-01-01",
    }
    owns = client is None
    client = client or httpx.Client(timeout=TIMEOUT_S)
    try:
        r = client.get(GIBS_WMS_URL, params=params)
        r.raise_for_status()
        if not r.headers.get("content-type", "").startswith("image/"):
            raise RuntimeError("GIBS did not return an image for the land cover layer")
        rgba = np.asarray(Image.open(io.BytesIO(r.content)).convert("RGBA"))
    finally:
        if owns:
            client.close()
    return LandCover(year, class_shares(rgba))


def land_cover_pair(lat: float, lon: float, years: Sequence[int]) -> list[LandCover]:
    with httpx.Client(timeout=TIMEOUT_S) as client:
        return [fetch_land_cover(lat, lon, y, client) for y in years]


def describe(tags: Iterable[str]) -> str:
    """Short plain-English kind of place for the planner prompt."""
    tags = list(tags)
    return ", ".join(tags) if tags else "unclassified"
