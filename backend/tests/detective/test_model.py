from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from app.detective.model import make_chat_model


def test_no_key_gives_none():
    assert make_chat_model() is None


def test_anthropic_key_gives_anthropic(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "x")
    m = make_chat_model()
    assert isinstance(m, ChatAnthropic)
    assert m.model == "claude-sonnet-5-5"


def test_openrouter_key_file(monkeypatch, tmp_path):
    f = tmp_path / "key"
    f.write_text("x")
    monkeypatch.setenv("OPENROUTER_KEY_FILE", str(f))
    m = make_chat_model()
    assert isinstance(m, ChatOpenAI)
    assert m.openai_api_base.endswith("/api/v1")
    assert m.model_name == "anthropic/claude-sonnet-5.5"


def test_model_override(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "x")
    monkeypatch.setenv("DETECTIVE_MODEL", "claude-other")
    assert make_chat_model().model == "claude-other"
