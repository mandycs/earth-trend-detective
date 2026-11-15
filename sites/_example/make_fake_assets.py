"""
Generate FAKE placeholder assets for sites/_example so the 3D story mode can be
built and demoed before the real pipeline exists.

Nothing here is real data. Every output is synthetic. The filenames and formats
match the story-mode contract in docs/team/PLAN.md section 6:

    heightmap.png         8-bit grayscale, 512x512, white = high
    base.jpg              1024x1024 satellite-like colour
    trend_<var>.png       512x512 RGBA, diverging, alpha = significance
    year_<var>_<YYYY>.png 512x512 RGB anomaly frame per year

Run with:
    uv run --python 3.11 --with pillow --with numpy python sites/_example/make_fake_assets.py
"""

from __future__ import annotations

import pathlib

import numpy as np
from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
SIZE = 512
YEARS = list(range(2003, 2025))
VAR = "grace_tws"
RNG = np.random.default_rng(42)


def fractal_noise(size: int, octaves: int = 6, persistence: float = 0.5) -> np.ndarray:
    """Value-noise via bicubic upsampling of random grids. Range roughly 0..1."""
    total = np.zeros((size, size), dtype=np.float32)
    amplitude = 1.0
    norm = 0.0
    for octave in range(octaves):
        cells = 2 ** (octave + 2)
        grid = RNG.random((cells, cells)).astype(np.float32)
        layer = np.asarray(
            Image.fromarray((grid * 255).astype(np.uint8)).resize(
                (size, size), Image.BICUBIC
            ),
            dtype=np.float32,
        ) / 255.0
        total += layer * amplitude
        norm += amplitude
        amplitude *= persistence
    total /= norm
    total -= total.min()
    total /= total.max()
    return total


def build_height(size: int = SIZE) -> tuple[np.ndarray, np.ndarray]:
    """Return (height 0..1, water_mask bool) for a fake reservoir basin."""
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float32) / size

    # Mountain rim: high at the borders, low in the middle.
    dx = np.minimum(xs, 1 - xs)
    dy = np.minimum(ys, 1 - ys)
    rim = np.clip(np.minimum(dx, dy) * 3.2, 0, 1) ** 0.7

    # A river/lake basin running diagonally through the middle.
    channel_axis = ys - (0.25 + 0.55 * xs)
    channel = np.exp(-((channel_axis / 0.085) ** 2))
    basin = -0.55 * channel

    # Ridges, plus fine detail.
    ridges = 1.0 - np.abs(fractal_noise(size, 5) * 2 - 1)
    detail = fractal_noise(size, 7)

    height = 0.20 + 0.72 * rim + 0.20 * ridges**2 + 0.10 * detail + basin
    height = np.clip(height, 0, 1)
    height -= height.min()
    height /= height.max()

    # Water sits in the lowest part of the basin.
    water = height < np.quantile(height, 0.17)
    return height, water


def hillshade(height: np.ndarray, azimuth: float = 315.0, altitude: float = 42.0) -> np.ndarray:
    """Simple Lambert hillshade from finite differences, in 0..1."""
    gy, gx = np.gradient(height * 60.0)
    slope = np.pi / 2 - np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az = np.radians(360.0 - azimuth + 90.0)
    alt = np.radians(altitude)
    shade = np.sin(alt) * np.sin(slope) + np.cos(alt) * np.cos(slope) * np.cos(az - aspect)
    return np.clip(shade, 0, 1)


def build_base(height: np.ndarray, water: np.ndarray, size: int = 1024) -> Image.Image:
    h = np.asarray(
        Image.fromarray((height * 255).astype(np.uint8)).resize((size, size), Image.BICUBIC),
        dtype=np.float32,
    ) / 255.0
    w = (
        np.asarray(
            Image.fromarray((water * 255).astype(np.uint8)).resize(
                (size, size), Image.BICUBIC
            ),
            dtype=np.float32,
        )
        / 255.0
        > 0.5
    )
    shade = hillshade(h)

    # Desert ground: tan at low elevation, red-brown rock higher up.
    rock = np.stack(
        [
            0.62 + 0.16 * h,
            0.49 + 0.13 * h,
            0.33 + 0.10 * h,
        ],
        axis=-1,
    )
    grain = fractal_noise(size, 7)[..., None]
    rock = rock * (0.80 + 0.40 * grain)
    rock *= (0.55 + 0.65 * shade)[..., None]

    # Water: dark blue-green, flat, with a hint of depth from height.
    floor = float(np.min(h[w])) if w.any() else 0.2
    depth = np.clip(1 - (h / max(floor, 1e-6)), 0, 1)
    lake = np.stack(
        [
            0.06 + 0.05 * depth,
            0.16 + 0.10 * depth,
            0.26 + 0.14 * depth,
        ],
        axis=-1,
    )
    lake *= 0.90 + 0.20 * grain

    rgb = np.where(w[..., None], lake, rock)
    return Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8), mode="RGB")


def diverging_rgba(values: np.ndarray, alpha: np.ndarray) -> Image.Image:
    """Blue (negative) - white (zero) - red (positive), straight from RGB stops."""
    v = np.clip(values, -1, 1)
    t = np.abs(v)[..., None]
    dry = np.array([0.80, 0.16, 0.10], dtype=np.float32)   # red  = losing water
    wet = np.array([0.10, 0.32, 0.72], dtype=np.float32)   # blue = gaining water
    mid = np.array([0.93, 0.90, 0.84], dtype=np.float32)
    tint = np.where((v < 0)[..., None], dry, wet)
    rgb = mid * (1 - t) + tint * t
    a = np.clip(alpha, 0, 1)[..., None]
    return Image.fromarray(
        np.concatenate([(rgb * 255), (a * 255)], axis=-1).astype(np.uint8), mode="RGBA"
    )


def main() -> None:
    height, water = build_height()
    h8 = (height * 255).astype(np.uint8)
    Image.fromarray(h8, mode="L").save(HERE / "heightmap.png", optimize=True)

    build_base(height, water).save(HERE / "base.jpg", quality=88, optimize=True)

    # Trend layer: strongest loss in the basin, never significant on the rim
    # (masked pixels are transparent, exactly like the real Sen/p-value output).
    ys, xs = np.mgrid[0:512, 0:512].astype(np.float32) / 512
    decay = np.clip(1.45 - np.hypot(xs - 0.5, ys - 0.5) * 2.9, 0, 1) ** 1.1
    trend = -decay * (0.55 + 0.45 * fractal_noise(512, 5))
    alpha = np.clip((decay - 0.42) * 2.6, 0, 1)
    diverging_rgba(trend, alpha).save(HERE / f"trend_{VAR}.png", optimize=True)

    # One anomaly frame per year: basin dries out progressively.
    for i, year in enumerate(YEARS):
        frac = i / (len(YEARS) - 1)
        values = trend * (0.15 + 1.05 * frac) + 0.10 * (fractal_noise(512, 4) - 0.5) * frac
        frame_alpha = alpha * (0.35 + 0.65 * frac)
        diverging_rgba(values, frame_alpha).save(
            HERE / f"year_{VAR}_{year}.png", optimize=True
        )

    print(f"wrote heightmap.png, base.jpg, trend_{VAR}.png and {len(YEARS)} year frames to {HERE}")


if __name__ == "__main__":
    main()
