import pytest
from fastapi.testclient import TestClient

from app.explain.llm import AnthropicLLM
from app.explain.router import get_llm
from app.main import app
from tests.explain_fakes import fake_client, json_text, lake_mead_report
from tests.test_explain_validator import GOOD


@pytest.fixture
def client():
    app.dependency_overrides[get_llm] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def use_llm(*texts: str) -> None:
    app.dependency_overrides[get_llm] = lambda: AnthropicLLM(fake_client(*texts))


def test_narrative_by_site_id_template_mode(client):
    r = client.post("/explain/narrative", json={"site_id": "lake_mead"})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "template"
    assert body["validation"]["ok"] is True
    assert body["validation"]["rejected"] == []
    assert "−6.5" in body["validation"]["checked_numbers"]
    assert "a lead, not proof" in body["text"]


def test_narrative_with_report_body_and_llm(client):
    use_llm(GOOD)
    r = client.post("/explain/narrative", json={"report": lake_mead_report()})
    assert r.status_code == 200
    assert r.json()["source"] == "llm"
    assert r.json()["text"] == GOOD


def test_narrative_needs_exactly_one_input(client):
    assert client.post("/explain/narrative", json={}).status_code == 422
    both = {"site_id": "lake_mead", "report": lake_mead_report()}
    assert client.post("/explain/narrative", json=both).status_code == 422
    assert client.post("/explain/narrative", json={"report": {"x": 1}}).status_code == 422


def test_narrative_unknown_site_is_404(client):
    r = client.post("/explain/narrative", json={"site_id": "../../etc"})
    assert r.status_code == 404
    assert "lake_mead" in r.json()["detail"]


def test_route_template_mode(client):
    r = client.post("/explain/route", json={"question": "Is the lake drying up?", "site_id": "lake_mead"})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "template"
    assert "grace_tws" in body["ids"]
    assert set(body["ids"]) <= set(body["allowed_ids"])


def test_route_llm_enum_restricted_to_site(client):
    use_llm(json_text({"ids": ["grace_tws", "snow_cover"]}))
    r = client.post("/explain/route", json={"question": "Is the lake drying up?", "site_id": "lake_mead"})
    body = r.json()
    assert body["source"] == "llm"
    assert "snow_cover" not in body["allowed_ids"]
    assert body["ids"] == ["grace_tws"]


def test_route_rejects_empty_question(client):
    assert client.post("/explain/route", json={"question": ""}).status_code == 422
