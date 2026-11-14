"""Story-mode sites: where the per-site sweep runs (catalog/sites.yaml)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

SITES_PATH = Path(__file__).resolve().parent.parent / "catalog" / "sites.yaml"


@dataclass(frozen=True)
class Site:
    id: str
    name: str
    bbox: tuple[float, float, float, float]  # [min_lon, min_lat, max_lon, max_lat]
    point: tuple[float, float]  # [lon, lat]
    tags: tuple[str, ...]

    @property
    def lat(self) -> float:
        return self.point[1]

    @property
    def lon(self) -> float:
        return self.point[0]


@dataclass(frozen=True)
class SiteCatalog:
    study_period: tuple[int, int]
    sites: tuple[Site, ...]

    def get(self, site_id: str) -> Site | None:
        return next((s for s in self.sites if s.id == site_id), None)


def _parse_site(raw: dict) -> Site:
    site_id = str(raw["id"])
    bbox = tuple(float(x) for x in raw["bbox"])
    point = tuple(float(x) for x in raw["point"])
    if len(bbox) != 4:
        raise ValueError(f"site {site_id!r}: bbox needs 4 numbers")
    if len(point) != 2:
        raise ValueError(f"site {site_id!r}: point needs [lon, lat]")
    min_lon, min_lat, max_lon, max_lat = bbox
    lon, lat = point
    if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90):
        raise ValueError(
            f"site {site_id!r}: bbox must be [min_lon, min_lat, max_lon, max_lat]"
        )
    if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
        raise ValueError(f"site {site_id!r}: point {point} is outside its bbox")
    return Site(
        id=site_id,
        name=str(raw["name"]),
        bbox=bbox,  # type: ignore[arg-type]
        point=point,  # type: ignore[arg-type]
        tags=tuple(str(t) for t in raw.get("tags") or ()),
    )


def load_sites(path: Path = SITES_PATH) -> SiteCatalog:
    """Load and validate the sites file."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    start, end = (int(y) for y in data["study_period"])
    if start > end:
        raise ValueError("study_period start must be <= end")
    sites = tuple(_parse_site(raw) for raw in data["sites"])
    ids = [s.id for s in sites]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate site ids in sites.yaml")
    return SiteCatalog(study_period=(start, end), sites=sites)
