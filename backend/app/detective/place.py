"""The place under investigation: a picked point, or one of the solved cases."""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.investigate.runner import point_site
from app.sites import Site, load_sites


@dataclass(frozen=True)
class Place:
    lat: float
    lon: float
    bbox: tuple[float, float, float, float]  # [min_lon, min_lat, max_lon, max_lat]
    tags: tuple[str, ...] = ()
    site_id: str | None = None
    water_share: float | None = None  # share of the land-cover box that is water; None = not profiled

    def as_site(self) -> Site:
        """The `Site` the fetchers expect: the solved case as configured, or a point site."""
        if self.site_id is not None:
            site = load_sites().get(self.site_id)
            if site is None:
                raise ValueError(f"unknown site_id {self.site_id!r}")
            return site
        return replace(point_site(self.lat, self.lon, self.tags), bbox=tuple(self.bbox))
