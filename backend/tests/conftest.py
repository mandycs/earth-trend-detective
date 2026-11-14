"""Test-wide safety: no test may pick up a real LLM key from the machine."""

import pytest


@pytest.fixture(autouse=True)
def _no_real_llm_keys(monkeypatch, tmp_path_factory):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_KEY_FILE", str(tmp_path_factory.mktemp("nokey") / "missing"))
