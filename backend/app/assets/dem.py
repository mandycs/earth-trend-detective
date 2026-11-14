"""Story-mode heightmap from NASADEM (NASA, 1 arc-second SRTM reprocessing).

- Tiles are found via CMR and downloaded from LP DAAC with the Earthdata `NASA_TOKEN`.
- Each `.hgt` tile is 3601x3601 big-endian int16 metres, rows north to south,
  1-pixel overlap with its neighbours. Voids (-32768) are filled with the tile median.
- Mosaic -> crop to the site bbox -> resample to `width` px -> 16-bit grayscale PNG,
  0 = min elevation, 65535 = max. The min/max in metres go into site.json so the 3D
  scene can scale heights exactly.
"""

from __future__ import annotations

import io
import logging
import math
import os
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np
from dotenv import load_dotenv
from PIL import Image

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_CACHE_DIR = BACKEND_DIR / "data" / "cache" / "nasadem"
CMR_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
TILE_SIZE = 3601
VOID = -32768
MIN_ELEVATION_M = 0.0
TIMEOUT_S = 300.0


@dataclass(frozen=True)
class Heightmap:
    path: Path
    width: int
    height: int
    min_m: float
    max_m: float


def tile_name(lat: int, lon: int) -> str:
    """NASADEM tile id for the 1° cell whose south-west corner is (lat, lon)."""
    ns = "n" if lat >= 0 else "s"
    ew = "e" if lon >= 0 else "w"
    return f"{ns}{abs(lat):02d}{ew}{abs(lon):03d}"


def tiles_for_bbox(bbox: Sequence[float]) -> list[tuple[int, int]]:
    w, s, e, n = bbox
    lats = range(math.floor(s), math.ceil(n))
    lons = range(math.floor(w), math.ceil(e))
    return [(lat, lon) for lat in lats for lon in lons]


def _token() -> str:
    load_dotenv(REPO_ROOT / ".env")
    token = os.environ.get("NASA_TOKEN", "").strip()
    if not token:
        raise RuntimeError("NASA_TOKEN missing: put it in the repo-root .env")
    return token


def _tile_url(client: httpx.Client, name: str) -> str:
    r = client.get(CMR_URL, params={"short_name": "NASADEM_HGT", "version": "001",
                                     "readable_granule_name": f"NASADEM_HGT_{name}"})
    r.raise_for_status()
    for entry in r.json()["feed"]["entry"]:
        for link in entry["links"]:
            if link["href"].startswith("https") and link["href"].endswith(".zip"):
                return link["href"]
    raise FileNotFoundError(f"NASADEM tile {name} not in CMR (ocean?)")


def read_hgt(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=">i2").reshape(TILE_SIZE, TILE_SIZE).astype(np.float32)
    voids = arr == VOID
    if voids.any():
        arr[voids] = np.median(arr[~voids]) if (~voids).any() else 0.0
    return arr


def load_tile(lat: int, lon: int, cache_dir: Path = DEFAULT_CACHE_DIR) -> np.ndarray:
    name = tile_name(lat, lon)
    path = cache_dir / f"NASADEM_HGT_{name}.zip"
    if not path.exists():
        with httpx.Client(timeout=TIMEOUT_S, follow_redirects=True) as cmr:
            url = _tile_url(cmr, name)
        logger.info("NASADEM download %s", name)
        headers = {"Authorization": f"Bearer {_token()}"}
        with httpx.Client(timeout=TIMEOUT_S, follow_redirects=True, headers=headers) as client:
            r = client.get(url)
            r.raise_for_status()
        cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
    with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as z:
        hgt = next(n for n in z.namelist() if n.endswith(".hgt"))
        return read_hgt(z.read(hgt))


def mosaic(tiles: dict[tuple[int, int], np.ndarray]) -> tuple[np.ndarray, float, float]:
    """Stitch tiles into one grid. Returns (array, west_lon, north_lat); step = 1/3600°."""
    lats = sorted({t[0] for t in tiles})
    lons = sorted({t[1] for t in tiles})
    step = TILE_SIZE - 1
    out = np.zeros((len(lats) * step + 1, len(lons) * step + 1), dtype=np.float32)
    for (lat, lon), arr in tiles.items():
        r0 = (lats[-1] - lat) * step
        c0 = (lon - lons[0]) * step
        out[r0:r0 + TILE_SIZE, c0:c0 + TILE_SIZE] = arr
    return out, float(lons[0]), float(lats[-1] + 1)


def crop(grid: np.ndarray, west: float, north: float, bbox: Sequence[float]) -> np.ndarray:
    w, s, e, n = bbox
    res = 1 / (TILE_SIZE - 1)
    c0, c1 = round((w - west) / res), round((e - west) / res) + 1
    r0, r1 = round((north - n) / res), round((north - s) / res) + 1
    return grid[r0:r1, c0:c1]


def to_png16(elev: np.ndarray, path: Path, width: int) -> Heightmap:
    lo, hi = float(elev.min()), float(elev.max())
    norm = (elev - lo) / (hi - lo) if hi > lo else np.zeros_like(elev)
    height = max(1, round(width * elev.shape[0] / elev.shape[1]))
    img = Image.fromarray((norm * 65535).astype(np.uint16))
    img = img.resize((width, height), Image.Resampling.BILINEAR) if img.mode == "I;16" else img
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return Heightmap(path=path, width=img.width, height=img.height, min_m=lo, max_m=hi)


def load_elevation(bbox: Sequence[float], cache_dir: Path = DEFAULT_CACHE_DIR) -> np.ndarray:
    """NASADEM elevation (m) cropped to bbox, rows north to south, 1 arc-second grid."""
    tiles = {t: load_tile(*t, cache_dir=cache_dir) for t in tiles_for_bbox(bbox)}
    grid, west, north = mosaic(tiles)
    # Sea/estuary pixels carry spurious negative heights in NASADEM; none of our sites
    # is below sea level, so clamp to 0 m (keeps the 3D coastline flat).
    return np.maximum(crop(grid, west, north, bbox), MIN_ELEVATION_M)


def build_heightmap(bbox: Sequence[float], out_path: Path, width: int = 1024,
                    cache_dir: Path = DEFAULT_CACHE_DIR) -> Heightmap:
    return to_png16(load_elevation(bbox, cache_dir), out_path, width)
