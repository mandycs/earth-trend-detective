"""AppEEARS extractor: request building, stats-CSV parsing, task resume. No network."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import pytest
import respx

from app.catalog import load_catalog
from app.extractors import appeears as ae

FIXTURE = Path(__file__).parent / "fixtures" / "appeears_stats_lst_snow.csv"
API = ae.API_URL


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture
def sites():
    return {s.id: s for s in ae.load_sites()}


def _vars(catalog, *ids):
    by_id = {v.id: v for v in catalog}
    return [by_id[i] for i in ids]


def test_site_layers_follow_tags(catalog, sites):
    bands = {sid: [v.band for v in ae.appeears_variables(catalog, s)] for sid, s in sites.items()}
    assert bands["lake_mead"] == ["LST_Day_1km"]
    assert set(bands["aletsch"]) == {"LST_Day_1km", "NDSI_Snow_Cover"}
    assert set(bands["donana"]) == {"_1_km_monthly_NDVI", "LST_Day_1km", "ET_500m"}


def test_build_area_request(catalog, sites):
    site = sites["donana"]
    req = ae.build_area_request(site, ae.appeears_variables(catalog, site))
    assert req["task_type"] == "area"
    params = req["params"]
    assert params["dates"] == [{"startDate": "01-01-2003", "endDate": "12-31-2024"}]
    assert {"product": "MOD13A3.061", "layer": "_1_km_monthly_NDVI"} in params["layers"]
    assert params["output"] == {"format": {"type": "netcdf4"}, "projection": "geographic"}
    ring = params["geo"]["features"][0]["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1] == [-6.6, 36.8]
    assert [-6.2, 37.15] in ring


def test_build_area_request_without_layers_fails(sites):
    with pytest.raises(ValueError):
        ae.build_area_request(sites["lake_mead"], [])


def test_year_chunks():
    assert ae.year_chunks(2003, 2024, 4) == [(2003, 2008), (2009, 2014), (2015, 2020), (2021, 2024)]
    assert ae.year_chunks(2003, 2004, 5) == [(2003, 2003), (2004, 2004)]
    assert ae.year_chunks(2003, 2024, 1) == [(2003, 2024)]


def test_parse_stats_csv_monthly_units(catalog):
    series = ae.parse_stats_csv(FIXTURE, _vars(catalog, "lst_day", "snow_cover"))
    lst = series["lst_day"]
    assert isinstance(lst.index, pd.DatetimeIndex)
    assert list(lst.index) == list(pd.date_range("2003-01-01", "2003-03-01", freq="MS"))
    # Stats are already scaled (Kelvin): only the catalog offset applies, not scale 0.02.
    assert lst["2003-01-01"] == pytest.approx(1.0)
    assert np.isnan(lst["2003-02-01"])  # Count 0 -> missing
    assert lst["2003-03-01"] == pytest.approx(10.0)
    # Snow mean 240 (cloud flag contamination) is dropped; January = mean(80, 60).
    assert series["snow_cover"]["2003-01-01"] == pytest.approx(70.0)


def test_parse_bundle_merges_chunks(tmp_path, catalog):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    shutil.copy(FIXTURE, tmp_path / "a" / "etd_x_2003-MOD11A2-061-Statistics.csv")
    later = FIXTURE.read_text(encoding="utf-8").replace("2003-", "2005-")
    (tmp_path / "b" / "etd_x_2005-MOD11A2-061-Statistics.csv").write_text(later, encoding="utf-8")
    lst = ae.parse_bundle(tmp_path, _vars(catalog, "lst_day"))["lst_day"]
    assert lst.index[0] == pd.Timestamp("2003-01-01")
    assert lst.index[-1] == pd.Timestamp("2005-03-01")
    assert len(lst) == 27  # contiguous monthly index, gaps are NaN
    assert np.isnan(lst["2004-06-01"])


def test_tasks_roundtrip(tmp_path):
    rec = ae.TaskRecord("aletsch@2003-2008", "aletsch", "t1", "2026-11-14T00:00:00+00:00")
    ae.save_tasks({rec.key: rec}, tmp_path)
    assert ae.load_tasks(tmp_path) == {rec.key: rec}


@respx.mock
def test_submit_splits_when_too_large(catalog, sites):
    too_large = {"message": "The total number of files this request will generate exceeds "
                 "the maximum size allowed by 50.0%. Please reduce the request and resubmit."}
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        if body["params"]["dates"][0]["startDate"] == "01-01-2003" and \
                body["params"]["dates"][0]["endDate"] == "12-31-2024":
            return httpx.Response(400, json=too_large)
        return httpx.Response(200, json={"task_id": f"id{len(calls)}", "status": "pending"})

    respx.post(f"{API}/task").mock(side_effect=handler)
    site = sites["aletsch"]
    with ae.make_client("fake") as client:
        records = ae.submit_site(client, site, ae.appeears_variables(catalog, site))
    # ceil(1.5 * 1.25) = 2 chunks
    assert [r.key for r in records] == ["aletsch@2003-2013", "aletsch@2014-2024"]
    assert calls[0]["task_name"] == "etd_aletsch"
    assert calls[1]["task_name"] == "etd_aletsch_2003_2013"


@respx.mock
def test_cmd_submit_resumes(tmp_path, monkeypatch, sites):
    existing = ae.TaskRecord("lake_mead", "lake_mead", "old", "2026-11-14T00:00:00+00:00")
    ae.save_tasks({"lake_mead": existing}, tmp_path)
    route = respx.post(f"{API}/task").mock(
        return_value=httpx.Response(200, json={"task_id": "new", "status": "pending"})
    )
    with ae.make_client("fake") as client:
        ae.cmd_submit(client, [sites["lake_mead"], sites["donana"]], tmp_path)
    assert route.call_count == 1
    tasks = ae.load_tasks(tmp_path)
    assert tasks["lake_mead"].task_id == "old"
    assert tasks["donana"].task_id == "new"


@respx.mock
def test_download_bundle(tmp_path):
    respx.get(f"{API}/bundle/t1").mock(return_value=httpx.Response(200, json={"files": [
        {"file_id": "f1", "file_name": "etd-MOD11A2-061-Statistics.csv", "file_size": 3},
        {"file_id": "f2", "file_name": "MOD11A2.061_1km_aid0001.nc", "file_size": 4},
    ]}))
    respx.get(f"{API}/bundle/t1/f1").mock(return_value=httpx.Response(200, content=b"a,b"))
    nc = respx.get(f"{API}/bundle/t1/f2").mock(return_value=httpx.Response(200, content=b"data"))
    with ae.make_client("fake") as client:
        paths = ae.download_bundle(client, "t1", tmp_path, only_csv=True)
        assert [p.name for p in paths] == ["etd-MOD11A2-061-Statistics.csv"]
        assert not nc.called
        ae.download_bundle(client, "t1", tmp_path)  # csv cached, nc fetched
    assert (tmp_path / "MOD11A2.061_1km_aid0001.nc").read_bytes() == b"data"


def test_load_token_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(ae, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("APPEEARS_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        ae.load_token()
