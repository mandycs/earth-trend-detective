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
    assert dhw.temporal == "annual" and dhw.applies_to == ()  # not offered until the annual path
    assert "not NASA" in dhw.label
    for var in (sst, chl, dhw):
        assert var.definition and var.units and var.resolution
    for var in (sst, chl):
        assert set(var.applies_to) <= {"ocean", "coast", "reef"} and var.applies_to
