import numpy as np

from app.assets.composite import bad_share, median_composite, native_width


def test_median_drops_transient_cloud_and_ignores_nodata():
    ground = np.full((4, 4, 3), 100, dtype=np.uint8)
    cloudy = ground.copy()
    cloudy[:2] = 240
    nodata = ground.copy()
    nodata[:, :2] = 0
    out = median_composite([ground, cloudy, ground, nodata])
    assert np.all(out == 100)


def test_pixel_without_any_data_stays_black():
    a = np.zeros((2, 2, 3), dtype=np.uint8)
    assert np.all(median_composite([a, a]) == 0)


def test_bad_share_counts_nodata_and_grey_bright_cloud_not_colour():
    img = np.full((10, 10, 3), 90, dtype=np.uint8)
    img[0] = 0           # no data
    img[1] = 230         # grey bright -> cloud
    img[2] = (250, 200, 120)  # bright but coloured (sand) -> fine
    assert abs(bad_share(img) - 0.2) < 1e-9


def test_native_width_is_capped_and_scales_with_bbox():
    assert native_width((-114.9, 35.9, -114.0, 36.6)) == 4096
    assert 900 < native_width((7.95, 46.38, 8.15, 46.56)) < 1100
