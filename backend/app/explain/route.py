"""Question -> catalog variable ids.

Claude picks from an enum of the allowed ids (structured output). The answer is
filtered against the enum again, so an id outside the list can never get through.
Without a key (or on any failure) a keyword router answers instead.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass

from app.explain.llm import LLM
from app.explain.prompts import ROUTE_SYSTEM, route_user
from app.explain.vocab import TOPIC_KEYWORDS, UNKNOWN_ID, VARIABLE_ALIASES

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RouteResult:
    ids: tuple[str, ...]
    source: str  # "llm" | "template"

    def to_dict(self) -> dict:
        return {"ids": list(self.ids), "source": self.source}


def route_schema(allowed_ids: tuple[str, ...]) -> dict:
    return {
        "type": "object",
        "properties": {
            "ids": {"type": "array", "items": {"type": "string", "enum": [*allowed_ids, UNKNOWN_ID]}},
        },
        "required": ["ids"],
        "additionalProperties": False,
    }


def clean_ids(raw: object, allowed_ids: tuple[str, ...]) -> tuple[str, ...]:
    """Keep allowed ids only, in order, no duplicates; ("unknown",) if nothing is left."""
    allowed = set(allowed_ids)
    out: list[str] = []
    for item in raw if isinstance(raw, list) else ():
        if isinstance(item, str) and item in allowed:
            if item not in out:
                out.append(item)
        elif item != UNKNOWN_ID:
            logger.warning("route dropped id outside the enum")
    return tuple(out) or (UNKNOWN_ID,)


def keyword_route(question: str, choices: Mapping[str, str]) -> tuple[str, ...]:
    """Deterministic router: variable names and topic words found in the question."""
    q = question.lower()
    hits: list[str] = []
    for vid, label in choices.items():
        names = (label.lower(), *VARIABLE_ALIASES.get(vid, ()))
        if any(re.search(r"\b" + re.escape(n), q) for n in names):
            hits.append(vid)
    for word, ids in TOPIC_KEYWORDS.items():
        if re.search(r"\b" + re.escape(word), q):
            hits.extend(i for i in ids if i in choices)
    return clean_ids(hits, tuple(choices))


def route_question(question: str, choices: Mapping[str, str], llm: LLM | None) -> RouteResult:
    """`choices` maps allowed id -> label (the enum)."""
    allowed = tuple(choices)
    if llm is not None:
        data = llm.json(ROUTE_SYSTEM, route_user(question, choices), route_schema(allowed))
        if data is not None:
            return RouteResult(clean_ids(data.get("ids"), allowed), "llm")
    return RouteResult(keyword_route(question, choices), "template")
