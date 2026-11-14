"""Layer suggestions: closed set of ids, cleaned answer, keyword fallback, API."""

import json

import pytest
from fastapi.testclient import TestClient

from app.explain.llm import AnthropicLLM
from app.explain.router import get_llm, get_sites_dir
from app.layer_suggest import clean_stack, suggest_layers
from app.main import app
from tests.explain_fakes import fake_client, json_text

DOC = {
    "layers": [
        {"id": "base_hq", "title": "Cloud-free picture", "status": "visual_only"},
        {"id": "detail", "title": "Close-up", "status": "visual_only"},
        {"id": "ndvi_gibs", "title": "Green vegetation (NDVI)", "status": "observed"},
        {"id": "year_lst_day", "title": "Daytime ground temperature: year by year", "status": "analysed"},
        {"id": "hillshade", "title": "Relief shading", "status": "visual_only"},
    ],
    "timeline": {"years": [2003, 2004, 2024]},
}
LAYERS = {la["id"]: la for la in DOC["layers"]}


def test_clean_drops_unknown_ids_caps_and_adds_base_last():
    raw = {"stack": [{"id": "evil"}, {"id": "ndvi_gibs", "opacity": 7, "why": "Green?"},
                     {"id": "ndvi_gibs"}, {"id": "hillshade", "opacity": 0.1, "why": "It is 3 m"}],
           "year": 1999, "caption": "Look at 2003"}
    stack, year, caption = clean_stack(raw, LAYERS, [2003, 2024], "overview")
    assert [s["id"] for s in stack] == ["ndvi_gibs", "hillshade", "base_hq"]
    assert stack[0]["opacity"] == 1.0 and stack[1]["opacity"] == 0.3
    assert not any(ch.isdigit() for s in stack for ch in s["why"])
    assert year is None
    assert not any(ch.isdigit() for ch in caption)


def test_drone_mode_uses_detail_as_base():
    stack, _, _ = clean_stack({"stack": [{"id": "year_lst_day"}]}, LAYERS, [], "drone")
    assert stack[-1]["id"] == "detail"


def test_keywords_without_llm():
    s = suggest_layers("Is it getting hotter?", DOC, "overview", None)
    assert s.source == "default"
    assert s.stack[0]["id"] == "year_lst_day"
    s = suggest_layers("Is it greener?", DOC, "overview", None)
    assert s.stack[0]["id"] == "ndvi_gibs"


def test_llm_answer_used_and_year_kept():
    raw = {"stack": [{"id": "ndvi_gibs", "opacity": 0.7, "why": "Shows plants."}], "year": 2024, "caption": "Look."}
    s = suggest_layers("q", DOC, "overview", AnthropicLLM(fake_client(json_text(raw))))
    assert s.source == "llm" and s.year == 2024
    assert [x["id"] for x in s.stack] == ["ndvi_gibs", "base_hq"]


def test_llm_answer_with_only_base_falls_back():
    raw = {"stack": [{"id": "base_hq", "opacity": 1, "why": "x"}], "year": None, "caption": "x"}
    s = suggest_layers("hot?", DOC, "overview", AnthropicLLM(fake_client(json_text(raw))))
    assert s.source == "default"


@pytest.fixture
def client(tmp_path):
    (tmp_path / "lake_mead").mkdir()
    (tmp_path / "lake_mead" / "layers.json").write_text(json.dumps(DOC))
    app.dependency_overrides[get_llm] = lambda: None
    app.dependency_overrides[get_sites_dir] = lambda: tmp_path
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_api(client):
    r = client.post("/layers/suggest", json={"site_id": "lake_mead", "question": "hot?", "mode": "drone"})
    assert r.status_code == 200
    assert r.json()["stack"][-1]["id"] == "detail"
    assert client.post("/layers/suggest", json={"site_id": "nope", "question": "q"}).status_code == 404
    assert client.post("/layers/suggest", json={"site_id": "lake_mead", "question": "q", "mode": "x"}).status_code == 422
