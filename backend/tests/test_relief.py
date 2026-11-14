import numpy as np
from PIL import Image

from app.assets.relief import (
    decode_terrain_rgb,
    encode_terrain_rgb,
    hillshade,
    pixel_size_m,
    write_hillshade,
    write_terrain_rgb,
)


def test_terrain_rgb_round_trip_keeps_decimetres():
    elev = np.array([[0.0, 165.3], [2373.0, 4171.9]])
    back = decode_terrain_rgb(encode_terrain_rgb(elev))
    assert np.allclose(back, elev, atol=0.051)


def test_terrain_rgb_png_is_lossless(tmp_path):
    elev = np.linspace(100, 4100, 64 * 64, dtype=np.float32).reshape(64, 64)
    path = write_terrain_rgb(elev, tmp_path / "h.png", width=64)
    back = decode_terrain_rgb(np.asarray(Image.open(path).convert("RGB")))
    assert np.allclose(back, elev, atol=0.06)


def test_hillshade_lights_northwest_facing_slope_more():
    # Rows run north->south, columns west->east: (r + c) grows to the south-east,
    # so this slope faces north-west, toward the main light.
    r, c = np.mgrid[0:50, 0:50]
    nw_facing = (r + c).astype(float) * 10
    se_facing = -nw_facing
    assert hillshade(nw_facing, 30, 30).mean() > hillshade(se_facing, 30, 30).mean()
    flat = hillshade(np.zeros((10, 10)), 30, 30)
    assert np.allclose(flat, flat[0, 0]) and 0 < flat[0, 0] < 1


def test_pixel_size_shrinks_east_west_with_latitude():
    dx_eq, dy_eq = pixel_size_m((0, -0.5, 1, 0.5), (100, 100))
    dx_60, _ = pixel_size_m((0, 59.5, 1, 60.5), (100, 100))
    assert abs(dx_60 / dx_eq - 0.5) < 0.01 and abs(dy_eq - 1112) < 5


def test_write_hillshade_keeps_aspect(tmp_path):
    elev = np.random.default_rng(0).normal(500, 50, (90, 120)).astype(np.float32)
    path = write_hillshade(elev, (0, 0, 1.2, 0.9), tmp_path / "hs.png", width=240)
    img = Image.open(path)
    assert img.mode == "L" and img.size == (240, 180)
