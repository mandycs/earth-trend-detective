"""A last guard for strings shown in the UI: links, key-like values and file paths masked."""

from __future__ import annotations

import re

_MASKS = (
    (re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.I), "[link]"),
    (re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}(?::\d+)?/\S*", re.I), "[link]"),
    (re.compile(r"\bbearer\s+\S+", re.I), "bearer [hidden]"),
    (
        re.compile(r"\b((?:x-)?api[_-]?key|access[_-]?token|token|secret|password|authorization)\b\s*[:=]\s*\S+", re.I),
        r"\1=[hidden]",
    ),
    (re.compile(r"(?<![\w.°])(?:~|/[\w.-]+)(?:/[\w.-]+)+/?"), "[path]"),
    (re.compile(r"\b[a-z]:\\\S+", re.I), "[path]"),
)


def scrub(text: str) -> str:
    """`text` with links, key-like values and file paths masked."""
    for pattern, mask in _MASKS:
        text = pattern.sub(mask, text)
    return text


_LONG_TOKEN = re.compile(r"\b(?:sk|pk|rk)-[\w-]{6,}|\b[A-Za-z0-9_\-]{32,}\b")
LOG_REASON_MAX = 200


def log_reason(exc: BaseException) -> str:
    """`Type: short message` for a server log: links, keys, long tokens and paths masked, one line, capped."""
    text = " ".join(_LONG_TOKEN.sub("[hidden]", scrub(str(exc))).split())
    if len(text) > LOG_REASON_MAX:
        text = text[: LOG_REASON_MAX - 1] + "…"
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__
