import json

import httpx
import respx

from app.explain import llm as llm_mod
from app.explain.openrouter import OPENROUTER_URL, OpenRouterLLM, get_openrouter_key


def ok(content: str, finish: str = "stop") -> httpx.Response:
    return httpx.Response(200, json={"model": "m", "choices": [{"finish_reason": finish, "message": {"content": content}}]})


@respx.mock
def test_json_sends_schema_and_parses():
    route = respx.post(OPENROUTER_URL).mock(return_value=ok('{"ids": ["grace_tws"]}'))
    llm = OpenRouterLLM(httpx.Client())
    assert llm.json("sys", "user", {"type": "object"}) == {"ids": ["grace_tws"]}
    body = json.loads(route.calls[0].request.content)
    assert body["response_format"]["type"] == "json_schema"
    assert body["messages"][0]["role"] == "system"


@respx.mock
def test_errors_and_truncation_return_none():
    llm = OpenRouterLLM(httpx.Client())
    respx.post(OPENROUTER_URL).mock(return_value=httpx.Response(401, json={"error": "bad key"}))
    assert llm.text("s", "u") is None
    respx.post(OPENROUTER_URL).mock(return_value=ok("partial", finish="length"))
    assert llm.text("s", "u") is None
    respx.post(OPENROUTER_URL).mock(return_value=ok("not json"))
    assert llm.json("s", "u", {}) is None


def test_key_from_env_or_file(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    keyfile = tmp_path / "openkey"
    keyfile.write_text("sk-or-test\n")
    monkeypatch.setenv("OPENROUTER_KEY_FILE", str(keyfile))
    assert get_openrouter_key() == "sk-or-test"
    monkeypatch.setenv("OPENROUTER_KEY_FILE", str(tmp_path / "missing"))
    assert get_openrouter_key() is None


def test_make_llm_prefers_anthropic_then_openrouter_then_none(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_mod, "get_api_key", lambda: None)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_KEY_FILE", str(tmp_path / "missing"))
    assert llm_mod.make_llm() is None
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-x")
    assert isinstance(llm_mod.make_llm(), OpenRouterLLM)
