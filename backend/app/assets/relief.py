"""Relief assets for the 3D story mode, from NASADEM elevation.

- terrain-RGB heightmap (Mapbox encoding): height_m = -10000 + (R*65536 + G*256 + B) * 0.1.
  Browsers decode 16-bit grayscale PNGs to 8 bits (256 levels); RGB keeps 0.1 m precision.
- Multidirectional hillshade (grayscale), same extent as the base texture, to multiply
  over the satellite image so ridges, canyons and shorelines read at a glance.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from PIL import Image

EARTH_RADIUS_M = 6_371_008.8
RGB_BASE_M = -10_000.0
RGB_STEP_M = 0.1
# Light from NW (classic) plus W, N and NE at lower weight: multidirectional shading keeps
# slopes facing away from a single sun readable.
HILLSHADE_LIGHTS = ((315.0, 0.5), (270.0, 0.2), (0.0, 0.15), (45.0, 0.15))
SUN_ALTITUDE_DEG = 35.0


def resample(elev: np.ndarray, width: int) -> np.ndarray:
    """Bilinear resample to `width` px keeping aspect (float32, metres)."""
    height = max(1, round(width * elev.shape[0] / elev.shape[1]))
    img = Image.fromarray(elev.astype(np.float32), mode="F")
    return np.asarray(img.resize((width, height), Image.Resampling.BILINEAR), dtype=np.float32)


def encode_terrain_rgb(elev: np.ndarray) -> np.ndarray:
    """uint8 RGB array encoding heights with 0.1 m precision."""
    code = np.clip(np.round((elev - RGB_BASE_M) / RGB_STEP_M), 0, 2**24 - 1).astype(np.uint32)
    return np.stack([(code >> 16) & 255, (code >> 8) & 255, code & 255], axis=-1).astype(np.uint8)


def decode_terrain_rgb(rgb: np.ndarray) -> np.ndarray:
    r, g, b = (rgb[..., i].astype(np.float64) for i in range(3))
    return RGB_BASE_M + (r * 65536 + g * 256 + b) * RGB_STEP_M


def pixel_size_m(bbox: Sequence[float], shape: tuple[int, int]) -> tuple[float, float]:
    """(dx, dy) in metres of one pixel of a grid covering bbox."""
    w, s, e, n = bbox
    mid = math.radians((s + n) / 2)
    dx = math.radians(e - w) * EARTH_RADIUS_M * math.cos(mid) / shape[1]
    dy = math.radians(n - s) * EARTH_RADIUS_M / shape[0]
    return dx, dy


def hillshade(elev: np.ndarray, dx: float, dy: float, z_factor: float = 1.0) -> np.ndarray:
    """Multidirectional hillshade in [0, 1]; rows north to south."""
    dz_drow, dz_dx = np.gradient(elev.astype(np.float64) * z_factor, dy, dx)
    dz_dy = -dz_drow  # rows go north -> south; flip so +y is north
    slope = np.arctan(np.hypot(dz_dx, dz_dy))
    aspect = np.arctan2(-dz_dy, -dz_dx)  # downslope direction (math angle: east = 0, north = pi/2)
    alt = math.radians(SUN_ALTITUDE_DEG)
    shade = np.zeros_like(elev, dtype=np.float64)
    for azimuth_deg, weight in HILLSHADE_LIGHTS:
        az = math.radians(90.0 - azimuth_deg)  # compass bearing -> math angle
        lit = math.sin(alt) * np.cos(slope) + math.cos(alt) * np.sin(slope) * np.cos(az - aspect)
        shade += weight * np.clip(lit, 0, 1)
    return np.clip(shade / sum(w for _, w in HILLSHADE_LIGHTS), 0, 1)


def write_terrain_rgb(elev: np.ndarray, out_path: Path, width: int = 1024) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(encode_terrain_rgb(resample(elev, width)), mode="RGB").save(out_path)
    return out_path


def write_hillshade(
    elev: np.ndarray, bbox: Sequence[float], out_path: Path, width: int = 2048, z_factor: float = 1.0
) -> Path:
    grid = resample(elev, width)
    dx, dy = pixel_size_m(bbox, grid.shape)
    shade = hillshade(grid, dx, dy, z_factor)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((shade * 255).astype(np.uint8), mode="L").save(out_path)
    return out_path
