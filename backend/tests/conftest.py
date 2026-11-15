"""Test-wide safety: no test may pick up a real LLM key from the machine."""

import pytest


@pytest.fixture(autouse=True)
def _no_real_llm_keys(monkeypatch, tmp_path_factory):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_KEY_FILE", str(tmp_path_factory.mktemp("nokey") / "missing"))
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr("app.explain.llm.REPO_ENV", tmp_path_factory.mktemp("noenv") / ".env")
    # never the real detective database (backend/data/detective/); tests that need one set their own
    monkeypatch.setenv("DETECTIVE_DB", str(tmp_path_factory.mktemp("detective-db") / "detective.sqlite"))
    # never the real ERDDAP disk cache (backend/data/cache/erddap/)
    monkeypatch.setattr("app.extractors.erddap.cache_dir_default", tmp_path_factory.mktemp("erddap-cache"))
    for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"):
        monkeypatch.delenv(name, raising=False)
