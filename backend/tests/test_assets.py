import io
import zipfile

import httpx
import numpy as np
import pytest
import respx
from PIL import Image

from app.assets import dem
from app.assets.gibs import GIBS_WMS_URL, fetch_base_image, wms_params


def test_wms_params_use_lat_lon_axis_order_and_keep_aspect():
    p = wms_params((-114.9, 35.9, -114.0, 36.6), "2024-06-20", 900)
    assert p["BBOX"] == "35.9,-114.9,36.6,-114.0"
    assert p["WIDTH"] == "900" and p["HEIGHT"] == "700"


@respx.mock
def test_fetch_base_image_rejects_non_image(tmp_path):
    respx.get(GIBS_WMS_URL).mock(return_value=httpx.Response(200, text="<ServiceException/>",
                                                             headers={"content-type": "text/xml"}))
    with pytest.raises(RuntimeError):
        fetch_base_image((0, 0, 1, 1), "2024-01-01", tmp_path / "base.jpg")


def test_tile_names_and_bbox_tiles():
    assert dem.tile_name(36, -115) == "n36w115"
    assert dem.tile_name(-1, 7) == "s01e007"
    assert dem.tiles_for_bbox((-114.9, 35.9, -114.0, 36.6)) == [(35, -115), (36, -115)]
    assert dem.tiles_for_bbox((7.95, 46.38, 8.15, 46.56)) == [(46, 7), (46, 8)]


def _tile(value_fn) -> np.ndarray:
    r, c = np.mgrid[0:dem.TILE_SIZE, 0:dem.TILE_SIZE]
    return value_fn(r, c).astype(np.float32)


def test_read_hgt_fills_voids():
    arr = np.full((dem.TILE_SIZE, dem.TILE_SIZE), 100, dtype=">i2")
    arr[0, 0] = dem.VOID
    out = dem.read_hgt(arr.tobytes())
    assert out[0, 0] == 100


def test_mosaic_stacks_north_tile_on_top_and_crop_picks_bbox():
    south = _tile(lambda r, c: np.full(r.shape, 1.0))
    north = _tile(lambda r, c: np.full(r.shape, 2.0))
    grid, west, north_lat = dem.mosaic({(35, -115): south, (36, -115): north})
    assert (west, north_lat) == (-115.0, 37.0)
    assert grid[0, 0] == 2.0 and grid[-1, 0] == 1.0
    cropped = dem.crop(grid, west, north_lat, (-114.9, 36.2, -114.5, 36.8))
    assert np.all(cropped == 2.0)


def test_heightmap_from_cached_tiles_is_16bit_png(tmp_path):
    arr = _tile(lambda r, c: 100 + c).astype(">i2")  # rises eastward
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("n35w115.hgt", arr.tobytes())
    for lat in (35, 36):
        (tmp_path / f"NASADEM_HGT_{dem.tile_name(lat, -115)}.zip").write_bytes(buf.getvalue())
    hm = dem.build_heightmap((-114.9, 35.9, -114.1, 36.6), tmp_path / "hm.png", width=200, cache_dir=tmp_path)
    img = Image.open(hm.path)
    assert img.mode == "I;16" and img.size[0] == 200
    px = np.array(img)
    assert px[:, -1].mean() > px[:, 0].mean()
    assert hm.max_m > hm.min_m
