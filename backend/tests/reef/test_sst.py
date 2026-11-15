import json

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from PIL import Image

from app import layers
from app.assets import maps
from app.catalog import load_catalog
from app.extractors.erddap import ErddapError
from app.reef import sst

BBOX = (145.5, -21.0, 150.0, -17.0)
LATS = np.array([-20.0, -19.95, -19.9, -19.85])  # ascending, as ERDDAP answers
LONS = np.array([147.0, 147.05, 147.1, 147.15, 147.2])
LAND = (2, 4)  # (lat index in the ascending fake, lon index): always NaN
SOUTH_MARK = (0, 1)  # southern edge pixel planted 5 °C warmer


def _fake_year(year, drop=()):
    times = pd.date_range(f"{year}-01-01", periods=12, freq="MS") + pd.Timedelta(days=15)
    times = pd.DatetimeIndex([t for t in times if (t.year, t.month) not in drop])
    months = times.month.to_numpy()
    base = 26.0 + 2.0 * np.cos(2 * np.pi * (months - 2) / 12) + 0.03 * (year - 2003)
    cube = np.broadcast_to(base[:, None, None], (len(times), len(LATS), len(LONS))).copy()
    cube = cube + 0.01 * np.arange(len(LONS))[None, None, :]
    cube[:, SOUTH_MARK[0], SOUTH_MARK[1]] += 5.0
    cube[:, LAND[0], LAND[1]] = np.nan
    return xr.DataArray(
        cube,
        dims=("time", "latitude", "longitude"),
        coords={"time": times, "latitude": LATS, "longitude": LONS},
        name="sst",
        attrs={"missing_years": []},
    )


class FakeFetch:
    def __init__(self, drop=(), fail=()):
        self.calls = []
        self.drop = drop
        self.fail = set(fail)

    def __call__(self, dataset, variable, bbox, start, end, stride, **kwargs):
        self.calls.append((dataset, variable, tuple(bbox), start, end, stride))
        if start in self.fail:
            raise ErddapError("ERDDAP busy: HTTP 503")
        return _fake_year(start, self.drop)


@pytest.fixture
def sst_var():
    return next(v for v in load_catalog() if v.id == "sst")


def test_one_fetch_per_year_in_order_and_cached(tmp_path):
    fetch = FakeFetch()
    sst.mur_grid(range(2003, 2006), BBOX, tmp_path, fetch=fetch)
    assert fetch.calls == [
        ("jplMURSST41mday", "sst", BBOX, y, y, sst.MUR_STRIDE) for y in (2003, 2004, 2005)
    ]
    assert sst.MUR_STRIDE == 5
    assert (tmp_path / "mur_2003_145.5_-21.0_150.0_-17.0_s5.nc").is_file()
    again = FakeFetch()
    grid = sst.mur_grid(range(2003, 2006), BBOX, tmp_path, fetch=again)
    assert again.calls == []
    assert len(grid.times) == 36


def test_mur_grid_rows_run_north_to_south(tmp_path):
    grid = sst.mur_grid(range(2003, 2005), BBOX, tmp_path, fetch=FakeFetch())
    assert grid.lat[0] > grid.lat[-1]
    assert list(grid.lat) == sorted(LATS, reverse=True)
    assert list(grid.lon) == list(LONS)
    # the planted southern pixel is now in the last row, 5 °C above its row neighbour
    last = grid.monthly[:, -1, :]
    assert np.allclose(last[:, SOUTH_MARK[1]] - last[:, 0], 5.0 + 0.01 * SOUTH_MARK[1])
    assert np.allclose(grid.monthly[:, 0, 1] - grid.monthly[:, 0, 0], 0.01)
    assert all(t.day == 1 for t in grid.times)
    assert grid.missing_years == ()


def test_missing_month_keeps_year(tmp_path, sst_var):
    fetch = FakeFetch(drop={(2023, 6)})
    grid = sst.mur_grid(range(2003, 2025), BBOX, tmp_path, fetch=fetch)
    series = sst.box_mean_series(grid)
    assert series.name == "sst"
    assert np.isnan(series[pd.Timestamp("2023-06-01")])
    y2023 = series[series.index.year == 2023]
    assert len(y2023) == 12 and y2023.notna().sum() == 11
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    sst.write_sst_maps(sst_var, grid, site_dir, BBOX, 2003, 2024)
    assert (site_dir / "year_sst_2023.png").is_file()


def test_box_mean_ignores_land(tmp_path):
    grid = sst.mur_grid(range(2003, 2005), BBOX, tmp_path, fetch=FakeFetch())
    series = sst.box_mean_series(grid)
    assert series.notna().all()
    assert isinstance(series.index, pd.DatetimeIndex)
    assert all(t.day == 1 for t in series.index)
    expected = np.nanmean(grid.monthly[0])
    assert series.iloc[0] == pytest.approx(expected)


def test_failed_year_is_recorded_not_a_silent_gap(tmp_path, sst_var):
    fetch = FakeFetch(fail={2010})
    grid = sst.mur_grid(range(2003, 2025), BBOX, tmp_path, fetch=fetch)
    assert grid.missing_years == (2010,)
    assert not (tmp_path / "mur_2010_145.5_-21.0_150.0_-17.0_s5.nc").exists()
    series = sst.box_mean_series(grid)
    assert series[series.index.year == 2010].isna().all()
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    sst.write_sst_maps(sst_var, grid, site_dir, BBOX, 2003, 2024)
    trend = json.loads((site_dir / "trend_sst.json").read_text())
    yearly = json.loads((site_dir / "year_sst.json").read_text())
    assert trend["missing_years"] == [2010] and yearly["missing_years"] == [2010]
    assert 2010 not in yearly["years"]


def test_source_down_raises(tmp_path):
    with pytest.raises(ErddapError):
        sst.mur_grid(range(2003, 2010), BBOX, tmp_path, fetch=FakeFetch(fail={2003, 2004, 2005}))


def test_sst_maps_written(tmp_path, sst_var):
    grid = sst.mur_grid(range(2003, 2025), BBOX, tmp_path, fetch=FakeFetch())
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    sst.write_sst_maps(sst_var, grid, site_dir, BBOX, 2003, 2024)
    trend = json.loads((site_dir / "trend_sst.json").read_text())
    assert (site_dir / "trend_sst.png").is_file()
    assert trend["share_up"] == 1.0
    assert trend["unit"].endswith("per decade")
    assert trend["missing_years"] == []
    assert trend["colormap"] == "RdBu_r"
    assert trend["legend"]["more"] == "↑ warmer water"
    years = sorted(site_dir.glob("year_sst_*.png"))
    assert len(years) == 22
    assert (site_dir / "year_sst.json").is_file()
    # the land pixel (ascending row 2 -> descending row 1) stays transparent, north row up
    with Image.open(site_dir / "trend_sst.png") as im:
        rgba = np.asarray(im.convert("RGBA").resize((len(LONS), len(LATS)), Image.Resampling.NEAREST))
    assert rgba[len(LATS) - 1 - LAND[0], LAND[1], 3] == 0
    assert (rgba[..., 3] > 0).sum() == len(LATS) * len(LONS) - 1
    doc = layers.build_layers("great_barrier_reef", site_dir)
    by_id = {la["id"]: la for la in doc["layers"]}
    assert {"trend_sst", "year_sst"} <= set(by_id)
    for lid in ("trend_sst", "year_sst"):
        assert by_id[lid]["source"]["name"] != "unknown"
        assert "MUR" in by_id[lid]["source"]["name"]


def test_offline_without_cache_raises(tmp_path):
    fetch = FakeFetch()
    with pytest.raises(FileNotFoundError):
        sst.load_mur_year(2003, BBOX, tmp_path, fetch=fetch, offline=True)
    assert fetch.calls == []


def test_offline_reads_cache(tmp_path):
    sst.load_mur_year(2003, BBOX, tmp_path, fetch=FakeFetch())
    fetch = FakeFetch()
    year = sst.load_mur_year(2003, BBOX, tmp_path, fetch=fetch, offline=True)
    assert fetch.calls == []
    assert year.dims == ("time", "latitude", "longitude")
    assert float(year.latitude[0]) > float(year.latitude[-1])


def test_failed_last_year_stays_as_twelve_nan_months(tmp_path):
    grid = sst.mur_grid(range(2003, 2025), BBOX, tmp_path, fetch=FakeFetch(fail={2024}))
    assert grid.years == tuple(range(2003, 2025))
    assert grid.missing_years == (2024,)
    series = sst.box_mean_series(grid)
    assert series.index[0] == pd.Timestamp("2003-01-01")
    assert series.index[-1] == pd.Timestamp("2024-12-01")
    y2024 = series[series.index.year == 2024]
    assert len(y2024) == 12 and y2024.isna().all()


def test_failed_first_year_stays_as_twelve_nan_months(tmp_path):
    grid = sst.mur_grid(range(2003, 2025), BBOX, tmp_path, fetch=FakeFetch(fail={2003}))
    series = sst.box_mean_series(grid)
    assert series.index[0] == pd.Timestamp("2003-01-01")
    y2003 = series[series.index.year == 2003]
    assert len(y2003) == 12 and y2003.isna().all()
    assert series[series.index.year == 2004].notna().all()


CORNER_LATS = np.array([-21.0, -20.0, -19.0, -18.0, -17.0])  # ascending, bbox south..north
CORNER_LONS = np.array([145.5, 146.625, 147.75, 148.875, 150.0])  # bbox west..east
PLANT = (-18.0, 148.875)  # warms 0.1 °C/yr faster than the rest


def _corner_fetch(dataset, variable, bbox, start, end, stride, **kwargs):
    times = pd.date_range(f"{start}-01-01", periods=12, freq="MS") + pd.Timedelta(days=15)
    months = times.month.to_numpy()
    base = 26.0 + 2.0 * np.cos(2 * np.pi * (months - 2) / 12) + 0.03 * (start - 2003)
    cube = np.broadcast_to(base[:, None, None], (12, len(CORNER_LATS), len(CORNER_LONS))).copy()
    r, c = list(CORNER_LATS).index(PLANT[0]), list(CORNER_LONS).index(PLANT[1])
    cube[:, r, c] += 0.1 * (start - 2003)
    return xr.DataArray(
        cube, dims=("time", "latitude", "longitude"),
        coords={"time": times, "latitude": CORNER_LATS, "longitude": CORNER_LONS}, name="sst",
    )


def test_overlay_aligns_with_bbox_corners(tmp_path, sst_var):
    grid = sst.mur_grid(range(2003, 2025), BBOX, tmp_path, fetch=_corner_fetch)
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    sst.write_sst_maps(sst_var, grid, site_dir, BBOX, 2003, 2024)
    meta = json.loads((site_dir / "trend_sst.json").read_text())
    with Image.open(site_dir / meta["value_file"]) as im:
        width, height = im.size
        code = np.asarray(im).astype(float)
    assert (width, height) == maps.overlay_size(site_dir, BBOX)
    values = meta["value_offset"] + meta["value_scale"] * code
    # rows north -> south: lat -18 is row 1 of 5; lon 148.875 is column 3 of 5
    row, col = 1, 3
    y, x = int((row + 0.5) * height / 5), int((col + 0.5) * width / 5)
    assert values[y, x] == pytest.approx(1.3, abs=1e-3)  # (0.03 + 0.1) °C/yr per decade
    assert values[y, int(0.5 * width / 5)] == pytest.approx(0.3, abs=1e-3)
    assert values[int(0.5 * height / 5), x] == pytest.approx(0.3, abs=1e-3)
    assert values[int(4.5 * height / 5), int(4.5 * width / 5)] == pytest.approx(0.3, abs=1e-3)
