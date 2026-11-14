"""Test doubles for the Anthropic client (no network)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

SITES_DIR = Path(__file__).resolve().parents[2] / "sites"


def lake_mead_report() -> dict:
    return json.loads((SITES_DIR / "lake_mead" / "site.json").read_text(encoding="utf-8"))


def fake_response(text: str, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(
        model="fake",
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
    )


def fake_client(*texts: str) -> MagicMock:
    """Anthropic-like client whose beta.messages.create returns `texts` in order."""
    client = MagicMock()
    client.beta.messages.create.side_effect = [fake_response(t) for t in texts]
    return client


def json_text(obj: object) -> str:
    return json.dumps(obj)
