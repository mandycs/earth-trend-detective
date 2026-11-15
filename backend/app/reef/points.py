"""The five reef points the case follows, and the case-wide constants."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
SITE_ID = "great_barrier_reef"
CHLOROPHYLL_POINT = "burdekin"
DEFAULT_CACHE_DIR = BACKEND_DIR / "data" / "cache" / "erddap"


@dataclass(frozen=True)
class ReefPoint:
    id: str
    name: str
    lat: float
    lon: float


REEF_POINTS: tuple[ReefPoint, ...] = (
    ReefPoint("north", "Northern reef (off Cooktown)", -14.6, 145.6),
    ReefPoint("davies", "Davies Reef (central)", -18.8, 147.6),
    ReefPoint("outer", "Outer shelf (central)", -18.3, 148.3),
    ReefPoint("burdekin", "Inshore, off the Burdekin River", -19.45, 147.75),
    ReefPoint("heron", "Heron Reef (south)", -23.4, 152.0),
)
