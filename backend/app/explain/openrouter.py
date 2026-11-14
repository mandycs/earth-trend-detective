"""OpenRouter provider (OpenAI-compatible chat completions) for the same Claude models.

Used when no direct Anthropic key (LLM_API_KEY) is set. The key is read at runtime from
OPENROUTER_API_KEY or from the file named by OPENROUTER_KEY_FILE (default
~/.secrets/openkey); it is never logged. Every failure returns None so callers fall
back to the deterministic template, exactly like the Anthropic wrapper.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_KEY_FILE = Path.home() / ".secrets" / "openkey"
ROUTE_MODEL = os.environ.get("OPENROUTER_MODEL_ROUTE", "anthropic/claude-haiku-5.5")
NARRATIVE_MODEL = os.environ.get("OPENROUTER_MODEL_NARRATIVE", "anthropic/claude-sonnet-5.5")
TIMEOUT_S = 45.0


def get_openrouter_key() -> str | None:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    path = Path(os.environ.get("OPENROUTER_KEY_FILE", str(DEFAULT_KEY_FILE))).expanduser()
    try:
        key = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return key or None


def _content(data: Any, model: str) -> str | None:
    try:
        choice = data["choices"][0]
        finish = choice.get("finish_reason")
        usage = data.get("usage") or {}
        logger.info(
            "llm openrouter model=%s finish=%s in=%s out=%s",
            data.get("model", model), finish, usage.get("prompt_tokens", "?"), usage.get("completion_tokens", "?"),
        )
        if finish not in ("stop", "end_turn", None):
            return None  # length, content_filter, ...
        text = (choice["message"].get("content") or "").strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        logger.warning("llm openrouter %s returned an unexpected body", model)
        return None
    return text or None


@dataclass(frozen=True)
class OpenRouterLLM:
    client: Any  # httpx.Client with auth header (or a test double with .post)
    route_model: str = ROUTE_MODEL
    narrative_model: str = NARRATIVE_MODEL

    def _create(self, model: str, system: str, user: str, max_tokens: int, extra: dict | None = None) -> str | None:
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            **(extra or {}),
        }
        try:
            response = self.client.post(OPENROUTER_URL, json=body)
        except httpx.HTTPError as exc:
            logger.warning("llm openrouter %s unreachable: %s", model, type(exc).__name__)
            return None
        if response.status_code >= 400:
            logger.warning("llm openrouter %s failed: HTTP %s", model, response.status_code)
            return None
        try:
            data = response.json()
        except ValueError:
            logger.warning("llm openrouter %s returned non-JSON", model)
            return None
        return _content(data, model)

    def json(self, system: str, user: str, schema: dict) -> dict | None:
        fmt = {"type": "json_schema", "json_schema": {"name": "answer", "strict": True, "schema": schema}}
        raw = self._create(self.route_model, system, user, 2048, {"response_format": fmt})
        if raw is None:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("llm openrouter %s returned invalid JSON", self.route_model)
            return None
        return data if isinstance(data, dict) else None

    def text(self, system: str, user: str) -> str | None:
        return self._create(self.narrative_model, system, user, 4096)


def make_openrouter_llm() -> OpenRouterLLM | None:
    key = get_openrouter_key()
    if key is None:
        return None
    client = httpx.Client(
        timeout=TIMEOUT_S,
        headers={"Authorization": f"Bearer {key}", "X-Title": "Earth Trend Detective"},
    )
    return OpenRouterLLM(client)
