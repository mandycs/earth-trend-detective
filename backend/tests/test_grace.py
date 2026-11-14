from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from app.extractors.grace import (
    FILE_GLOB,
    SERIES_NAME,
    extract_series,
    fetch_grace_series,
    regional_mean,
)

LATS = np.arange(-89.75, 90.0, 0.5)
LONS = np.arange(0.25, 360.0, 0.5)


def make_dataset(
    times: list[str],
    value_fn=None,
    bounds: list[tuple[str, str]] | None = None,
) -> xr.Dataset:
    """Global 0.5 deg grid; lwe = value_fn(lat2d, lon2d) + time index."""
    lat2d, lon2d = np.meshgrid(LATS, LONS, indexing="ij")
    base = np.zeros_like(lat2d) if value_fn is None else value_fn(lat2d, lon2d)
    data = np.stack([base + i for i in range(len(times))])
    ds = xr.Dataset(
        {"lwe_thickness": (("time", "lat", "lon"), data)},
        coords={"time": pd.to_datetime(times, format="ISO8601"), "lat": LATS, "lon": LONS},
    )
    if bounds is not None:
        tb = np.array([[np.datetime64(a), np.datetime64(b)] for a, b in bounds], dtype="datetime64[ns]")
        ds["time_bounds"] = (("time", "bounds"), tb)
    return ds


def test_regional_mean_clips_bbox_and_weights_by_cos_lat():
    # value = latitude -> weighted mean over [10, 20] lat is slightly below 15.
    ds = make_dataset(["2010-01-16"], lambda lat, lon: lat)
    mean = float(regional_mean(ds["lwe_thickness"], [10.0, 10.0, 12.0, 20.0])[0])
    cells = LATS[(LATS >= 10) & (LATS <= 20)]
    expected = np.average(cells, weights=np.cos(np.deg2rad(cells)))
    assert mean == pytest.approx(expected)
    assert 14.5 < mean < 15.0


def test_negative_longitudes_map_to_0_360():
    # Mark only cells west of Greenwich in lon 245..246 (= -115..-114).
    ds = make_dataset(["2010-01-16"], lambda lat, lon: np.where((lon > 245) & (lon < 246), 7.0, 0.0))
    mean = float(regional_mean(ds["lwe_thickness"], [-114.9, 35.9, -114.1, 36.6])[0])
    assert mean == pytest.approx(7.0)


def test_bbox_crossing_prime_meridian_wraps():
    ds = make_dataset(["2010-01-16"], lambda lat, lon: np.where((lon < 1) | (lon > 359), 3.0, 99.0))
    mean = float(regional_mean(ds["lwe_thickness"], [-0.9, 40.0, 0.9, 41.0])[0])
    assert mean == pytest.approx(3.0)


def test_bbox_smaller_than_cell_uses_nearest_cell():
    # Aletsch-like bbox: no cell centre inside, nearest centre is (46.25 or 46.75, 8.25 or 7.75).
    ds = make_dataset(["2010-01-16"], lambda lat, lon: lat * 1000 + lon)
    bbox = [7.95, 46.38, 8.15, 46.56]  # centre (8.05, 46.47)
    value = float(regional_mean(ds["lwe_thickness"], bbox)[0])
    assert value == pytest.approx(46.25 * 1000 + 8.25)


def test_extract_series_month_start_index_with_gaps():
    times = ["2017-05-16T12:00", "2017-06-15", "2018-06-16", "2018-07-16T12:00"]
    ds = make_dataset(times, lambda lat, lon: np.ones_like(lat))
    series = extract_series(ds, [-114.9, 35.9, -114.0, 36.6], 2017, 2018)
    assert series.name == SERIES_NAME
    assert len(series) == 24
    assert series.index[0] == pd.Timestamp("2017-01-01")
    assert series.index[-1] == pd.Timestamp("2018-12-01")
    assert (series.index.day == 1).all()
    assert series["2017-05-01"] == pytest.approx(1.0)
    assert series["2018-07-01"] == pytest.approx(4.0)
    assert series["2017-07-01":"2018-05-01"].isna().all()
    assert int(series.notna().sum()) == 4


def test_straddling_solution_moves_to_free_month():
    times = ["2011-11-01T12:00", "2012-01-01", "2012-01-16T12:00"]
    bounds = [
        ("2011-10-17", "2011-11-16"),
        ("2011-12-17", "2012-01-15"),  # mid-time in Jan, but Dec is free
        ("2012-01-01", "2012-01-31"),
    ]
    ds = make_dataset(times, bounds=bounds)
    series = extract_series(ds, [10.0, 10.0, 12.0, 12.0], 2011, 2012)
    assert series["2011-11-01"] == pytest.approx(0.0)
    assert series["2011-12-01"] == pytest.approx(1.0)
    assert series["2012-01-01"] == pytest.approx(2.0)


def test_unresolvable_collision_is_averaged():
    ds = make_dataset(["2012-03-05", "2012-03-25"])
    series = extract_series(ds, [10.0, 10.0, 12.0, 12.0], 2012, 2012)
    assert series["2012-03-01"] == pytest.approx(0.5)


def test_fetch_uses_cached_file_without_network(tmp_path: Path):
    ds = make_dataset(["2020-01-16", "2020-02-15"], lambda lat, lon: np.full_like(lat, 2.0))
    name = FILE_GLOB.replace("*", "200204_202609.GLO.RL06.3M.MSCNv04CRI")
    ds.to_netcdf(tmp_path / name)
    series = fetch_grace_series([7.95, 46.38, 8.15, 46.56], 2020, 2020, cache_dir=tmp_path)
    assert len(series) == 12
    assert series["2020-02-01"] == pytest.approx(3.0)
    assert series["2020-03-01":].isna().all()
