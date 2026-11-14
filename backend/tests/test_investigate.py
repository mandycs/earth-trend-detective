"""Investigator: closed-menu plans, land cover parsing, runner events, SSE endpoint."""

from __future__ import annotations

import json
from functools import partial

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.explain.llm import AnthropicLLM
from app.explain.router import get_llm
from app.gather import GatherResult
from app.investigate import landcover, runner, thennow
from app.investigate.landcover import LandCover, class_shares, share_changes, tags_for
from app.investigate.menu import FINAL_STEP, MAX_STEPS, clean_plan, default_plan
from app.investigate.planner import make_plan
from app.investigate.router import get_investigate
from app.main import app
from tests.explain_fakes import fake_client, json_text

# --------------------------------------------------------------------------- menu


def _ids(plan) -> list[str]:
    return [s.id for s in plan]


def test_clean_plan_keeps_menu_ids_and_appends_explain():
    plan = clean_plan([{"id": "then_and_now", "why": "See the shore move."}, {"id": "land_cover", "why": "x"}], ())
    assert _ids(plan) == ["then_and_now", "land_cover", FINAL_STEP]
    assert plan[0].why == "See the shore move."


def test_clean_plan_drops_unknown_and_duplicate_ids():
    raw = [{"id": "rm -rf", "why": ""}, {"id": "climate"}, {"id": "climate"}, {"id": "then_and_now"}]
    assert _ids(clean_plan(raw, ())) == ["climate", "then_and_now", FINAL_STEP]


def test_clean_plan_puts_dependencies_first():
    plan = clean_plan([{"id": "water_storage", "why": "a"}, {"id": "then_and_now", "why": "b"}], ())
    assert _ids(plan) == ["climate", "water_storage", "then_and_now", FINAL_STEP]


def test_clean_plan_reason_with_figures_is_replaced():
    plan = clean_plan([{"id": "climate", "why": "It warmed 2 °C"}, {"id": "land_cover", "why": "ok"}], ())
    assert not any(ch.isdigit() for ch in plan[0].why)
    assert plan[0].why == plan[0].step.does


def test_clean_plan_too_short_uses_default_for_place():
    assert _ids(clean_plan([{"id": "climate"}], ("water_body",)))[:-1] == list(default_plan(("water_body",)))
    assert _ids(clean_plan("nonsense", ()))[-1] == FINAL_STEP


def test_clean_plan_caps_length():
    raw = [{"id": i} for i in ("land_cover", "climate", "water_storage", "then_and_now", "soil_and_runoff")]
    assert len(clean_plan(raw, ())) <= MAX_STEPS + 1


# --------------------------------------------------------------------------- planner


def test_planner_without_llm_uses_default():
    plan = make_plan("Is the lake drying?", "Lake", ("water_body",), None)
    assert plan.source == "default"
    assert _ids(plan.steps)[-1] == FINAL_STEP


def test_planner_uses_llm_plan():
    raw = {"steps": [{"id": "then_and_now", "why": "Look at the shore."}, {"id": "climate", "why": "Rain?"}]}
    plan = make_plan("q", "p", (), AnthropicLLM(fake_client(json_text(raw))))
    assert plan.source == "llm"
    assert _ids(plan.steps) == ["then_and_now", "climate", FINAL_STEP]


def test_planner_bad_llm_answer_falls_back():
    plan = make_plan("q", "p", ("urban",), AnthropicLLM(fake_client(json_text({"steps": [{"id": "nope"}]}))))
    assert plan.source == "default"


# --------------------------------------------------------------------------- land cover


def test_class_shares_and_tags():
    rgba = np.zeros((2, 2, 4), dtype=np.uint8)
    rgba[0, 0] = (134, 202, 227, 255)  # water
    rgba[0, 1] = (134, 202, 227, 255)
    rgba[1, 0] = (191, 191, 189, 255)  # barren
    rgba[1, 1] = (0, 0, 0, 0)  # no data
    shares = class_shares(rgba)
    assert shares == {"Water": pytest.approx(0.667, abs=1e-3), "Barren": pytest.approx(0.333, abs=1e-3)}
    assert tags_for(shares) == ("water_body", "desert")


def test_share_changes_sorted_by_size():
    before = LandCover(2003, {"Water": 0.5, "Barren": 0.5})
    after = LandCover(2023, {"Water": 0.2, "Barren": 0.79, "Urban and built-up land": 0.01})
    changes = share_changes(before, after)
    assert [c["class"] for c in changes] == ["Water", "Barren"]
    assert changes[0]["change"] == pytest.approx(-0.3)


# --------------------------------------------------------------------------- runner


def _fake_gather(site, variables, start, end):
    idx = pd.date_range(f"{start}-01-01", f"{end}-12-01", freq="MS")
    rng = np.random.default_rng(0)
    series = {
        v.id: pd.Series(np.arange(len(idx)) * 0.01 + rng.normal(0, 0.1, len(idx)), index=idx, name=v.id)
        for v in variables
        if v.source in {"power", "grace"} and "any" in v.applies_to
    }
    return GatherResult(series=series, missing={}, sources=tuple(sorted({v.source for v in variables})))


def _fake_land(lat, lon):
    return {"tags": ["water_body", "desert"], "before": {}, "after": {}, "changes": [], "status": "analysed"}


def _events(**kw):
    return list(runner.investigate("Is the lake drying?", gather=_fake_gather, land_cover_fn=_fake_land, **kw))


@pytest.fixture
def no_pictures(monkeypatch):
    monkeypatch.setattr(thennow, "then_and_now", lambda *a, **k: {"status": "visual_only", "before": None})


def test_runner_point_streams_place_plan_steps_done(no_pictures):
    events = _events(lat=36.2, lon=-114.5)
    names = [e["event"] for e in events]
    assert names[0] == "place" and names[1] == "plan" and names[-1] == "done"
    assert events[0]["data"]["tags"] == ["water_body", "desert"]
    plan_ids = [s["id"] for s in events[1]["data"]["steps"]]
    done = {e["data"]["id"]: e["data"]["result"] for e in events if e["event"] == "step_done"}
    assert set(done) == set(plan_ids)
    assert {v["id"] for v in done["climate"]["variables"]} >= {"t2m", "precip"}
    assert [v["id"] for v in done["water_storage"]["variables"]] == ["grace_tws"]
    assert done[FINAL_STEP]["source"] == "template"
    json.dumps([e["data"] for e in events], allow_nan=False)  # SSE-safe


def test_runner_failing_step_does_not_stop(no_pictures):
    def broken(site, variables, start, end):
        raise RuntimeError("down")

    events = list(runner.investigate("q", lat=1.0, lon=2.0, gather=broken, land_cover_fn=_fake_land))
    failed = [e["data"]["id"] for e in events if e["event"] == "step_failed"]
    assert "climate" in failed
    assert events[-1]["event"] == "done"


def test_runner_land_cover_failure_still_plans(no_pictures):
    def boom(lat, lon):
        raise RuntimeError("gibs down")

    events = list(runner.investigate("q", lat=1.0, lon=2.0, gather=_fake_gather, land_cover_fn=boom))
    assert events[0]["data"]["tags"] == []
    assert events[1]["event"] == "plan"


def test_runner_known_site_uses_site_tags(no_pictures):
    events = _events(site_id="aletsch")
    assert events[0]["data"]["id"] == "aletsch"
    assert "glacier" in events[0]["data"]["tags"]


# --------------------------------------------------------------------------- API


@pytest.fixture
def client(monkeypatch, no_pictures):
    app.dependency_overrides[get_llm] = lambda: None
    app.dependency_overrides[get_investigate] = lambda: partial(
        runner.investigate, gather=_fake_gather, land_cover_fn=_fake_land
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_api_streams_events(client):
    r = client.post("/investigate", json={"question": "Is it drying?", "lat": 36.2, "lon": -114.5})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(r.text)
    assert events[0][0] == "place" and events[-1][0] == "done"


@pytest.mark.parametrize(
    "body",
    [
        {"question": "q"},
        {"question": "q", "lat": 1.0},
        {"question": "q", "site_id": "aletsch", "lat": 1.0, "lon": 2.0},
        {"question": "", "lat": 1.0, "lon": 2.0},
        {"question": "q", "lat": 91.0, "lon": 2.0},
    ],
)
def test_api_rejects_bad_body(client, body):
    assert client.post("/investigate", json=body).status_code == 422


def test_api_unknown_site_404(client):
    assert client.post("/investigate", json={"question": "q", "site_id": "atlantis"}).status_code == 404


def test_landcover_module_has_all_igbp_colours():
    assert len(landcover.CLASSES) == 17
