"""Thin Claude wrapper: one JSON call (structured output) and one text call.

Every failure (no key, API error, refusal, truncation, bad JSON) returns None so callers
fall back to deterministic text. Never logs the key or the prompts, only model,
stop reason and token counts.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import anthropic
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

REPO_ENV = Path(__file__).resolve().parents[3] / ".env"

# Fast, cheap models for short structured tasks. The temperature knob no longer exists
# on these models; low effort keeps answers short and steady instead.
ROUTE_MODEL = os.environ.get("LLM_MODEL_ROUTE", "claude-haiku-5-5")
NARRATIVE_MODEL = os.environ.get("LLM_MODEL_NARRATIVE", "claude-sonnet-5-5")
# Server-side refusal fallback (beta) exists for Sonnet 5.5, not for Haiku 5.5.
_FALLBACK_MODELS = frozenset({"claude-sonnet-5-5", "claude-opus-5-5"})
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
REQUEST_TIMEOUT_S = 30.0


class LLM(Protocol):
    def json(self, system: str, user: str, schema: dict) -> dict | None: ...

    def text(self, system: str, user: str) -> str | None: ...


def get_api_key() -> str | None:
    """LLM_API_KEY from the environment or the repo-root .env; None if unset or empty."""
    load_dotenv(REPO_ENV)
    key = os.environ.get("LLM_API_KEY", "").strip()
    return key or None


def _text_of(response: Any) -> str | None:
    stop = getattr(response, "stop_reason", None)
    usage = getattr(response, "usage", None)
    logger.info(
        "llm model=%s stop=%s in=%s out=%s",
        getattr(response, "model", "?"),
        stop,
        getattr(usage, "input_tokens", "?"),
        getattr(usage, "output_tokens", "?"),
    )
    if stop not in ("end_turn", "stop_sequence"):
        return None  # refusal, max_tokens, ...
    parts = [b.text for b in getattr(response, "content", ()) if getattr(b, "type", None) == "text"]
    text = "".join(parts).strip()
    return text or None


@dataclass(frozen=True)
class AnthropicLLM:
    client: Any  # anthropic.Anthropic (or a test double with .beta.messages.create)
    route_model: str = ROUTE_MODEL
    narrative_model: str = NARRATIVE_MODEL

    def _create(self, model: str, system: str, user: str, max_tokens: int, output_config: dict) -> str | None:
        kwargs: dict[str, Any] = {}
        if model in _FALLBACK_MODELS:
            kwargs = {"betas": [_FALLBACK_BETA], "fallbacks": "default"}
        try:
            response = self.client.beta.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config=output_config,
                **kwargs,
            )
        except anthropic.APIStatusError as exc:
            logger.warning("llm %s failed: HTTP %s %s", model, exc.status_code, type(exc).__name__)
            return None
        except anthropic.APIConnectionError as exc:
            logger.warning("llm %s unreachable: %s", model, type(exc).__name__)
            return None
        return _text_of(response)

    def json(self, system: str, user: str, schema: dict) -> dict | None:
        raw = self._create(
            self.route_model,
            system,
            user,
            max_tokens=2048,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        )
        if raw is None:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("llm %s returned invalid JSON", self.route_model)
            return None
        return data if isinstance(data, dict) else None

    def text(self, system: str, user: str) -> str | None:
        return self._create(self.narrative_model, system, user, max_tokens=4096, output_config={"effort": "low"})


def make_llm() -> LLM | None:
    """Claude via LLM_API_KEY (Anthropic), else via OpenRouter if its key is available,
    else None (template mode)."""
    key = get_api_key()
    if key is not None:
        return AnthropicLLM(anthropic.Anthropic(api_key=key, timeout=REQUEST_TIMEOUT_S, max_retries=1))
    from app.explain.openrouter import make_openrouter_llm  # local import: optional provider

    return make_openrouter_llm()
