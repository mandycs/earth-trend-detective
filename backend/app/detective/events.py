"""The detective run as a stream of events for the front (spec §5.4).

    place -> (thinking -> tool_start -> tool_done | tool_failed -> map* -> board?)* -> board -> answer -> done
    error {message} replaces the rest when something outside the tools breaks.

The graph runs with `stream_mode="updates"`; each node update is turned into events here.
Nothing in an event is computed by the model: results, the board and the answer come from
the graph's state (the case), and the board is re-judged by `board.evaluate` every time.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from pydantic import BaseModel, Field, model_validator

from app.detective import board as case_board
from app.detective.graph import BUDGET_REACHED, new_case
from app.detective.ledger import Ledger, json_safe
from app.detective.nodes import text_of
from app.detective.place import Place
from app.detective.report import n_finite_tests
from app.detective.session import Session
from app.investigate.landcover import box_around
from app.sites import load_sites

logger = logging.getLogger(__name__)

Event = dict[str, Any]

NO_PLACE = "Pick a point or draw a box on the map first."
BAD_BOX = "The box must be [min_lon, min_lat, max_lon, max_lat] in degrees, with min below max."
NO_THREAD = "A checkpoint_id needs the thread_id of its investigation."
NO_MODEL = "The investigator needs a language model key on the server."
UNEXPECTED = "The investigation stopped on an unexpected error. Please try again."
UNKNOWN_CASE = "Unknown case."
UNKNOWN_STEP = "We could not find that step of the investigation."
MID_STEP = "Pick a step after a tool finished."
OTHER_PLACE = "That step belongs to an investigation of another place."
SOURCE_DOWN = "The data source did not answer."
FAILED_STATUSES = frozenset({"not_available", "rejected", "failed"})
_LINK = re.compile(r"https?://\S+")


class DetectiveRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)  # [min_lon, min_lat, max_lon, max_lat]
    site_id: str | None = Field(default=None, max_length=100)
    thread_id: str | None = Field(default=None, min_length=1, max_length=100)
    checkpoint_id: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def _a_place(self) -> DetectiveRequest:
        if self.bbox is not None:
            w, s, e, n = self.bbox
            if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
                raise ValueError(BAD_BOX)
        point = self.lat is not None and self.lon is not None
        if self.site_id is None and self.bbox is None and not point:
            raise ValueError(NO_PLACE)
        if self.checkpoint_id is not None and self.thread_id is None:
            raise ValueError(NO_THREAD)
        return self


class RunRefused(Exception):
    """The request cannot start a run (an HTTP error, not an event)."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class Run:
    thread_id: str
    config: dict
    input: dict
    case: dict  # the case before the run (to diff map ops and failures against)
    follow_up: bool
    forked_from: str | None = None


def event(kind: str, **data: Any) -> Event:
    return {"event": kind, "data": json_safe(data)}


# --------------------------------------------------------------------------- the place


def place_for(req: DetectiveRequest) -> Place:
    """The `Place` a request points at: a solved case as configured, a drawn box or a picked point."""
    if req.site_id is not None:
        site = load_sites().get(req.site_id)
        if site is None:
            raise RunRefused(422, UNKNOWN_CASE)
        return Place(lat=site.lat, lon=site.lon, bbox=tuple(site.bbox), tags=tuple(site.tags), site_id=site.id)
    if req.bbox is not None:
        w, s, e, n = (float(v) for v in req.bbox)
        point = req.lat is not None and req.lon is not None
        lat, lon = (req.lat, req.lon) if point else ((s + n) / 2, (w + e) / 2)
        return Place(lat=float(lat), lon=float(lon), bbox=(w, s, e, n))
    return Place(lat=float(req.lat), lon=float(req.lon), bbox=box_around(float(req.lat), float(req.lon)))


def _place_key(p: Mapping) -> tuple:
    return (
        round(float(p["lat"]), 6),
        round(float(p["lon"]), 6),
        tuple(round(float(v), 6) for v in p["bbox"]),
        p.get("site_id"),
    )


def _same_place(case: Mapping, place: Place) -> bool:
    return _place_key(case["place"]) == _place_key({"lat": place.lat, "lon": place.lon, "bbox": place.bbox, "site_id": place.site_id})


def place_payload(case: Mapping) -> dict:
    p = case["place"]
    site = load_sites().get(p["site_id"]) if p.get("site_id") else None
    return {
        "id": p.get("site_id") or "point",
        "name": site.name if site else f"Point {float(p['lat']):.3f}, {float(p['lon']):.3f}",
        "lat": p["lat"],
        "lon": p["lon"],
        "bbox": list(p["bbox"]),
        "tags": list(p.get("tags") or []),
        "site_id": p.get("site_id"),
        "years": [case.get("start"), case.get("end")],
    }


# --------------------------------------------------------------------------- the run


def _pending_calls(messages: list[BaseMessage]) -> bool:
    last = messages[-1] if messages else None
    return isinstance(last, AIMessage) and bool(last.tool_calls)


def prepare_run(graph: Any, req: DetectiveRequest) -> Run:
    """Which thread and checkpoint the request runs on, and the graph input.

    - `checkpoint_id`: a fork from that step of the thread (same place only).
    - `thread_id` of the same place: a follow-up (ledger, FDR family and board kept).
    - `thread_id` of another place: a new thread (the ledger cache key does not hold the place).
    """
    place = place_for(req)
    question = HumanMessage(req.question.strip())
    if req.checkpoint_id is not None:
        config = {"configurable": {"thread_id": req.thread_id, "checkpoint_id": req.checkpoint_id}}
        values = graph.get_state(config).values or {}
        case = values.get("case")
        if not case:
            raise RunRefused(404, UNKNOWN_STEP)
        if _pending_calls(values.get("messages") or []):
            raise RunRefused(422, MID_STEP)
        if not _same_place(case, place):
            raise RunRefused(422, OTHER_PLACE)
        return Run(req.thread_id, config, {"messages": [question]}, case, True, req.checkpoint_id)
    if req.thread_id is not None:
        config = {"configurable": {"thread_id": req.thread_id}}
        case = (graph.get_state(config).values or {}).get("case")
        if case and _same_place(case, place):
            return Run(req.thread_id, config, {"messages": [question]}, case, True)
        thread_id = req.thread_id if not case else uuid.uuid4().hex
    else:
        thread_id = uuid.uuid4().hex
    case = new_case(place)
    return Run(thread_id, {"configurable": {"thread_id": thread_id}}, {"messages": [question], "case": case}, case, False)


def _plain(reason: Any) -> str:
    return _LINK.sub("[link]", str(reason or "")).strip() or SOURCE_DOWN


def _tool_content(message: ToolMessage) -> dict:
    if isinstance(message.artifact, Mapping):
        return dict(message.artifact)
    try:
        content = json.loads(text_of(message))
    except (TypeError, ValueError):
        return {"status": "failed", "reason": text_of(message)}
    return content if isinstance(content, dict) else {}


def summary_of(result: Mapping) -> str:
    """One plain line about a tool result, with no figure of its own."""
    status = result.get("status")
    if status in FAILED_STATUSES:
        return f"{'Rejected' if status == 'rejected' else 'Not available'}: {_plain(result.get('reason'))}"
    label = result.get("label") or result.get("var_id") or result.get("series_id")
    verdict = result.get("verdict")
    parts = [str(label)] if label else []
    if verdict:
        parts.append(f"verdict {verdict}")
    elif result.get("note"):
        parts.append(str(result["note"]).rstrip("."))
    return (". ".join(parts) + ".") if parts else "Done."


def board_payload(case: Mapping) -> dict:
    """The board re-judged against the correction as it stands now, and the number of tests."""
    session = Session.from_state(case, (), None, "")
    judged = case_board.evaluate(session.board, session.ledger)
    return {"suspects": case_board.as_json(judged), "n_tests": n_finite_tests(session.ledger)}


def answer_payload(answer: Mapping | None) -> dict | None:
    if not answer:
        return None
    return {"text": answer.get("text"), "checked": bool(answer.get("checked")), "figures": list(answer.get("figures") or [])}


def _agent_events(values: Mapping) -> Iterator[Event]:
    for reply in values.get("messages") or []:
        if not isinstance(reply, AIMessage) or not reply.tool_calls:
            continue
        text = text_of(reply).strip()
        if text:
            yield event("thinking", text=text)
        for call in reply.tool_calls:
            yield event("tool_start", id=call.get("id"), tool=call.get("name"), args=call.get("args") or {})


def _tool_events(messages: list, failures: Mapping[str, Mapping]) -> Iterator[Event]:
    for m in messages:
        if not isinstance(m, ToolMessage):
            continue
        cid, tool = m.tool_call_id, m.name
        if cid in failures:
            yield event("tool_failed", id=cid, tool=tool, reason=_plain(failures[cid].get("reason")))
        elif text_of(m) == BUDGET_REACHED:
            yield event("tool_failed", id=cid, tool=tool, reason=BUDGET_REACHED)
        else:
            result = _tool_content(m)
            if result.get("transient"):  # a source that did not answer: not evidence, not cached
                yield event("tool_failed", id=cid, tool=tool, reason=_plain(result.get("reason")))
            else:
                summary = summary_of(result)
                yield event("tool_done", id=cid, tool=tool, summary=summary, result=result, evidence_id=result.get("evidence_id"))


def stream_run(graph: Any, run: Run) -> Iterator[Event]:
    """Events of one run; anything that breaks outside the tools ends it with one `error`."""
    try:
        yield event("place", thread_id=run.thread_id, follow_up=run.follow_up, forked_from=run.forked_from, **place_payload(run.case))
        case = run.case
        last_board = board_payload(case)
        n_calls = 0
        for update in graph.stream(run.input, run.config, stream_mode="updates"):
            for node, values in (update or {}).items():
                if not isinstance(values, Mapping):
                    continue
                after = values.get("case") or case
                if node == "agent":
                    yield from _agent_events(values)
                elif node == "tools":
                    known = len(case.get("failures") or [])
                    new = {f.get("id"): f for f in (after.get("failures") or [])[known:] if f.get("id")}
                    yield from _tool_events(values.get("messages") or [], new)
                    for op in (after.get("map") or [])[len(case.get("map") or []) :]:
                        yield event("map", **op)
                    board = board_payload(after)
                    if board["suspects"] != last_board["suspects"]:  # a new test alone is not a board change
                        yield event("board", **board)
                    last_board = board
                elif node == "conclude":
                    yield from _tool_events(values.get("messages") or [], {})  # calls left when the budget ran out
                    last_board = board_payload(after)
                    yield event("board", **last_board)
                    answer = answer_payload(values.get("answer"))
                    if answer:
                        yield event("answer", **answer)
                case = after
                if "tool_calls" in values:
                    n_calls = int(values["tool_calls"] or 0)
        yield event("done", thread_id=run.thread_id, n_tests=last_board["n_tests"], n_tool_calls=n_calls)
    except Exception as exc:  # noqa: BLE001 - a plain message, never a trace, URL or key
        logger.warning("detective run failed: %s", type(exc).__name__)
        yield event("error", message=UNEXPECTED)


# --------------------------------------------------------------------------- re-opening a thread


def history(graph: Any, thread_id: str) -> list[dict] | None:
    """Steps of a thread that a run can be forked from, newest first (None: no such thread)."""
    snapshots = list(graph.get_state_history({"configurable": {"thread_id": thread_id}}))
    if not snapshots:
        return None
    out = []
    for snap in snapshots:
        values = snap.values or {}
        messages, case = values.get("messages") or [], values.get("case")
        if (snap.metadata or {}).get("source") != "loop" or not messages or not case:
            continue
        last = messages[-1]
        item = {
            "checkpoint_id": snap.config["configurable"]["checkpoint_id"],
            "step": (snap.metadata or {}).get("step"),
        }
        if isinstance(last, ToolMessage):
            item |= {"kind": "tool", "tool": last.name, "summary": summary_of(_tool_content(last))}
        elif isinstance(last, AIMessage) and not last.tool_calls and values.get("answer"):
            item |= {"kind": "answer", "summary": (values["answer"] or {}).get("text")}
        else:
            continue
        item |= {"n_tests": n_finite_tests(Ledger.from_state(case["ledger"])), "created_at": snap.created_at}
        out.append(item)
    return out


def current_case(graph: Any, thread_id: str) -> dict | None:
    """The thread as it stands: place, question, board, map ops and answer (None: no such thread)."""
    values = graph.get_state({"configurable": {"thread_id": thread_id}}).values or {}
    case = values.get("case")
    if not case:
        return None
    human = [m for m in values.get("messages") or [] if isinstance(m, HumanMessage)]
    return json_safe(
        {
            "thread_id": thread_id,
            "place": place_payload(case),
            "question": text_of(human[-1]).strip() if human else None,
            "board": board_payload(case),
            "map": list(case.get("map") or []),
            "answer": answer_payload(values.get("answer")),
            "n_tool_calls": int(values.get("tool_calls") or 0),
        }
    )
