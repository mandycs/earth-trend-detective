"""Chat-model factory for the detective agent.

Anthropic direct when LLM_API_KEY is set, else OpenRouter (same Claude model through
the OpenAI-compatible endpoint) when its key exists, else None. Keys are read by the
existing helpers and never logged. Constructing the models makes no network call.
"""

from __future__ import annotations

import os

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.explain.llm import get_api_key
from app.explain.openrouter import get_openrouter_key

ANTHROPIC_MODEL = "claude-sonnet-5-5"
OPENROUTER_MODEL = "anthropic/claude-sonnet-5.5"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
TIMEOUT_S = 60.0  # one model call; a stuck provider must not hold a run forever
MAX_RETRIES = 2


def make_chat_model() -> BaseChatModel | None:
    override = os.environ.get("DETECTIVE_MODEL", "").strip()
    key = get_api_key()
    if key:
        return ChatAnthropic(model=override or ANTHROPIC_MODEL, api_key=key, timeout=TIMEOUT_S, max_retries=MAX_RETRIES)
    or_key = get_openrouter_key()
    if or_key:
        return ChatOpenAI(
            model=override or OPENROUTER_MODEL,
            base_url=OPENROUTER_BASE_URL,
            api_key=or_key,
            timeout=TIMEOUT_S,
            max_retries=MAX_RETRIES,
            default_headers={"X-Title": "Earth Trend Detective"},
        )
    return None
