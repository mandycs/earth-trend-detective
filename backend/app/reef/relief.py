"""Seabed relief of the reef box from GEBCO_2020 (GEBCO Compilation Group, not NASA).

`fetch_gebco` reads the grid through the ERDDAP extractor (same cache and retry rules) and
returns metres with rows north -> south. `write_relief` clips the heights to -100..800 m so
the shallow reef shelf stays visible, writes the heightmap PNGs and a `heightmap.json` that
records both the raw and the clipped range, the source and a note saying so.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import httpx
import numpy as np

from app.assets import dem
from app.assets import relief as assets_relief
from app.extractors import erddap

GEBCO_STRIDE = 2
CLIP_M = (-100.0, 800.0)
SOURCE = "GEBCO_2020 (GEBCO Compilation Group)"
SOURCE_ID = "GEBCO_2020"
NOTE = "Heights clipped to −100…800 m so the shallow reef shelf stays visible; deeper sea and higher land are flattened."
HEIGHTMAP_WIDTH = 1024


def _offline_client() -> httpx.Client:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise FileNotFoundError("GEBCO is not in the cache and offline mode is on")

    return httpx.Client(transport=httpx.MockTransport(refuse))


def fetch_gebco(
    bbox: Sequence[float], cache_dir: Path, client: httpx.Client | None = None, offline: bool = False
) -> np.ndarray:
    """GEBCO_2020 elevation (m) over bbox (west, south, east, north), rows north -> south.

    Offline raises `FileNotFoundError` without a cached grid; a failed request raises
    `erddap.ErddapError` (an HTTP error is not "no data").
    """
    if offline:
        client = _offline_client()
    grid = erddap.fetch_elevation_grid(tuple(bbox), GEBCO_STRIDE, client, cache_dir)
    return grid.sortby("latitude", ascending=False).to_numpy().astype(np.float64)  # ERDDAP: south first


def write_relief(elev: np.ndarray, bbox: Sequence[float], site_dir: Path) -> dict:
    """Write heightmap.png, heightmap_rgb.png, hillshade.png and heightmap.json; return the sidecar."""
    site_dir.mkdir(parents=True, exist_ok=True)
    raw = (float(np.nanmin(elev)), float(np.nanmax(elev)))
    clipped = np.clip(elev, *CLIP_M)
    hm = dem.to_png16(clipped, site_dir / "heightmap.png", HEIGHTMAP_WIDTH)
    assets_relief.write_terrain_rgb(clipped, site_dir / "heightmap_rgb.png", HEIGHTMAP_WIDTH)
    assets_relief.write_hillshade(clipped, bbox, site_dir / "hillshade.png")
    meta = {
        "min_m": hm.min_m,
        "max_m": hm.max_m,
        "raw_range_m": [raw[0], raw[1]],
        "clipped_to": [CLIP_M[0], CLIP_M[1]],
        "width": hm.width,
        "height": hm.height,
        "source": SOURCE,
        "source_id": SOURCE_ID,
        "note": NOTE,
    }
    (site_dir / "heightmap.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta
