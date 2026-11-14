"""Story-mode trend / yearly / water maps from synthetic AppEEARS NetCDF. No network."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pymannkendall as mk
import pytest
from PIL import Image

from app.assets import maps
from app.catalog import load_catalog
from app.extractors import water
from tests.nc_synth import trend_cube, write_layer, write_lst

LAKE_BBOX = (-114.9, 35.9, -114.0, 36.6)
NY, NX = 8, 10
BASE_SIZE = (450, 350)


@pytest.fixture
def lake_env(tmp_path):
    cache = tmp_path / "cache"
    sites = tmp_path / "sites"
    (sites / "lake_mead").mkdir(parents=True)
    Image.new("RGB", BASE_SIZE).save(sites / "lake_mead" / "base.jpg")
    times = pd.date_range("2002-12-27", "2024-12-31", freq="8D")  # real file starts 2002-12-27
    slope = np.zeros((NY, NX))
    slope[:, : NX // 2] = 0.15  # west half warms 1.5 °C/decade, east half flat
    kelvin = trend_cube(times, NY, NX, base=300.0, slope_per_year=slope, amp=10.0, noise=0.8)
    kelvin[:, 0, -1] = np.nan  # never observed -> transparent
    qc = np.where(np.isfinite(kelvin), 0, 2)
    qc[:, -1, :] = 129  # LST error > 2 K on the southern row -> dropped by QC
    write_lst(cache / "lake_mead" / "MOD11A2.061_1km_aid0001.nc", kelvin, times, LAKE_BBOX, qc)
    return cache, sites


def rgba(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGBA"))


def test_trend_png_sign_colours_and_faded_pixels(lake_env):
    cache, sites = lake_env
    maps.build_site_maps("lake_mead", cache, sites, load_catalog())
    site = sites / "lake_mead"
    img = rgba(site / "trend_lst_day.png")
    assert img.shape[:2] == (BASE_SIZE[1], BASE_SIZE[0])  # same aspect as base.jpg
    west = img[img.shape[0] // 2, img.shape[1] // 8]
    east = img[img.shape[0] // 2, img.shape[1] * 7 // 8]
    assert west[0] > west[2] + 60  # warming -> red end of RdBu_r
    assert west[3] == maps.ALPHA_SIGNIFICANT
    assert east[3] == maps.ALPHA_FADED  # flat + noise -> not significant, drawn faded
    assert img[0, -1, 3] == 0  # no data -> transparent
    assert img[-1, img.shape[1] // 8, 3] == 0  # QC-rejected row -> transparent
    meta = json.loads((site / "trend_lst_day.json").read_text())
    assert meta["vmin"] == -meta["vmax"] and 1.2 < meta["vmax"] < 2.0
    assert meta["unit"] == "°C per decade" and meta["colormap"] == "RdBu_r"
    assert meta["legend"]["more"].startswith("↑ more") and meta["legend"]["less"].startswith("↓ less")
    assert 0.4 <= meta["share_significant"] <= 0.65


def test_year_pngs_one_per_year_with_shared_scale(lake_env):
    cache, sites = lake_env
    maps.build_site_maps("lake_mead", cache, sites, load_catalog())
    site = sites / "lake_mead"
    pngs = sorted(site.glob("year_lst_day_*.png"))
    assert len(pngs) == 22 and pngs[0].name == "year_lst_day_2003.png"
    meta = json.loads((site / "year_lst_day.json").read_text())
    assert meta["years"] == list(range(2003, 2025)) and meta["vmin"] == -meta["vmax"]
    first, last = rgba(pngs[0]), rgba(pngs[-1])
    col = first.shape[1] // 8
    assert first[first.shape[0] // 2, col, 2] > first[first.shape[0] // 2, col, 0]  # 2003 cooler -> blue
    assert last[last.shape[0] // 2, col, 0] > last[last.shape[0] // 2, col, 2]  # 2024 warmer -> red


def test_sen_mk_grid_matches_pymannkendall_on_one_pixel():
    rng = np.random.default_rng(3)
    years = list(range(2003, 2025))
    series = 0.05 * np.arange(22) + rng.normal(0, 0.3, 22)
    annual = np.stack([np.full((2, 2), v) for v in series])
    annual[:, 1, 1] = np.nan
    annual[5, 0, 1] = np.nan  # gap year
    slope, p = maps.sen_mk_grid(years, annual)
    ref = mk.original_test(series)
    assert slope[0, 0] == pytest.approx(ref.slope * 10, rel=1e-9)
    assert p[0, 0] == pytest.approx(ref.p, rel=1e-6)
    assert np.isfinite(slope[0, 1]) and np.isnan(slope[1, 1]) and np.isnan(p[1, 1])


def test_negative_snow_trend_is_drawn_red_less(tmp_path):
    """RdBu for snow: losing snow must land on the red ('↓ less') end."""
    cat = load_catalog()
    snow = next(v for v in cat if v.id == "snow_cover")
    times = pd.date_range("2003-01-01", "2024-12-01", freq="MS")
    cube = trend_cube(times, 4, 4, base=60.0, slope_per_year=np.full((4, 4), -1.5), amp=20.0, noise=1.0)
    grid = maps.Grid(times, cube, np.linspace(46.5, 46.4, 4), np.linspace(8.0, 8.1, 4))
    maps.write_variable_maps(snow, grid, tmp_path, (7.95, 46.38, 8.15, 46.56))
    px = rgba(tmp_path / "trend_snow_cover.png")[0, 0]
    assert px[0] > px[2] and px[3] == maps.ALPHA_SIGNIFICANT


def test_water_masks_show_the_lake_shrinking(tmp_path):
    cache, sites = tmp_path / "cache", tmp_path / "sites"
    (sites / "lake_mead").mkdir(parents=True)
    times = pd.date_range("2003-01-01", "2024-12-31", freq="32D")
    green = np.full((len(times), NY, NX), 0.08)
    nir = np.full((len(times), NY, NX), 0.30)
    state = np.zeros((len(times), NY, NX))
    for k, t in enumerate(times):
        cols = max(1, 8 - (t.year - 2003) // 3)  # lake loses a column every 3 years
        nir[k, :, :cols] = 0.02
    bundle = cache / "lake_mead_water"
    write_layer(bundle / "MOD09A1.061_500m_aid0001.nc", water.GREEN, green, times, LAKE_BBOX, "int16", -28672, 0.0001)
    write_layer(bundle / "MOD09A1.061_500m_aid0001_b.nc", water.NIR, nir, times, LAKE_BBOX, "int16", -28672, 0.0001)
    write_layer(bundle / "MOD09A1.061_500m_aid0001_s.nc", water.STATE, state, times, LAKE_BBOX, "uint16", 65535)
    # one file per layer is not how AppEEARS ships it; merge into one like the real bundle
    import xarray as xr

    merged = xr.merge([xr.open_dataset(p) for p in sorted(bundle.glob("*.nc"))], compat="override")
    merged.load().to_netcdf(tmp_path / "merged.nc")
    for p in bundle.glob("*.nc"):
        p.unlink()
    (tmp_path / "merged.nc").rename(bundle / "MOD09A1.061_500m_aid0001.nc")

    maps.build_site_maps("lake_mead", cache, sites, load_catalog())
    site = sites / "lake_mead"
    assert len(list(site.glob("year_water_*.png"))) == 22
    meta = json.loads((site / "year_water.json").read_text())
    assert meta["area_km2"]["2003"] > meta["area_km2"]["2024"] > 0
    img = rgba(site / "year_water_2003.png")
    assert tuple(img[img.shape[0] // 2, 2]) == maps.WATER_RGBA
    assert img[img.shape[0] // 2, -2, 3] == 0
    monthly = water.fetch_water_area(bundle)
    assert monthly.notna().sum() > 200 and (bundle / water.CACHE_CSV).exists()
    assert water.fetch_water_area(bundle).equals(monthly)  # served from the CSV cache


def test_value_grid_round_trips(tmp_path):
    import numpy as np
    from PIL import Image

    from app.assets.maps import save_values_png, value_encoding

    vals = np.array([[-1.5, 0.0], [np.nan, 0.75]])
    off, scale = value_encoding(vals)
    path = save_values_png(vals, (2, 2), off, scale, tmp_path / "v.png")
    code = np.asarray(Image.open(path)).astype(float)
    assert code[1, 0] == 0
    back = off + scale * code
    assert np.allclose(back[[0, 0, 1], [0, 1, 1]], [-1.5, 0.0, 0.75], atol=scale)
