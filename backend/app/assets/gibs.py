"""Story-mode base texture from NASA GIBS (Global Imagery Browse Services), no auth.

Default layer: MODIS Terra Corrected Reflectance True Color (250 m), one clear day.
WMS 1.3.0 with EPSG:4326 uses axis order lat,lon in BBOX.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

GIBS_WMS_URL = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
DEFAULT_LAYER = "MODIS_Terra_CorrectedReflectance_TrueColor"
TIMEOUT_S = 120.0


def wms_params(bbox: Sequence[float], date: str, width: int, layer: str = DEFAULT_LAYER) -> dict[str, str]:
    w, s, e, n = bbox
    height = max(1, round(width * (n - s) / (e - w)))
    return {
        "SERVICE": "WMS",
        "REQUEST": "GetMap",
        "VERSION": "1.3.0",
        "LAYERS": layer,
        "CRS": "EPSG:4326",
        "BBOX": f"{s},{w},{n},{e}",
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "FORMAT": "image/jpeg",
        "TIME": date,
    }


def fetch_base_image(
    bbox: Sequence[float], date: str, out_path: Path, width: int = 2048, layer: str = DEFAULT_LAYER
) -> Path:
    """Download a true-colour JPEG of the bbox for `date` (YYYY-MM-DD) to `out_path`."""
    response = httpx.get(GIBS_WMS_URL, params=wms_params(bbox, date, width, layer), timeout=TIMEOUT_S)
    response.raise_for_status()
    if not response.headers.get("content-type", "").startswith("image/"):
        raise RuntimeError(f"GIBS did not return an image: {response.text[:200]}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(response.content)
    logger.info("GIBS %s %s -> %s", layer, date, out_path)
    return out_path
