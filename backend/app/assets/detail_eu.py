"""High-detail crops for the drone view in Europe, with real aerial photos year by year.

- Aletsch (Switzerland): swisstopo swissALTI3D heights (2 m) and SWISSIMAGE orthophotos.
  SWISSIMAGE "journey through time" gives, for each year, the newest photo available
  that year; a year with no new flight repeats the previous image, and we say so.
- Doñana (Spain): IGN MDT05 heights (5 m, whole metres) and PNOA orthophotos; PNOA only
  has the years Andalucía was flown.

All public, no login. Same contract as the Lake Mead crop (`detail.py`), plus
`photos/<YYYY>.jpg` and `photos_by_year` in detail.json. Photos are pictures, not
measurements: flight dates and seasons differ between years.

Usage (from backend/, venv active):
    python -m app.assets.detail_eu [aletsch] [donana]
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import math
import sys
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, map_coordinates

from app.assets.relief import encode_terrain_rgb, hillshade, pixel_size_m

logger = logging.getLogger(__name__)

SITES_DIR = Path(__file__).resolve().parents[3] / "sites"
TIMEOUT_S = 120.0
HEIGHT_PX = 2048
BASE_PX = 3000
PHOTO_PX = 1600
YEARS = range(2003, 2025)
WORKERS = 8

ALTI_STAC = "https://data.geo.admin.ch/api/stac/v0.9/collections/ch.swisstopo.swissalti3d/items"
SWISS_WMTS = "https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.swissimage-product/default/{time}/3857/{z}/{x}/{y}.jpeg"
IGN_WCS = "https://servicios.idee.es/wcs-inspire/mdt"
PNOA_HIST_WMS = "https://www.ign.es/wms/pnoa-historico"


@dataclass(frozen=True)
class Crop:
    site: str
    bbox: tuple[float, float, float, float]  # west, south, east, north
    label: str
    sources: tuple[dict, ...]


CROPS = {
    "aletsch": Crop(
        "aletsch",
        (8.00, 46.395, 8.08, 46.445),
        "Lower tongue of the Great Aletsch Glacier",
        (
            {"name": "swisstopo swissALTI3D elevation model, 2 m", "url": "https://www.swisstopo.admin.ch/en/height-model-swissalti3d"},
            {"name": "swisstopo SWISSIMAGE orthophotos (journey through time)", "url": "https://www.swisstopo.admin.ch/en/orthoimage-swissimage-10"},
        ),
    ),
    "donana": Crop(
        "donana",
        (-6.50, 36.955, -6.43, 37.01),
        "Santa Olalla and Dulce lagoons, Doñana",
        (
            {"name": "IGN Spain MDT05 elevation model, 5 m", "url": "https://centrodedescargas.cnig.es/"},
            {"name": "IGN Spain PNOA orthophotos (historic series)", "url": "https://pnoa.ign.es/"},
        ),
    ),
}


# --------------------------------------------------------------------------- geometry


def grid(bbox: Sequence[float], width: int) -> tuple[np.ndarray, np.ndarray]:
    """lat (rows, north->south) and lon (cols) of pixel centres; aspect kept in metres."""
    w, s, e, n = bbox
    dx, dy = pixel_size_m(bbox, (1, 1))
    height = max(1, round(width * dy / dx))
    lon = w + (np.arange(width) + 0.5) * (e - w) / width
    lat = n - (np.arange(height) + 0.5) * (n - s) / height
    return lat, lon


def wgs84_to_lv95(lat: np.ndarray, lon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """swisstopo approximate formulas (about 1 m accuracy): degrees -> (E, N) metres."""
    phi = (lat * 3600 - 169028.66) / 10000
    lam = (lon * 3600 - 26782.5) / 10000
    e = 2600072.37 + 211455.93 * lam - 10938.51 * lam * phi - 0.36 * lam * phi**2 - 44.54 * lam**3
    n = (
        1200147.07 + 308807.95 * phi + 3745.25 * lam**2 + 76.63 * phi**2
        - 194.56 * lam**2 * phi + 119.79 * phi**3
    )
    return e, n


def mercator_tile(lat: float, lon: float, z: int) -> tuple[float, float]:
    """Fractional XYZ tile coordinates of a point."""
    n = 2**z
    x = (lon + 180) / 360 * n
    y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
    return x, y


# --------------------------------------------------------------------------- heights


def _get(client: httpx.Client, url: str, **params: str) -> bytes:
    r = client.get(url, params=params or None)
    r.raise_for_status()
    return r.content


def swiss_heights(client: httpx.Client, bbox: Sequence[float], width: int) -> np.ndarray:
    lat, lon = grid(bbox, width)
    lat2, lon2 = np.meshgrid(lat, lon, indexing="ij")
    e, n = wgs84_to_lv95(lat2, lon2)
    items = client.get(ALTI_STAC, params={"bbox": ",".join(map(str, bbox)), "limit": 200}).json()["features"]
    tiles: dict[tuple[int, int], str] = {}
    for item in items:
        ek, nk = (int(v) for v in item["id"].rsplit("_", 1)[1].split("-"))
        href = next(a["href"] for k, a in item["assets"].items() if k.endswith("_2_2056_5728.tif"))
        tiles[(ek, nk)] = href  # newest survey wins if several (ids sort by year)
    e0, e1 = int(e.min() // 1000), int(e.max() // 1000)
    n0, n1 = int(n.min() // 1000), int(n.max() // 1000)
    px = 500  # 2 m tiles of 1 km
    mosaic = np.full(((n1 - n0 + 1) * px, (e1 - e0 + 1) * px), np.nan, dtype=np.float32)

    def load(key: tuple[int, int]) -> tuple[tuple[int, int], np.ndarray]:
        return key, np.asarray(Image.open(io.BytesIO(_get(client, tiles[key]))), dtype=np.float32)

    keys = [(ek, nk) for ek in range(e0, e1 + 1) for nk in range(n0, n1 + 1) if (ek, nk) in tiles]
    with ThreadPoolExecutor(WORKERS) as pool:
        for (ek, nk), arr in pool.map(load, keys):
            row = (n1 - nk) * px
            col = (ek - e0) * px
            mosaic[row:row + px, col:col + px] = arr
    rows = ((n1 + 1) * 1000 - n) / 2 - 0.5
    cols = (e - e0 * 1000) / 2 - 0.5
    out = map_coordinates(np.nan_to_num(mosaic, nan=np.nanmedian(mosaic)), [rows, cols], order=1)
    logger.info("swissALTI3D: %d tiles, %.0f-%.0f m", len(keys), out.min(), out.max())
    return out.astype(np.float32)


def spain_heights(client: httpx.Client, bbox: Sequence[float], width: int) -> np.ndarray:
    w, s, e, n = bbox
    raw = client.get(
        IGN_WCS,
        params=[
            ("SERVICE", "WCS"), ("REQUEST", "GetCoverage"), ("VERSION", "2.0.1"),
            ("CoverageId", "Elevacion4258_5"), ("SUBSET", f"Lat({s},{n})"), ("SUBSET", f"Long({w},{e})"),
            ("FORMAT", "image/tiff"),
        ],
    )
    raw.raise_for_status()
    src = np.asarray(Image.open(io.BytesIO(raw.content)), dtype=np.float32)
    # Whole-metre heights make terraces on flat ground: smooth by ~2 source pixels.
    src = gaussian_filter(src, 2.0)
    lat, _ = grid(bbox, width)
    img = Image.fromarray(src, mode="F").resize((width, len(lat)), Image.Resampling.BILINEAR)
    logger.info("IGN MDT05: %s px, %.1f-%.1f m", src.shape, src.min(), src.max())
    return np.asarray(img, dtype=np.float32)


# --------------------------------------------------------------------------- photos


def swiss_photo(client: httpx.Client, bbox: Sequence[float], width: int, time: str, z: int) -> Image.Image:
    """SWISSIMAGE for `time` (a year or 'current') resampled from Web Mercator tiles."""
    lat, lon = grid(bbox, width)
    w, s, e, n = bbox
    x0, y0 = mercator_tile(n, w, z)
    x1, y1 = mercator_tile(s, e, z)
    tx = range(int(x0), int(x1) + 1)
    ty = range(int(y0), int(y1) + 1)
    mosaic = np.zeros((len(ty) * 256, len(tx) * 256, 3), dtype=np.uint8)

    def load(xy: tuple[int, int]) -> tuple[tuple[int, int], np.ndarray]:
        x, y = xy
        raw = _get(client, SWISS_WMTS.format(time=time, z=z, x=x, y=y))
        return xy, np.asarray(Image.open(io.BytesIO(raw)).convert("RGB"))

    with ThreadPoolExecutor(WORKERS) as pool:
        for (x, y), arr in pool.map(load, [(x, y) for y in ty for x in tx]):
            mosaic[(y - ty[0]) * 256:(y - ty[0] + 1) * 256, (x - tx[0]) * 256:(x - tx[0] + 1) * 256] = arr
    fx = np.array([mercator_tile(46.4, lo, z)[0] for lo in lon])  # x does not depend on lat
    fy = np.array([mercator_tile(la, 8.0, z)[1] for la in lat])  # y does not depend on lon
    cols = (fx - tx[0]) * 256 - 0.5
    rows = (fy - ty[0]) * 256 - 0.5
    rr, cc = np.meshgrid(rows, cols, indexing="ij")
    out = np.stack([map_coordinates(mosaic[..., c], [rr, cc], order=1) for c in range(3)], axis=-1)
    return Image.fromarray(out.astype(np.uint8))


def pnoa_photo(client: httpx.Client, bbox: Sequence[float], width: int, year: int) -> Image.Image | None:
    """PNOA orthophoto of `year`, or None if Andalucía was not flown that year."""
    lat, _ = grid(bbox, width)
    w, s, e, n = bbox
    r = client.get(PNOA_HIST_WMS, params={
        "SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": "1.3.0", "LAYERS": f"PNOA{year}", "STYLES": "",
        "CRS": "EPSG:4326", "BBOX": f"{s},{w},{n},{e}", "WIDTH": str(width), "HEIGHT": str(len(lat)),
        "FORMAT": "image/jpeg",
    })
    if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
        return None
    img = Image.open(io.BytesIO(r.content)).convert("RGB")
    a = np.asarray(img).astype(np.int32).sum(-1)
    if ((a > 740) | (a < 10)).mean() > 0.5:  # blank: not flown that year
        return None
    return img


# --------------------------------------------------------------------------- build


def _digest(img: Image.Image) -> str:
    small = img.resize((64, 64)).tobytes()
    return hashlib.md5(small, usedforsecurity=False).hexdigest()


def yearly_photos(
    fetch: Callable[[int], Image.Image | None], years: Sequence[int], out_dir: Path
) -> dict[str, dict]:
    """photos/<YYYY>.jpg for each year with an image; a year identical to the year before
    is recorded as `same_as` (no new flight that year), not saved twice."""
    out_dir.mkdir(parents=True, exist_ok=True)
    by_year: dict[str, dict] = {}
    previous: tuple[str, int] | None = None
    for year in years:
        img = fetch(year)
        if img is None:
            continue
        digest = _digest(img)
        if previous is not None and digest == previous[0]:
            by_year[str(year)] = {"file": f"photos/{previous[1]}.jpg", "same_as": previous[1]}
            continue
        img.save(out_dir / f"{year}.jpg", quality=85)
        by_year[str(year)] = {"file": f"photos/{year}.jpg"}
        previous = (digest, year)
    return by_year


def build(site: str, sites_dir: Path = SITES_DIR) -> dict:
    crop = CROPS[site]
    out = sites_dir / site / "detail"
    out.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=TIMEOUT_S, follow_redirects=True) as client:
        if site == "aletsch":
            dem = swiss_heights(client, crop.bbox, HEIGHT_PX)
            base = swiss_photo(client, crop.bbox, BASE_PX, "current", 16)
            photos = yearly_photos(lambda y: swiss_photo(client, crop.bbox, PHOTO_PX, str(y), 15), YEARS, out / "photos")
            photo_note = (
                "Each year shows the newest SWISSIMAGE photo available that year; 'same_as' marks years "
                "with no new flight. Flight dates and seasons differ, so snow cover differs too."
            )
        else:
            dem = spain_heights(client, crop.bbox, HEIGHT_PX)
            photos = yearly_photos(lambda y: pnoa_photo(client, crop.bbox, PHOTO_PX, y), YEARS, out / "photos")
            newest = max(int(y) for y, p in photos.items() if "same_as" not in p)
            base = pnoa_photo(client, crop.bbox, BASE_PX, newest)
            photo_note = (
                "PNOA photos exist only for the years Andalucía was flown. Flight months differ, and "
                "the marsh floods by season, so compare years with care."
            )
    Image.fromarray(encode_terrain_rgb(dem)).save(out / "heightmap_rgb.png", optimize=True)
    dx, dy = pixel_size_m(crop.bbox, dem.shape)
    Image.fromarray((hillshade(dem, dx, dy) * 255).astype(np.uint8)).save(out / "hillshade.png", optimize=True)
    base.save(out / "base.jpg", quality=88)
    doc = {
        "bbox": list(crop.bbox),
        "label": crop.label,
        "size_px": {"heightmap": [dem.shape[1], dem.shape[0]], "base": list(base.size)},
        "resolution_m": {"heightmap": round(dx, 2), "base": round(dx * dem.shape[1] / base.size[0], 2)},
        "height_range_m": [round(float(dem.min()), 1), round(float(dem.max()), 1)],
        "encoding": "terrain-rgb: height_m = -10000 + (R*65536 + G*256 + B) * 0.1",
        "photos_by_year": photos,
        "photo_note": photo_note,
        "note": "Ground and photos are pictures, not measurements of change.",
        "status": "visual_only",
        "sources": list(crop.sources),
    }
    (out / "detail.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("%s detail: %s, photos %s", site, doc["size_px"], sorted(photos))
    return doc


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    for site_id in sys.argv[1:] or list(CROPS):
        build(site_id)
