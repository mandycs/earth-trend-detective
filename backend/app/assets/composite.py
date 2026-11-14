"""Cloud-free 30 m base texture: per-pixel median of many NASA HLS scenes (via GIBS).

1. Screen every day of a season for both HLS layers (Landsat L30, Sentinel-2 S30) with a
   small thumbnail; score = share of no-data (black) + cloud-like (bright, grey) pixels.
2. Download the best N scenes at full size.
3. Per pixel, median over scenes where the pixel has data. Clouds and shadows are transient,
   so the median keeps the ground (and persistent snow/ice) and drops them.

Output width defaults to ~2x the native 30 m resolution of the bbox, capped at MAX_WIDTH.
"""

from __future__ import annotations

import datetime as dt
import io
import logging
import math
from collections.abc import Sequence
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

from app.assets.gibs import GIBS_WMS_URL, wms_params

logger = logging.getLogger(__name__)

HLS_LAYERS = ("HLS_L30_Nadir_BRDF_Adjusted_Reflectance", "HLS_S30_Nadir_BRDF_Adjusted_Reflectance")
NATIVE_M = 30.0
MAX_WIDTH = 4096
THUMB_WIDTH = 256
NODATA_SUM = 15
CLOUD_MIN = 200  # all three channels above this and nearly grey -> cloud-like
MAX_BAD_SHARE = 0.35
TIMEOUT_S = 120.0


def native_width(bbox: Sequence[float], native_m: float = NATIVE_M) -> int:
    """~2x the native pixel count across the bbox, capped at MAX_WIDTH."""
    w, s, e, n = bbox
    width_m = math.radians(e - w) * 6_371_008.8 * math.cos(math.radians((s + n) / 2))
    return min(MAX_WIDTH, int(2 * width_m / native_m))


def bad_share(rgb: np.ndarray) -> float:
    a = rgb.astype(np.int32)
    nodata = a.sum(-1) < NODATA_SUM
    grey = (a.max(-1) - a.min(-1)) < 25
    cloud = (a.min(-1) > CLOUD_MIN) & grey
    return float((nodata | cloud).mean())


def _get(client: httpx.Client, bbox: Sequence[float], date: str, width: int, layer: str) -> np.ndarray | None:
    r = client.get(GIBS_WMS_URL, params=wms_params(bbox, date, width, layer))
    if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
        return None
    return np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB"))


def season_dates(year: int, start: tuple[int, int], end: tuple[int, int]) -> list[str]:
    d0, d1 = dt.date(year, *start), dt.date(year, *end)
    return [(d0 + dt.timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def median_composite(scenes: Sequence[np.ndarray]) -> np.ndarray:
    """Per-pixel median over scenes, ignoring no-data pixels; black where no scene has data."""
    stack = np.stack([s.astype(np.float32) for s in scenes])  # (n, h, w, 3)
    nodata = stack.sum(-1, keepdims=True) < NODATA_SUM
    stack = np.where(nodata, np.nan, stack)
    with np.errstate(all="ignore"):
        out = np.nanmedian(stack, axis=0)
    return np.nan_to_num(out, nan=0.0).clip(0, 255).astype(np.uint8)


def build_composite(
    bbox: Sequence[float],
    out_path: Path,
    dates: Sequence[str],
    n_best: int = 12,
    width: int | None = None,
    layers: Sequence[str] = HLS_LAYERS,
    method: str = "per-pixel median of NASA HLS 30 m scenes (GIBS)",
) -> dict:
    width = width or native_width(bbox)
    with httpx.Client(timeout=TIMEOUT_S) as client:
        scored = []
        for layer in layers:
            for date in dates:
                thumb = _get(client, bbox, date, THUMB_WIDTH, layer)
                if thumb is not None:
                    score = bad_share(thumb)
                    if score <= MAX_BAD_SHARE:
                        scored.append((score, date, layer))
        best = sorted(scored)[:n_best]
        if not best:
            raise RuntimeError(f"no usable scene of {', '.join(layers)} in the requested dates")
        scenes = [s for s in (_get(client, bbox, d, width, layer) for _, d, layer in best) if s is not None]
    composite = median_composite(scenes)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(composite).save(out_path, quality=92)
    meta = {"width": composite.shape[1], "height": composite.shape[0], "scenes": [[d, layer] for _, d, layer in best],
            "method": method}
    logger.info("composite %s: %d scenes, %dx%d", out_path.name, len(scenes), composite.shape[1], composite.shape[0])
    return meta
