"""The work inside the detective graph's nodes: run one tool call, write the checked answer.

- `run_call`: one model tool call against the session. Exceptions become a plain
  `{"status": "failed", "reason": ...}` result (the graph never crashes on a tool).
- `tool_message`: what the model sees (compact JSON, no `chart` / `series` / `transient`,
  verdicts refreshed from the ledger now) and, as `artifact`, the full result for the front.
- `narrate`: the narrator writes at most 3 sentences from the report; the validator checks
  every figure against the ledger; one retry with the rejections; else the code's template.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import ValidationError

from app.detective.ledger import json_safe
from app.detective.prompt import CONCLUDE_PROMPT, conclude_request, retry_request
from app.detective.session import Session
from app.detective.tools import TOOLS
from app.detective.tools.analysis import refresh_verdicts
from app.detective.tools.analysis import WORDING
from app.explain.numbers import extract_numbers
from app.explain.template import template_narrative
from app.explain.validator import MAX_QUESTION_SENTENCES, SENTENCE_SPLIT, validate_narrative

logger = logging.getLogger(__name__)

HIDDEN_KEYS = frozenset({"chart", "series", "transient"})
MAX_REASON = 200
# "this part is human", "it is man-made": the answer may only say "not explained by the climate we measured".
HUMAN_CLAIM = re.compile(
    r"\b(?:is|are|was|were)\s+(?:(?:mostly|largely|partly|all|clearly)\s+)?human\b"
    r"|\b(?:hu)?man[- ]made\b|\bhuman[- ]caused\b",
    re.IGNORECASE,
)


class ToolFailure(Exception):
    """A tool call that could not run; `str(exc)` is the plain reason shown to the model."""


def text_of(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    parts = [b.get("text", "") if isinstance(b, Mapping) else str(b) for b in content]
    return "".join(p for p in parts if p)


def _bad_args(exc: ValidationError) -> str:
    details = "; ".join(f"{'.'.join(str(x) for x in e['loc']) or 'args'}: {e['msg']}" for e in exc.errors())
    return f"bad arguments ({details})"


def run_call(session: Session, call: Mapping) -> dict:
    """Result of one tool call; raises `ToolFailure` with a plain reason when it cannot run."""
    name = str(call.get("name"))
    spec = TOOLS.get(name)
    if spec is None:
        raise ToolFailure(f"unknown tool {name!r}")
    try:
        args = spec.args_schema.model_validate(call.get("args") or {})
    except ValidationError as exc:
        raise ToolFailure(_bad_args(exc)[:MAX_REASON]) from exc
    kwargs = {k: getattr(args, k) for k in type(args).model_fields}
    try:
        return spec.fn(session, **kwargs)
    except Exception as exc:  # noqa: BLE001 - a broken tool is a step result, never a crash
        logger.warning("tool %s raised %s: %s", name, type(exc).__name__, exc)
        raise ToolFailure(f"the tool stopped with an error: {exc}"[:MAX_REASON]) from exc


def _hide(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _hide(v) for k, v in value.items() if k not in HIDDEN_KEYS}
    if isinstance(value, list):
        return [_hide(v) for v in value]
    return value


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def tool_message(session: Session, call: Mapping, result: dict) -> ToolMessage:
    full = json_safe(refresh_verdicts(session, result))  # q / verdict as the correction stands now
    return ToolMessage(compact(_hide(full)), tool_call_id=call["id"], name=call.get("name"), artifact=full)


def failed_message(call: Mapping, reason: str) -> ToolMessage:
    return ToolMessage(
        compact({"status": "failed", "reason": reason}),
        tool_call_id=call["id"],
        name=call.get("name"),
        status="error",
    )


# --------------------------------------------------------------------------- conclude


def check(text: str, report: Mapping) -> tuple[bool, list[str], list[str]]:
    """(accepted, figures quoted, rejection details) for one candidate answer."""
    result = validate_narrative(text, report)
    rejected = [r.detail for r in result.rejected]
    hit = HUMAN_CLAIM.search(text)
    if hit:
        rejected.append(f"'{hit.group(0)}': never say a part is human; say 'not explained by the climate we measured'")
    return not rejected, list(result.checked_numbers), rejected


def template_answer(report: Mapping) -> tuple[str, list[str]]:
    sentences = [s for s in SENTENCE_SPLIT.split(template_narrative(report, residual_wording=WORDING).strip()) if s.strip()]
    text = " ".join(sentences[:MAX_QUESTION_SENTENCES])
    return text, [n.text for n in extract_numbers(text)]


def narrate(
    narrator: BaseChatModel, question: str, report: Mapping, board: Sequence[Mapping]
) -> tuple[str, bool, list[str], str]:
    """(text, checked, figures, source): the model's answer if the validator accepts it within
    two tries, else the template (generated by code from the report, so it counts as checked)."""
    request: list[BaseMessage] = [
        SystemMessage(CONCLUDE_PROMPT),
        HumanMessage(conclude_request(question, report, board)),
    ]
    for _ in range(2):
        try:
            text = text_of(narrator.invoke(request)).strip()
        except Exception as exc:  # noqa: BLE001 - no model answer: the template still answers
            logger.warning("narrator failed: %s", type(exc).__name__)
            break
        ok, figures, rejected = check(text, report)
        if ok:
            return text, True, figures, "llm"
        logger.info("narrator answer rejected on %d point(s)", len(rejected))
        request = [*request, AIMessage(text), HumanMessage(retry_request(rejected))]
    text, figures = template_answer(report)
    return text, True, figures, "template"
