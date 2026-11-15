"""The work inside the detective graph's nodes: run one tool call, write the checked answer.

- `run_call`: one model tool call against the session. Exceptions become a plain
  `{"status": "failed", "reason": ...}` result (the graph never crashes on a tool).
- `tool_message`: what the model sees (compact JSON, no `chart` / `series` / `transient`,
  verdicts refreshed from the ledger now) and, as `artifact`, the full result for the front.
- `narrate`: the narrator writes at most 3 sentences from the report; the validator checks
  every figure against the ledger; one retry with the rejections (two for a "why" question,
  whose first tries tend to claim a cause); else the code's template, which states the data
  cell, the board and what could not be measured. It also returns why each try was rejected
  (`{try, kind, reason}`, with every quoted piece of the model's text taken out).
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
from app.detective.tools.analysis import WORDING, refresh_verdicts
from app.detective.wording import RESIDUAL_WORDING, answer_rejections, cause_problems, without_quotes
from app.explain.numbers import extract_numbers
from app.explain.template import NO_SPLIT_SENTENCE, template_narrative
from app.explain.validator import MAX_QUESTION_SENTENCES, SENTENCE_SPLIT, validate_narrative

logger = logging.getLogger(__name__)

HIDDEN_KEYS = frozenset({"chart", "series", "transient"})
MAX_REASON = 200
TOOL_ERROR_PREFIX = "the tool stopped with an error"  # events.py shows only its own sentence for these
NOTHING_MEASURED = "Nothing could be measured here, so we can't say yet whether anything is changing."
NO_SPLIT = "We have not split this change into the climate and the rest yet."
MAX_NOT_MEASURED = 3
MAX_BOARD_IN_TEMPLATE = 3
TRIES = 2
WHY_TRIES = 3
WHY_QUESTION = re.compile(r"\bwhy\b|\bhow come\b|\bwhat(?:'s| is| are)?\s+(?:causing|behind|making)\b", re.IGNORECASE)
BOARD_WORDS = {
    "supported": "is supported by a test",
    "trend_only": "has a real trend of its own but is not linked to the change",
    "hint": "is only a hint",
    "ruled_out": "is ruled out",
    "open": "is still open",
}


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
        raise ToolFailure(f"{TOOL_ERROR_PREFIX}: {exc}"[:MAX_REASON]) from exc


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


def _rejections(text: str, report: Mapping, board: Sequence[Mapping]) -> tuple[list[str], list[tuple[str, str]]]:
    result = validate_narrative(text, report)
    found = [(r.kind, r.detail) for r in result.rejected] + answer_rejections(text, report, board)
    return list(result.checked_numbers), found


def check(text: str, report: Mapping, board: Sequence[Mapping] = ()) -> tuple[bool, list[str], list[str]]:
    """(accepted, figures quoted, rejection details) for one candidate answer: the shared
    validator, then the detective's own rules (`wording.answer_rejections`)."""
    figures, found = _rejections(text, report, board)
    return not found, figures, [detail for _, detail in found]


def _nothing_measured(report: Mapping) -> str:
    text = NOTHING_MEASURED
    rows = list(report.get("not_measured") or [])[:MAX_NOT_MEASURED]
    if rows:
        text += " What stopped us: " + "; ".join(f"{r['label'].lower()} ({r['reason']})" for r in rows) + "."
    return text


def _clean_name(name: str) -> bool:
    """A suspect name the code may repeat: no figure and no cause claim in it."""
    return bool(name) and not extract_numbers(name) and not cause_problems(name)


def _board_clause(board: Sequence[Mapping]) -> str | None:
    parts = []
    for s in board:
        name = str(s.get("label") or s.get("id") or "").strip()
        words = BOARD_WORDS.get(str(s.get("status")))
        if words and _clean_name(name):
            parts.append(f"{name} {words}")
    if not parts:
        return None
    parts = parts[:MAX_BOARD_IN_TEMPLATE]
    listed = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    return f"on the case board, {listed}"


def _cell_clause(report: Mapping) -> str | None:
    cells = list(report.get("data_cells") or ())
    if not cells:
        return None
    sizes = " or ".join(f"about {c['size_km']:.0f} km" for c in cells)
    return f"each data value covers a cell of {sizes} across, not just this place"


def _missing_clause(report: Mapping) -> str | None:
    asked = list(report.get("asked_not_measured") or ())
    if not asked:
        return None
    reasons = {r["label"]: r["reason"] for r in report.get("not_measured") or ()}
    names = [f"{a.lower()} ({reasons[a]})" if reasons.get(a) else a.lower() for a in asked]
    return f"we could not measure {', '.join(names)} here"


def _extra_sentence(report: Mapping, board: Sequence[Mapping]) -> str | None:
    clauses = [c for c in (_missing_clause(report), _cell_clause(report), _board_clause(board)) if c]
    if not clauses:
        return None
    text = "; ".join(clauses)
    return text[0].upper() + text[1:] + "."


def template_answer(report: Mapping, board: Sequence[Mapping] = ()) -> tuple[str, list[str]]:
    """The code's own answer from the report (no model). With no test that ran it says so.
    Otherwise: what changed, the share not explained by the climate (else whether the change is
    real), then one sentence with what could not be measured, the data cell and the board."""
    if not report.get("n_tests"):
        text = _nothing_measured(report)
    else:
        narrative = template_narrative(report, residual_wording=WORDING).replace(NO_SPLIT_SENTENCE, NO_SPLIT)
        sentences = [s for s in SENTENCE_SPLIT.split(narrative.strip()) if s.strip()]
        extra = _extra_sentence(report, board)
        if extra is None:
            chosen = sentences[:MAX_QUESTION_SENTENCES]
        else:
            share = next((s for s in sentences[1:] if RESIDUAL_WORDING in s.lower()), None)
            second = share or next((s for s in sentences[1:] if s != NO_SPLIT), None)
            chosen = [s for s in (sentences[0] if sentences else None, second) if s][: MAX_QUESTION_SENTENCES - 1]
            chosen.append(extra)
        text = " ".join(chosen)
    return text, [n.text for n in extract_numbers(text)]


def narrate(
    narrator: BaseChatModel, question: str, report: Mapping, board: Sequence[Mapping]
) -> tuple[str, bool, list[str], str, list[dict]]:
    """(text, checked, figures, source, rejected): the model's answer if the validator accepts it
    within two tries (three for a "why" question), else the template (generated by code from the
    report, so it counts as checked). `rejected` lists why each try was turned down."""
    request: list[BaseMessage] = [
        SystemMessage(CONCLUDE_PROMPT),
        HumanMessage(conclude_request(question, report, board)),
    ]
    why = bool(WHY_QUESTION.search(question or ""))
    log: list[dict] = []
    for attempt in range(1, (WHY_TRIES if why else TRIES) + 1):
        try:
            text = text_of(narrator.invoke(request)).strip()
        except Exception as exc:  # noqa: BLE001 - no model answer: the template still answers
            logger.warning("narrator failed: %s", type(exc).__name__)
            break
        figures, found = _rejections(text, report, board)
        if not found:
            return text, True, figures, "llm", log
        logger.info("narrator answer rejected on %d point(s)", len(found))
        log += [{"try": attempt, "kind": kind, "reason": without_quotes(detail)} for kind, detail in found]
        request = [*request, AIMessage(text), HumanMessage(retry_request([d for _, d in found], why=why))]
    text, figures = template_answer(report, board)
    return text, True, figures, "template", log
