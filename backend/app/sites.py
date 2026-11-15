"""Story-mode sites: where the per-site sweep runs (catalog/sites.yaml)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

PIPELINES = frozenset({"land", "sea"})
SITES_PATH = Path(__file__).resolve().parent.parent / "catalog" / "sites.yaml"


@dataclass(frozen=True)
class UpstreamClimate:
    """Extra climate driver location(s) for a site whose impact depends on a remote basin.

    POWER is fetched at each point and the series are averaged into `*_upstream` drivers.
    """

    points: tuple[tuple[float, float], ...]  # [lon, lat] each
    label: str


@dataclass(frozen=True)
class Site:
    id: str
    name: str
    bbox: tuple[float, float, float, float]  # [min_lon, min_lat, max_lon, max_lat]
    point: tuple[float, float]  # [lon, lat]
    tags: tuple[str, ...]
    upstream_climate: UpstreamClimate | None = None
    snow_terms: bool = False  # derive degree-days and winter precipitation drivers
    pipeline: str = "land"  # "sea" cases are built by app.reef.build, not the land tools

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

    def land_ids(self) -> list[str]:
        return [s.id for s in self.sites if s.pipeline == "land"]


def _parse_upstream(site_id: str, raw: object) -> UpstreamClimate | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"site {site_id!r}: upstream_climate must be a mapping")
    pts = raw.get("points") or ([raw["point"]] if "point" in raw else [])
    if not pts:
        raise ValueError(f"site {site_id!r}: upstream_climate needs point or points")
    points = []
    for p in pts:
        lon, lat = (float(x) for x in p)
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError(f"site {site_id!r}: upstream_climate point {p} is not [lon, lat]")
        points.append((lon, lat))
    return UpstreamClimate(points=tuple(points), label=str(raw.get("label") or "upstream"))


def parse_pipeline(site_id: str, raw: object) -> str:
    pipeline = str(raw if raw is not None else "land")
    if pipeline not in PIPELINES:
        raise ValueError(
            f"site {site_id!r}: pipeline {pipeline!r} must be one of {sorted(PIPELINES)}"
        )
    return pipeline


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
    pipeline = parse_pipeline(site_id, raw.get("pipeline"))
    return Site(
        id=site_id,
        name=str(raw["name"]),
        bbox=bbox,  # type: ignore[arg-type]
        point=point,  # type: ignore[arg-type]
        tags=tuple(str(t) for t in raw.get("tags") or ()),
        upstream_climate=_parse_upstream(site_id, raw.get("upstream_climate")),
        snow_terms=bool(raw.get("snow_terms", False)),
        pipeline=pipeline,
    )


def require_land(site_id: str, catalog: SiteCatalog | None = None) -> None:
    """Raise ValueError if `site_id` is a sea site (land tools must not build it)."""
    site = (catalog or load_sites()).get(site_id)
    if site is not None and site.pipeline == "sea":
        raise ValueError(f"{site_id} is a sea site; it is built by app.reef.build")


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
