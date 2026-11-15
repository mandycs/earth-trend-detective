"""The reef ("Ask Alibi" from its story: /detective?site=great_barrier_reef) through the whole detective, offline.

A sea case (pipeline: sea) must not reach a land-only source and must not crash: the land tools answer
"not available", the sea variables run.
"""

import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from app import gather
from app.catalog import load_catalog
from app.detective import router as detective_router
from app.detective.events import DetectiveRequest, place_for
from app.detective.ledger import Ledger
from app.detective.session import Session
from app.detective.tools import data as tools
from app.extractors import erddap
from app.investigate import landcover
from app.investigate.landcover import LandCover
from app.main import app

REEF = "great_barrier_reef"
LAND_ONLY = ("lst_day", "soil_moisture", "runoff", "ndvi", "et", "snow_cover")


class FakeModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kw):
        return self


def _call(name, args, cid):
    return AIMessage(content="Checking.", tool_calls=[{"name": name, "args": args, "id": cid}])


@pytest.fixture
def sea_offline(monkeypatch):
    touched = []

    def land_fetcher(name):
        def boom(*a, **kw):
            touched.append(name)
            raise AssertionError(f"a land source was fetched at sea: {name}")

        return boom

    def fake_power(site, variables, catalog, start, end):
        idx = pd.date_range(f"{start}-01-01", f"{end}-12-01", freq="MS")
        return {v.id: pd.Series(26 + np.sin(2 * np.pi * idx.month / 12), index=idx) for v in variables}

    fetchers = {k: land_fetcher(k) for k in ("grace", "gldas", "appeears", "appeears_water", "gibs")}
    monkeypatch.setattr(gather, "FETCHERS", {**gather.FETCHERS, **fetchers, "power": fake_power})

    def fake_sst(dataset, variable, lat, lon, start, end, client=None):
        idx = pd.date_range(f"{start}-01-01", f"{end}-12-01", freq="MS")
        t = np.arange(idx.size) / 12.0
        s = pd.Series(26 + 2 * np.sin(2 * np.pi * idx.month / 12) + 0.03 * t, index=idx)
        return s, (lat, lon)

    monkeypatch.setattr(erddap, "fetch_point_monthly", fake_sst)
    monkeypatch.setattr(erddap, "fetch_min_elevation", land_fetcher("gebco"))
    sea = LandCover(year=2023, shares={"Water": 1.0})
    monkeypatch.setattr(landcover, "fetch_land_cover", lambda lat, lon, year, client=None: sea)
    return touched


def test_the_reef_is_open_sea_for_the_detective():
    place = place_for(DetectiveRequest(question="q", site_id=REEF))
    s = Session(ledger=Ledger(), place=place, catalog=load_catalog(), series={})
    rows = {r["id"]: r for r in tools.list_variables(s)["variables"]}
    for land_only in LAND_ONLY:
        assert land_only not in rows
    assert rows["grace_tws"]["available"] is False
    assert rows["sst"]["available"] and rows["t2m"]["available"]


def test_a_land_case_is_not_open_sea():
    place = place_for(DetectiveRequest(question="q", site_id="lake_mead"))
    s = Session(ledger=Ledger(), place=place, catalog=load_catalog(), series={})
    assert tools._open_sea(s) is False


def test_ask_alibi_on_the_reef_runs_without_land_tools(sea_offline):
    messages = [
        _call("profile_place", {}, "p1"),
        _call("list_variables", {}, "l1"),
        _call("get_series", {"var_id": "soil_moisture"}, "g1"),
        _call("get_series", {"var_id": "grace_tws"}, "g2"),
        _call("water_extent", {}, "w1"),
        _call("get_series", {"var_id": "sst"}, "g3"),
        _call("trend_test", {"series_id": "sst:2003-2024"}, "t1"),
        AIMessage(content="I have what I need."),
        AIMessage(content="Sea surface temperature here went up from 2003 to 2024."),
    ]
    app.dependency_overrides[detective_router.get_detective_model] = lambda: FakeModel(messages=iter(messages))
    app.dependency_overrides[detective_router.get_persistence] = lambda: (MemorySaver(), InMemoryStore())
    try:
        r = TestClient(app).post("/detective", json={"question": "Is the sea getting warmer here?", "site_id": REEF})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    events = []
    for block in r.text.split("\n\n"):
        if block.strip():
            lines = dict(line.split(": ", 1) for line in block.splitlines())
            events.append((lines["event"], json.loads(lines["data"])))
    kinds = [k for k, _ in events]
    assert "error" not in kinds and kinds[-1] == "done"
    assert sea_offline == []
    done = {d["id"]: d for k, d in events if k in ("tool_done", "tool_failed") and d.get("id")}
    assert done["g1"]["result"]["status"] == "not_available"
    assert done["g2"]["result"]["status"] == "not_available"
    assert done["w1"]["result"]["status"] == "not_available"
    assert done["g3"]["result"]["status"] == "ok"
    assert done["t1"]["result"].get("test_id")
