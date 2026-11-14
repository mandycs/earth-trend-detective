"""High-detail crop for the 3D drone view: USGS 3DEP lidar heights + USGS NAIP aerial photo.

Lake Mead only (US open data). Both come from public USGS ArcGIS ImageServers, no login.
The lidar (AZ_LowerColoradoRiver_2018) was flown when the lake was low, so the shore it
captured above that day's water is real ground. Over the water the lidar is flat
("hydro-flattened") at that day's level: nothing below it can be shown.

Lake level per year comes from USBR (NGVD29, read in metres). The lidar is NAVD88. Instead of a
datum model we measure the offset: the flat water surface in the lidar vs the USBR level
of the survey months. Years whose level is below the lidar water surface are listed as
not drawable (the ground under them was under water when the lidar flew).

Usage (from backend/, venv active):
    python -m app.assets.detail
"""

from __future__ import annotations

import io
import json
import logging
import time
from collections.abc import Sequence
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
from PIL import Image

from app.assets.relief import encode_terrain_rgb, hillshade, pixel_size_m
from app.validation.usbr import fetch_mead_elevation

logger = logging.getLogger(__name__)

SITES_DIR = Path(__file__).resolve().parents[3] / "sites"
DEM_URL = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
NAIP_URL = "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPPlus/ImageServer/exportImage"
TIMEOUT_S = 180.0

# Las Vegas Bay, Lake Mead: the drowned Las Vegas Wash channel and the white "bathtub ring".
# The 3DEP mosaic here mixes the 2018 survey (water flat at ~329.6 m, most of the box) with
# a later one flattened lower (~317.7 m, the bay's western arm). The water surface used is
# the most common flat height; levels below it are not drawn anywhere, so both parts agree.
BBOX = (-114.845, 36.075, -114.775, 36.13)
DEM_PX = 2048  # ~3 m per pixel over the ~6 km box
PHOTO_WIDTHS = (3000, 2600, 2048)  # ~2-3 m per pixel; one request (larger ones time out)
SURVEY = "USGS 3DEP lidar AZ_LowerColoradoRiver_2018 (QL1/QL2)"
SURVEY_MONTHS = ("2018-10", "2018-11", "2018-12", "2019-01", "2019-02", "2019-03")
YEARS = (2003, 2024)

SOURCES = [
    {"name": "USGS 3D Elevation Program (3DEP) lidar, 1 m", "url": "https://www.usgs.gov/3d-elevation-program"},
    {"name": "USDA NAIP aerial photography, via USGS The National Map", "url": "https://naip-usdaonline.hub.arcgis.com/"},
    {"name": "Lake Mead elevation, US Bureau of Reclamation", "url": "https://www.usbr.gov/lc/region/g4000/hourly/mead-elv.html"},
]


def _export(client: httpx.Client, url: str, bbox: Sequence[float], width: int, height: int, **extra: str) -> bytes:
    params = {
        "bbox": ",".join(str(v) for v in bbox),
        "bboxSR": "4326",
        "imageSR": "4326",
        "size": f"{width},{height}",
        "f": "image",
        **extra,
    }
    r = client.get(url, params=params)
    r.raise_for_status()
    if not r.headers.get("content-type", "").startswith("image/"):
        raise RuntimeError(f"{url} did not return an image: {r.text[:200]}")
    return r.content


def size_for(bbox: Sequence[float], width: int) -> tuple[int, int]:
    w, s, e, n = bbox
    dx, dy = pixel_size_m(bbox, (1, 1))  # metres per degree-box -> aspect in metres
    return width, max(1, round(width * dy / dx))


def fetch_dem(client: httpx.Client, bbox: Sequence[float], width: int) -> np.ndarray:
    w, h = size_for(bbox, width)
    raw = _export(
        client, DEM_URL, bbox, w, h, format="tiff", pixelType="F32", interpolation="RSP_BilinearInterpolation"
    )
    return np.asarray(Image.open(io.BytesIO(raw)), dtype=np.float32)


def fetch_photo(client: httpx.Client, bbox: Sequence[float], widths: Sequence[int] = PHOTO_WIDTHS) -> Image.Image:
    """NAIP photo of bbox in ONE request: tiled requests can each pick a different flight
    and leave colour seams. The service is flaky at large sizes: try each width twice,
    largest first."""
    last: Exception | None = None
    for width in widths:
        w, h = size_for(bbox, width)
        for attempt in (1, 2):
            try:
                raw = _export(client, NAIP_URL, bbox, w, h, format="jpgpng", bandIds="0,1,2")
                return Image.open(io.BytesIO(raw)).convert("RGB")
            except (httpx.HTTPStatusError, httpx.TimeoutException) as exc:
                last = exc
                logger.warning("NAIP %d px attempt %d failed: %s", width, attempt, type(exc).__name__)
                time.sleep(5)
    raise RuntimeError("NAIP did not answer at any size") from last


def water_surface_m(dem: np.ndarray) -> tuple[float, float]:
    """(height, share) of the hydro-flattened water: the most common height (0.1 m bins)."""
    valid = dem[np.isfinite(dem) & (dem > -1000)]
    bins = np.round(valid, 1)
    values, counts = np.unique(bins, return_counts=True)
    top = int(np.argmax(counts))
    return float(values[top]), float(counts[top] / counts.sum())


def yearly_levels_m(monthly_m: pd.Series, years: tuple[int, int]) -> dict[int, float]:
    m = monthly_m.dropna()
    annual = m.groupby(m.index.year).mean()
    return {int(y): round(float(v), 2) for y, v in annual.items() if years[0] <= y <= years[1]}


def build_detail(sites_dir: Path = SITES_DIR, bbox: Sequence[float] = BBOX) -> dict:
    out = sites_dir / "lake_mead" / "detail"
    out.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=TIMEOUT_S) as client:
        dem = fetch_dem(client, bbox, DEM_PX)
        photo = fetch_photo(client, bbox)

    nodata = ~np.isfinite(dem) | (dem < -1000)
    if nodata.any():
        dem = np.where(nodata, np.nanmedian(dem[~nodata]), dem)
    Image.fromarray(encode_terrain_rgb(dem)).save(out / "heightmap_rgb.png", optimize=True)
    dx, dy = pixel_size_m(bbox, dem.shape)
    shade = hillshade(dem, dx, dy)
    Image.fromarray((shade * 255).astype(np.uint8)).save(out / "hillshade.png", optimize=True)
    photo.save(out / "base.jpg", quality=88)

    surface, share = water_surface_m(dem)
    monthly = fetch_mead_elevation(*YEARS)
    survey_m = float(monthly[monthly.index.strftime("%Y-%m").isin(SURVEY_MONTHS)].mean())
    offset = surface - survey_m  # lidar (NAVD88) minus USBR (NGVD29) at the survey
    levels = {y: round(v + offset, 2) for y, v in yearly_levels_m(monthly, YEARS).items()}
    doc = {
        "bbox": list(bbox),
        "size_px": {"heightmap": [dem.shape[1], dem.shape[0]], "base": list(photo.size)},
        "resolution_m": {"heightmap": round(dx, 2), "base": round(dx * dem.shape[1] / photo.size[0], 2)},
        "height_range_m": [round(float(dem.min()), 1), round(float(dem.max()), 1)],
        "encoding": "terrain-rgb: height_m = -10000 + (R*65536 + G*256 + B) * 0.1",
        "survey": SURVEY,
        "lidar_water_surface_m": round(surface, 2),
        "lidar_water_share": round(share, 3),
        "usbr_level_at_survey_m": round(survey_m, 2),
        "datum_offset_m": round(offset, 2),
        "water_level_m_by_year": {str(y): v for y, v in levels.items()},
        "drawable_years": [y for y, v in levels.items() if v >= surface],
        "note": (
            "Ground and photo are present-day pictures, not measurements of change. Water levels are USBR "
            "yearly means moved onto the lidar heights; years below the lidar water surface cannot be drawn."
        ),
        "status": "visual_only",
        "sources": SOURCES,
    }
    (out / "detail.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    logger.info(
        "detail: %s, water surface %.2f m (%.0f%% of pixels), offset %.2f m, drawable %s",
        doc["size_px"], surface, share * 100, offset, doc["drawable_years"],
    )
    return doc


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    build_detail()
