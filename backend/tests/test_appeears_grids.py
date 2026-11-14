"""AppEEARS NetCDF grids, pixel-wise snow cover, stats scale detection and watch. No network."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.catalog import load_catalog
from app.extractors import appeears as ae
from tests.nc_synth import write_layer, write_lst

FIXTURE = Path(__file__).parent / "fixtures" / "appeears_stats_lst_snow.csv"
ALETSCH_BBOX = (7.95, 46.38, 8.15, 46.56)


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


def var(catalog, var_id):
    return next(v for v in catalog if v.id == var_id)


def write_snow(path: Path, values: np.ndarray, times: pd.DatetimeIndex) -> Path:
    """MOD10A1-like: uint8, 255 fill, flags 200-254 stored as plain values, no scale_factor."""
    return write_layer(path, ae.SNOW_BAND, values, times, ALETSCH_BBOX, "uint8", 255)


# --------------------------------------------------------------------------- grids


def test_open_layer_decodes_julian_time_scale_and_fill(tmp_path, catalog):
    times = pd.date_range("2003-01-01", periods=4, freq="8D")
    k = np.full((4, 3, 2), 300.0)
    k[0, 0, 0] = np.nan  # fill (0)
    write_lst(tmp_path / "MOD11A2.061_1km_aid0001.nc", k, times, ALETSCH_BBOX)
    da = ae.open_layer(tmp_path, "LST_Day_1km")
    assert isinstance(da.indexes["time"], pd.DatetimeIndex)
    assert list(da["time"].values) == list(times.values)
    assert da.attrs["etd_scaled"] is True
    assert da["lat"].values[0] > da["lat"].values[-1]
    celsius = ae.layer_to_units(da, var(catalog, "lst_day")).values
    assert np.isnan(celsius[0, 0, 0])
    assert np.nanmax(np.abs(celsius - 26.85)) < 0.05


def test_open_layer_merges_year_chunk_subfolders(tmp_path):
    for i, start in enumerate(["2003-01-01", "2009-01-01"]):
        times = pd.date_range(start, periods=3, freq="D")
        write_snow(tmp_path / f"{2003 + 6 * i}-x" / "MOD10A1.061_500m_aid0001.nc", np.full((3, 2, 2), 50.0), times)
    da = ae.open_layer(tmp_path, ae.SNOW_BAND)
    assert da.sizes["time"] == 6 and pd.DatetimeIndex(da["time"].values).is_monotonic_increasing


def test_open_layer_none_without_netcdf(tmp_path):
    assert ae.open_layer(tmp_path, ae.SNOW_BAND) is None
    assert ae.snow_cover_monthly(tmp_path / "nope") is None


# --------------------------------------------------------------------------- snow


def test_snow_flags_are_masked_per_pixel_before_averaging(tmp_path):
    times = pd.date_range("2010-01-01", "2010-02-28", freq="D")
    v = np.full((len(times), 4, 5), 80.0)
    v[:, :, :2] = 250.0  # cloud flag on 40% of the pixels, every day of January...
    jan = np.asarray(times.month == 1)
    feb = ~jan
    v[np.ix_(feb, range(4), range(5))] = 239.0  # ... and night/ocean on all of February
    v[np.where(feb)[0][:3], :, :] = 40.0  # except 3 of 28 days (10.7% < 20%)
    write_snow(tmp_path / "MOD10A1.061_500m_aid0001.nc", v, times)
    series = ae.snow_cover_monthly(tmp_path)
    assert series[pd.Timestamp("2010-01-01")] == pytest.approx(80.0)  # flags never pull it up
    assert np.isnan(series[pd.Timestamp("2010-02-01")])


def test_fetch_site_series_prefers_pixel_snow_over_stats_csv(tmp_path, catalog):
    bundle = tmp_path / "aletsch" / "2003-2008"
    bundle.mkdir(parents=True)
    shutil.copy(FIXTURE, bundle / "MOD10A1-061-Statistics.csv")
    times = pd.date_range("2003-01-01", "2003-01-31", freq="D")
    write_snow(bundle / "MOD10A1.061_500m_aid0001.nc", np.full((len(times), 3, 3), 33.0), times)
    series = ae.fetch_site_series("aletsch", cache_dir=tmp_path, catalog=catalog)
    assert series["snow_cover"][pd.Timestamp("2003-01-01")] == pytest.approx(33.0)
    assert "lst_day" in series  # stats CSV still used for the other layers


# --------------------------------------------------------------------------- stats scale


def test_stats_scale_detects_raw_dn(catalog):
    lst = var(catalog, "lst_day")
    assert ae._stats_scale(pd.Series([14500.0, 15000.0]), lst) == pytest.approx(0.02)
    assert ae._stats_scale(pd.Series([290.0, 300.0]), lst) == 1.0
    ndvi = var(catalog, "ndvi")
    assert ae._stats_scale(pd.Series([3500.0, 4200.0]), ndvi) == pytest.approx(0.0001)
    assert ae._stats_scale(pd.Series([0.35, 0.42]), ndvi) == 1.0


def test_parse_stats_csv_raw_dn_lst_lands_in_celsius(tmp_path, catalog):
    df = pd.read_csv(FIXTURE)
    lst = df["Dataset"] == "LST_Day_1km"
    df.loc[lst, "Mean"] = df.loc[lst, "Mean"] / 0.02
    path = tmp_path / "raw.csv"
    df.to_csv(path, index=False)
    series = ae.parse_stats_csv(path, [var(catalog, "lst_day")])["lst_day"]
    assert series[pd.Timestamp("2003-01-01")] == pytest.approx(1.0, abs=0.01)
    assert ae.check_units(series.to_frame().to_dict("series")) == []


def test_check_units_flags_kelvin():
    s = pd.Series([290.0, 300.0], index=pd.date_range("2003-01-01", periods=2, freq="MS"))
    assert ae.check_units({"lst_day": s}) == ["lst_day"]


# --------------------------------------------------------------------------- watch


def rec(key, site, tid):
    return ae.TaskRecord(key, site, tid, "now")


@pytest.fixture
def watch_env(tmp_path, monkeypatch):
    tasks = {
        "lake_mead": rec("lake_mead", "lake_mead", "t1"),
        "lake_mead_water": rec("lake_mead_water", "lake_mead_water", "t2"),
        "aletsch@2003-2008": rec("aletsch@2003-2008", "aletsch", "t3"),
    }
    ae.save_tasks(tasks, tmp_path)
    schedule = {"t1": ["pending", "done"], "t2": ["done"], "t3": ["processing", "error"]}
    downloads: list[str] = []

    def fake_status(client, task_id):
        seq = schedule[task_id]
        return {"status": seq.pop(0) if len(seq) > 1 else seq[0]}

    def fake_download(client, task_id, dest, only_csv=False):
        downloads.append(task_id)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / f"{task_id}.nc").write_bytes(b"x")
        return [dest / f"{task_id}.nc"]

    monkeypatch.setattr(ae, "task_status", fake_status)
    monkeypatch.setattr(ae, "download_bundle", fake_download)
    return tmp_path, downloads


def test_watch_downloads_as_ready_and_exits(watch_env):
    cache, downloads = watch_env
    sleeps, built = [], []
    final = ae.watch(None, cache, interval=5, sleep=sleeps.append, on_site_complete=built.append)
    assert final == {"lake_mead_water": "done", "lake_mead": "done", "aletsch@2003-2008": "error"}
    assert downloads == ["t2", "t1"]
    assert sleeps == [5]
    assert built == ["lake_mead"]  # aletsch never completes; water folds into lake_mead
    assert (cache / "lake_mead_water" / ".done_t2").exists()
    # idempotent: everything already downloaded -> nothing fetched again
    again = ae.watch(None, cache, interval=5, sleep=sleeps.append, max_rounds=1)
    assert downloads == ["t2", "t1"] and again["lake_mead"] == "done"


def test_watch_token_rejected_raises(tmp_path, monkeypatch):
    import httpx

    ae.save_tasks({"x": rec("x", "x", "t9")}, tmp_path)

    def denied(client, task_id):
        request = httpx.Request("GET", "https://example/task")
        raise httpx.HTTPStatusError("401", request=request, response=httpx.Response(401, request=request))

    monkeypatch.setattr(ae, "task_status", denied)
    with pytest.raises(RuntimeError, match="token"):
        ae.watch(None, tmp_path, sleep=lambda s: None, max_rounds=1)


def test_chunked_tasks_get_their_own_folder(tmp_path):
    assert ae.bundle_dest(tmp_path, rec("aletsch@2009-2014", "aletsch", "t")) == tmp_path / "aletsch" / "2009-2014"
    assert ae.bundle_dest(tmp_path, rec("donana", "donana", "t")) == tmp_path / "donana"
    assert ae.story_site("lake_mead_water") == "lake_mead"


# --------------------------------------------------------------------------- real-bundle regressions


QC_ONLY_CSV = """File,aid,Date,2,17,33,49,65,81,97,113,129,145
QC_Day_2002361_aid0001,aid0001,2002-12-27 00:00:00+00:00,6.0,3307.0,,,555.0,2917.0,,,,
QC_Day_2003001_aid0001,aid0001,2003-01-01 00:00:00+00:00,16.0,5211.0,,,540.0,915.0,,,,
"""
QC_LOOKUP_CSV = """Value,MODLAND,Data Quality flag,Emis Error flag,LST Error Flag
2,LST not produced due to cloud effects,Good data quality,Average emissivity error <= 0.01,Average LST error <= 1K
"""


def lst_bundle(bundle: Path, kelvin: np.ndarray, times: pd.DatetimeIndex, qc=None) -> Path:
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / "MOD11A2-061-QC-Day-Statistics-QA.csv").write_text(QC_ONLY_CSV)
    (bundle / "MOD11A2-061-QC-Day-lookup.csv").write_text(QC_LOOKUP_CSV)
    return write_lst(bundle / "MOD11A2.061_1km_aid0001.nc", kelvin, times, (-114.9, 35.9, -114.0, 36.6), qc)


def test_qc_only_csv_bundle_reads_lst_from_netcdf(tmp_path, catalog):
    """Real lake_mead bundle shape: QC statistics CSV next to the NetCDF -> no KeyError."""
    times = pd.date_range("2002-12-27", "2003-03-31", freq="8D")
    lst_bundle(tmp_path / "lake_mead", np.full((len(times), 4, 4), 310.15), times)
    assert ae.stats_csvs(tmp_path / "lake_mead") == []
    assert ae.parse_bundle(tmp_path / "lake_mead", list(catalog)) == {}
    series = ae.fetch_site_series("lake_mead", cache_dir=tmp_path, catalog=catalog)
    assert series["lst_day"][pd.Timestamp("2003-02-01")] == pytest.approx(37.0, abs=0.01)


def test_lst_qc_filter_drops_large_error_pixels(tmp_path, catalog):
    times = pd.date_range("2003-01-01", periods=3, freq="8D")
    k = np.full((3, 2, 2), 300.15)
    k[:, 0, 0] = 350.15  # bad pixel ...
    qc = np.zeros((3, 2, 2), dtype=int)
    qc[:, 0, 0] = 129  # ... flagged LST error > 2 K
    qc[:, 0, 1] = 65  # other quality, error <= 2 K -> kept
    lst_bundle(tmp_path, k, times, qc)
    units = ae.load_layer_units(tmp_path, var(catalog, "lst_day"))
    assert np.isnan(units.values[:, 0, 0]).all()
    assert np.isfinite(units.values[:, 1:, :]).all() and np.isfinite(units.values[:, 0, 1]).all()
    assert ae.lst_qc_good(np.array([np.nan, 0, 17, 65, 129, 145, 2])).tolist() == [True, True, True, True, False, False, False]


def test_netcdf_preferred_over_matching_stats_csv(tmp_path, catalog):
    times = pd.date_range("2003-01-01", "2003-01-31", freq="8D")
    bundle = tmp_path / "lake_mead"
    lst_bundle(bundle, np.full((len(times), 3, 3), 283.15), times)
    shutil.copy(FIXTURE, bundle / "MOD11A2-061-Statistics.csv")  # says ~1-2 °C in Jan 2003
    series = ae.fetch_site_series("lake_mead", cache_dir=tmp_path, catalog=catalog)
    assert series["lst_day"][pd.Timestamp("2003-01-01")] == pytest.approx(10.0, abs=0.01)


def test_stats_csv_fallback_when_no_netcdf_layer(tmp_path, catalog):
    bundle = tmp_path / "lake_mead"
    bundle.mkdir()
    shutil.copy(FIXTURE, bundle / "MOD11A2-061-Statistics.csv")
    series = ae.fetch_site_series("lake_mead", cache_dir=tmp_path, catalog=catalog)
    assert series["lst_day"][pd.Timestamp("2003-01-01")] == pytest.approx(1.0, abs=0.01)
