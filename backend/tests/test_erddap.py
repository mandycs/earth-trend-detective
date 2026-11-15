"""ERDDAP fetcher (sea temperature, chlorophyll, heat stress): offline, on recorded responses."""

from __future__ import annotations

import math
from pathlib import Path
from urllib.parse import unquote

import httpx
import numpy as np
import pandas as pd
import pytest

from app import gather
from app.catalog import load_catalog
from app.extractors import erddap
from app.investigate.runner import point_site

FIXTURES = Path(__file__).parent / "fixtures" / "erddap"


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _csv(name: str) -> httpx.Response:
    return httpx.Response(200, text=_text(name))


def _axes(url: str) -> list[str]:
    """The bracketed constraints of a griddap URL, decoded: ['(t0):1:(t1)', '(lat)', '(lon)']."""
    query = unquote(str(url).split("?", 1)[1])
    return [part.split("]")[0] for part in query.split("[")[1:]]


@pytest.fixture(autouse=True)
def _no_pause(monkeypatch):
    monkeypatch.setattr(erddap, "_sleep", lambda _s: None)


def _var(var_id: str):
    return next(v for v in load_catalog() if v.id == var_id)


# --------------------------------------------------------------------------- parsing and requests


def test_parses_monthly_csv():
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return _csv("mur_point_2010.csv")

    series, cell = erddap.fetch_point_monthly(
        "jplMURSST41mday", "sst", 36.0, -10.0, 2010, 2010, client=_client(handler)
    )
    # units row skipped, the 2011-01 row ERDDAP snaps onto the 12-31 stop dropped
    assert list(series.index) == list(pd.date_range("2010-01-01", "2010-03-01", freq="MS"))
    assert series.iloc[0] == pytest.approx(17.320068)
    assert series.dtype == float
    assert cell == (36.0, -10.0)
    assert series.attrs["cell"] == (36.0, -10.0)
    assert len(urls) == 1
    assert "%5B" in urls[0] and "%5D" in urls[0] and "[" not in urls[0]
    assert urls[0].startswith("https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST41mday.csv?sst%5B")


def test_requests_one_year_per_call_in_order():
    years: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        years.append(_axes(request.url)[0][1:5])
        return _csv("mur_point_2010.csv")

    erddap.fetch_point_monthly("jplMURSST41mday", "sst", 36.0, -10.0, 2008, 2010, client=_client(handler))
    assert years == ["2008", "2009", "2010"]


def test_year_outside_the_dataset_is_a_gap_not_an_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if _axes(request.url)[0].startswith("(2011"):
            return httpx.Response(404, text=_text("no_matching_results.txt"))
        return _csv("mur_point_2010.csv")

    series, _ = erddap.fetch_point_monthly("jplMURSST41mday", "sst", 36.0, -10.0, 2010, 2011, client=_client(handler))
    assert series.notna().sum() == 3
    assert series.index.max() == pd.Timestamp("2010-03-01")


def test_unknown_dataset_404_is_an_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text='Error {\n    code=404;\n    message="Not Found: Currently unknown datasetID=x";\n}\n')

    with pytest.raises(erddap.ErddapError):
        erddap.fetch_point_monthly("x", "sst", 36.0, -10.0, 2010, 2010, client=_client(handler))


def test_busy_server_is_retried_then_fails():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503, text="Service Unavailable")

    with pytest.raises(erddap.ErddapError):
        erddap.fetch_point_monthly("jplMURSST41mday", "sst", 36.0, -10.0, 2010, 2010, client=_client(handler))
    assert len(calls) == erddap.RETRIES


def test_dhw_comes_from_the_coral_reef_watch_server():
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return _csv("dhw_point_2016.csv")

    series, cell = erddap.fetch_point_yearly_max(
        "noaacrwdhwDaily", "degree_heating_week", -14.6, 145.6, 2016, 2016, client=_client(handler)
    )
    assert urls[0].startswith("https://coastwatch.noaa.gov/erddap/griddap/noaacrwdhwDaily.csv?degree_heating_week%5B")
    time_axis = _axes(urls[0])[0]
    assert time_axis.startswith("(2016-01-01") and "(2016-06-30" in time_axis  # January to June only
    assert list(series.index) == [pd.Timestamp("2016-01-01")]
    assert series.iloc[0] == pytest.approx(7.32)
    assert series.attrs["temporal"] == "annual"
    assert cell == (-14.625, 145.625)


# --------------------------------------------------------------------------- masked coastal cell


def test_masked_cell_falls_back_to_nearest_valid():
    asked = (-19.25, 146.8)  # Townsville coast: masked as land in MUR
    requests: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        axes = _axes(request.url)
        requests.append(axes)
        if len(requests) == 1:
            return _csv("mur_masked_point.csv")
        if len(requests) == 2:
            return _csv("mur_coast_box.csv")
        return _csv("mur_coast_valid_point.csv")

    series, cell = erddap.fetch_point_monthly(
        "jplMURSST41mday", "sst", asked[0], asked[1], 2010, 2010, client=_client(handler)
    )
    lat_axis, lon_axis = requests[1][1], requests[1][2]
    lat_bounds = [float(x.strip("()")) for x in lat_axis.split(":")[::2]]
    lon_bounds = [float(x.strip("()")) for x in lon_axis.split(":")[::2]]
    assert all(abs(b - asked[0]) <= 0.1 + 1e-9 for b in lat_bounds)
    assert all(abs(b - asked[1]) <= 0.1 + 1e-9 for b in lon_bounds)
    assert cell != asked
    assert math.dist(cell, asked) <= 0.1 + 1e-9
    assert series.notna().sum() == 3
    assert series.attrs["cell"] == cell
    # the series itself was asked again at the valid cell
    assert requests[2][1] == f"({cell[0]})" and requests[2][2] == f"({cell[1]})"


def test_no_valid_cell_nearby_keeps_the_empty_series():
    def handler(request: httpx.Request) -> httpx.Response:
        return _csv("mur_masked_point.csv")

    series, cell = erddap.fetch_point_monthly("jplMURSST41mday", "sst", -19.25, 146.8, 2010, 2010, client=_client(handler))
    assert series.notna().sum() == 0
    assert cell == (-19.25, 146.8)


# --------------------------------------------------------------------------- grid


def test_fetch_grid_stacks_years_by_time_lat_lon():
    calls: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(_axes(request.url))
        return _csv("mur_coast_box.csv")

    grid = erddap.fetch_grid(
        "jplMURSST41mday", "sst", (146.7, -19.35, 146.9, -19.15), 2010, 2010, stride=10, client=_client(handler)
    )
    assert grid.dims == ("time", "latitude", "longitude")
    assert grid.shape == (1, 3, 3)
    assert ":10:" in calls[0][1] and ":10:" in calls[0][2]
    assert pd.Timestamp(grid.time.values[0]) == pd.Timestamp("2010-01-01")
    assert np.isnan(grid.sel(latitude=-19.25, longitude=146.8).item())
    assert grid.sel(latitude=-19.15, longitude=146.7).item() == pytest.approx(29.315765)


# --------------------------------------------------------------------------- gather layer


@pytest.fixture
def transport(monkeypatch):
    """Route the gather fetcher's ERDDAP client through a handler set by the test."""
    state: dict = {}

    def new_client() -> httpx.Client:
        return _client(lambda request: state["handler"](request))

    monkeypatch.setattr(erddap, "new_client", new_client)
    return state


def test_erddap_error_page_is_not_available(transport):
    transport["handler"] = lambda request: httpx.Response(200, text=_text("error_page.html"))
    site = point_site(36.0, -10.0, ("ocean",))
    series, missing = gather._run_source("erddap", site, (_var("sst"),), load_catalog(), 2010, 2010)
    assert series == {}
    assert missing == {"sst": gather.SOURCES["erddap"].failure}
    assert "ERDDAP" in gather.SOURCES["erddap"].failure


def test_gather_fetches_sst_at_sea(transport):
    transport["handler"] = lambda request: _csv("mur_point_2010.csv")
    site = point_site(36.0, -10.0, ("ocean",))
    series, missing = gather._run_source("erddap", site, (_var("sst"),), load_catalog(), 2010, 2010)
    assert missing == {}
    assert series["sst"].notna().sum() == 3
    assert series["sst"].iloc[0] == pytest.approx(17.320068)


def test_chlorophyll_is_returned_on_log10(transport):
    transport["handler"] = lambda request: _csv("chl_point_2010.csv")
    site = point_site(37.6, -0.75, ("coast",))
    raw = gather.FETCHERS["erddap"](site, (_var("chlorophyll"),), load_catalog(), 2010, 2010)
    got = raw["chlorophyll"]
    assert got.iloc[0] == pytest.approx(math.log10(0.97567683))
    assert got.attrs["cell"] == (37.604164, -0.770828)


# --------------------------------------------------------------------------- catalog


def test_sea_variables_in_the_catalog():
    by_id = {v.id: v for v in load_catalog()}
    sst, chl, dhw = by_id["sst"], by_id["chlorophyll"], by_id["dhw"]
    assert (sst.source, sst.dataset, sst.band) == ("erddap", "jplMURSST41mday", "sst")
    assert (chl.source, chl.dataset, chl.band) == ("erddap", "erdMH1chlamday_R2022SQ", "chlor_a")
    assert (dhw.source, dhw.dataset, dhw.band) == ("erddap", "noaacrwdhwDaily", "degree_heating_week")
    assert chl.transform == "log10" and chl.units == "log10(mg/m³)"
    assert dhw.temporal == "annual" and dhw.applies_to == ("reef",)  # yearly peaks, on the annual path
    assert "not NASA" in dhw.label
    for var in (sst, chl, dhw):
        assert var.definition and var.units and var.resolution
    for var in (sst, chl):
        assert set(var.applies_to) <= {"ocean", "coast", "reef"} and var.applies_to


# --------------------------------------------------------------------------- fix round 1


def _for_year(name: str, year: int) -> str:
    """A recorded 2010 fixture moved to `year` (the 2011 snapped row to year + 1)."""
    return _text(name).replace("2011-", f"{year + 1}-").replace("2010-", f"{year}-")


def test_cache_hit_makes_no_http_call(tmp_path):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return _csv("mur_point_2010.csv")

    first, _ = erddap.fetch_point_monthly("jplMURSST41mday", "sst", 36.0, -10.0, 2010, 2010, client=_client(handler), cache_dir=tmp_path)
    assert len(calls) == 1 and list(tmp_path.rglob("*.csv"))

    def no_network(request: httpx.Request) -> httpx.Response:
        raise AssertionError("cache hit must not call ERDDAP")

    again, _ = erddap.fetch_point_monthly("jplMURSST41mday", "sst", 36.0, -10.0, 2010, 2010, client=_client(no_network), cache_dir=tmp_path)
    pd.testing.assert_series_equal(first, again)


def test_current_year_is_not_cached(tmp_path, monkeypatch):
    import datetime as dt

    monkeypatch.setattr(erddap, "_today", lambda: dt.date(2010, 6, 1))
    erddap.fetch_point_monthly(
        "jplMURSST41mday", "sst", 36.0, -10.0, 2010, 2010, client=_client(lambda r: _csv("mur_point_2010.csv")), cache_dir=tmp_path
    )
    assert not list(tmp_path.rglob("*.csv"))


def test_failing_middle_year_is_a_gap(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        year = int(_axes(request.url)[0][1:5])
        if year == 2010:
            return httpx.Response(503, text="Service Unavailable")
        return httpx.Response(200, text=_for_year("mur_point_2010.csv", year))

    series, _ = erddap.fetch_point_monthly("jplMURSST41mday", "sst", 36.0, -10.0, 2009, 2011, client=_client(handler), cache_dir=tmp_path)
    assert sorted(set(series.dropna().index.year)) == [2009, 2011]
    assert series.attrs["missing_years"] == [2010]


def test_three_failed_first_years_raise(tmp_path):
    years = []

    def handler(request: httpx.Request) -> httpx.Response:
        years.append(int(_axes(request.url)[0][1:5]))
        return httpx.Response(502, text="Proxy Error")

    with pytest.raises(erddap.ErddapError):
        erddap.fetch_point_monthly("jplMURSST41mday", "sst", 36.0, -10.0, 2008, 2015, client=_client(handler), cache_dir=tmp_path)
    assert sorted(set(years)) == [2008, 2009, 2010]  # stopped early
    assert len(years) == 3 * erddap.RETRIES


def test_two_threads_never_overlap(tmp_path):
    import threading
    import time as _time

    active, peak = [0], [0]
    guard = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        with guard:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        _time.sleep(0.02)
        with guard:
            active[0] -= 1
        return _csv("mur_point_2010.csv")

    def run(lon: float) -> None:  # different points: no shared cache entries
        erddap.fetch_point_monthly("jplMURSST41mday", "sst", 36.0, lon, 2005, 2010, client=_client(handler), cache_dir=tmp_path)

    threads = [threading.Thread(target=run, args=(lon,)) for lon in (-10.0, -11.0)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak[0] == 1


def test_partial_last_year_is_clamped_to_the_time_axis(tmp_path, monkeypatch):
    import datetime as dt

    monkeypatch.setattr(erddap, "_today", lambda: dt.date(2026, 11, 15))
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(_axes(request.url)[0])
        if len(asked) == 1:
            return httpx.Response(404, text=_text("axis_maximum_404.txt"))
        return httpx.Response(200, text=_for_year("chl_point_2010.csv", 2026))

    series, _ = erddap.fetch_point_monthly(
        "erdMH1chlamday_R2022SQ", "chlor_a", 37.6, -0.75, 2026, 2026, client=_client(handler), cache_dir=tmp_path
    )
    assert asked[1] == "(2026-01-01T00:00:00Z):1:(2026-04-16T00:00:00Z)"
    assert series.notna().sum() == 4
    assert not list(tmp_path.rglob("*.csv"))  # current year: not cached


def test_requery_at_moved_cell_with_no_rows_is_skipped(tmp_path):
    masked = (
        "time,latitude,longitude,degree_heating_week\nUTC,degrees_north,degrees_east,degree_Celsius_weeks\n"
        "2010-01-16T12:00:00Z,-19.25,146.8,NaN\n"
    )
    box = _text("mur_coast_box.csv").replace("sst", "degree_heating_week")
    responses = iter(
        [
            httpx.Response(200, text=masked),  # the asked cell: masked
            httpx.Response(200, text=box),  # the probe finds a valid neighbour
            httpx.Response(404, text=_text("no_matching_results.txt")),  # ...which has no rows
        ]
    )
    series, cell = erddap.fetch_point_yearly_max(
        "noaacrwdhwDaily", "degree_heating_week", -19.25, 146.8, 2010, 2010,
        client=_client(lambda r: next(responses)), cache_dir=tmp_path,
    )
    assert series.empty  # no IndexError on an empty frame
    assert cell != (-19.25, 146.8)


def test_box_corners_beyond_the_offset_are_never_picked(tmp_path):
    asked = (-19.25, 146.8)
    # only valid cells are the box corners at ~0.14 degrees: farther than the 0.1 limit
    box = (
        "time,latitude,longitude,sst\nUTC,degrees_north,degrees_east,degree_C\n"
        "2010-01-16T00:00:00Z,-19.35,146.7,29.1\n"
        "2010-01-16T00:00:00Z,-19.35,146.8,NaN\n"
        "2010-01-16T00:00:00Z,-19.25,146.8,NaN\n"
        "2010-01-16T00:00:00Z,-19.15,146.9,29.2\n"
    )
    responses = iter([_csv("mur_masked_point.csv"), httpx.Response(200, text=box)])
    series, cell = erddap.fetch_point_monthly(
        "jplMURSST41mday", "sst", *asked, 2010, 2010, client=_client(lambda r: next(responses)), cache_dir=tmp_path
    )
    assert cell == asked
    assert series.notna().sum() == 0


def test_chlorophyll_zero_or_nan_becomes_nan_without_warning(transport):
    import warnings

    transport["handler"] = lambda request: _csv("chl_point_zero_nan.csv")
    site = point_site(37.6, -0.75, ("coast",))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        got = gather.FETCHERS["erddap"](site, (_var("chlorophyll"),), load_catalog(), 2010, 2010)["chlorophyll"]
    assert np.isnan(got.loc["2010-02-01"]) and np.isnan(got.loc["2010-03-01"])
    assert got.loc["2010-04-01"] == pytest.approx(math.log10(0.6155786))


# --------------------------------------------------------------------------- cache hardening


def test_clamped_past_year_is_never_cached(tmp_path, monkeypatch):
    import datetime as dt

    monkeypatch.setattr(erddap, "_today", lambda: dt.date(2030, 1, 1))
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(_axes(request.url)[0])
        if len(asked) == 1:
            return httpx.Response(404, text=_text("axis_maximum_404.txt"))
        return httpx.Response(200, text=_for_year("chl_point_2010.csv", 2026))

    erddap.fetch_point_monthly(
        "erdMH1chlamday_R2022SQ", "chlor_a", 37.6, -0.75, 2026, 2026, client=_client(handler), cache_dir=tmp_path
    )
    assert len(asked) == 2  # it was clamped
    assert not list(tmp_path.rglob("*.csv"))


def test_cache_is_written_atomically(tmp_path, monkeypatch):
    replaced: list[tuple[str, str]] = []
    real = erddap.os.replace

    def spy(src, dst):
        replaced.append((str(src), str(dst)))
        return real(src, dst)

    monkeypatch.setattr(erddap.os, "replace", spy)
    erddap.fetch_point_monthly(
        "jplMURSST41mday", "sst", 36.0, -10.0, 2010, 2010, client=_client(lambda r: _csv("mur_point_2010.csv")), cache_dir=tmp_path
    )
    assert len(replaced) == 1
    src, dst = replaced[0]
    assert Path(src).parent == Path(dst).parent and src != dst and dst.endswith(".csv")
    assert [p.name for p in tmp_path.rglob("*") if p.is_file()] == [Path(dst).name]  # no temp file left


def test_corrupt_cache_file_is_deleted_and_fetched_again(tmp_path):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return _csv("mur_point_2010.csv")

    first, _ = erddap.fetch_point_monthly("jplMURSST41mday", "sst", 36.0, -10.0, 2010, 2010, client=_client(handler), cache_dir=tmp_path)
    (cached,) = list(tmp_path.rglob("*.csv"))
    cached.write_text("<html>half-written", encoding="utf-8")
    again, _ = erddap.fetch_point_monthly("jplMURSST41mday", "sst", 36.0, -10.0, 2010, 2010, client=_client(handler), cache_dir=tmp_path)
    assert len(calls) == 2
    pd.testing.assert_series_equal(first, again)
    assert "half-written" not in cached.read_text(encoding="utf-8")  # healed


def test_min_elevation_is_the_lowest_cell_and_is_cached(tmp_path):
    csv = "latitude,longitude,elevation\ndegrees_north,degrees_east,m\n36.0,-10.0,-250.0\n36.1,-10.0,-4.0\n36.0,-9.9,12.0\n"
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, text=csv)

    low = erddap.fetch_min_elevation((-10.1, 35.9, -9.9, 36.1), client=_client(handler), cache_dir=tmp_path)
    assert low == -250.0 and "GEBCO_2020.csv?elevation%5B" in calls[0]
    again = erddap.fetch_min_elevation((-10.1, 35.9, -9.9, 36.1), client=_client(lambda r: 1 / 0), cache_dir=tmp_path)
    assert again == -250.0 and len(calls) == 1


def test_min_elevation_error_page_raises(tmp_path):
    with pytest.raises(erddap.ErddapError):
        erddap.fetch_min_elevation((0, 0, 1, 1), client=_client(lambda r: httpx.Response(200, text="<html>x")), cache_dir=tmp_path)


def test_min_elevation_scales_the_stride_on_a_big_box(tmp_path):
    """GEBCO is 1/240 degree: past 2 degrees a side the stride grows so a request stays <= ~200 x 200."""
    csv = "latitude,longitude,elevation\ndegrees_north,degrees_east,m\n36.0,-10.0,-250.0\n"
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, text=csv)

    erddap.fetch_min_elevation((-10.0, 35.0, -5.0, 40.0), client=_client(handler), cache_dir=tmp_path)
    erddap.fetch_min_elevation((-10.1, 35.9, -9.9, 36.1), client=_client(handler), cache_dir=tmp_path)
    big, small = (_axes(u) for u in calls)
    assert big[0].split(":")[1] == "6" and big[1].split(":")[1] == "6"  # 5 deg * 240 / 200
    assert small[0].split(":")[1] == "4"  # the default for a small box
    lo, step, hi = big[0].split(":")
    assert (float(hi.strip("()")) - float(lo.strip("()"))) * 240 / int(step) <= 200
