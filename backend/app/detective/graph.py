"""The detective graph: a real tool loop, then a checked answer.

    START -> agent -(tool calls, budget left)-> tools -(budget left)-> agent ...
                  \\-(no tool calls / budget spent)-> conclude -> END
                                       tools -(budget spent)-> conclude

State: `messages` (the conversation), `case` (the JSON-safe `Session.to_state()` plus
`failures` and `run_started`), `tool_calls` (calls made in the current run) and `answer`.
Every node rebuilds the `Session` from `case` (series from the store) and returns a new
`case`, so each checkpoint holds the case as it was at that step: a thread can be resumed
after a restart, replayed step by step and forked from any checkpoint.

A run starts when the last message is the user's: the tool budget and the clock restart.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from dataclasses import asdict
from typing import Annotated, Any, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.store.base import BaseStore

from app.catalog import Variable, load_catalog
from app.detective import board as case_board
from app.detective.ledger import Ledger, json_safe
from app.detective.nodes import (
    ToolFailure,
    failed_message,
    narrate,
    next_questions,
    run_call,
    text_of,
    tool_message,
)
from app.detective.persistence import save_series, save_tests
from app.detective.place import Place
from app.detective.prompt import SYSTEM_PROMPT
from app.detective.report import ledger_report, n_finite_tests
from app.detective.session import Session
from app.detective.tools import TOOLS

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOOL_CALLS = 40
BUDGET_REACHED = "Budget reached."
AGENT_DOWN = "The model did not answer."


class DetectiveState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    case: dict
    tool_calls: int
    answer: dict | None


def limits_from_env() -> tuple[int, float | None]:
    """(`DETECTIVE_MAX_TOOL_CALLS`, default 40; `DETECTIVE_MAX_SECONDS`, default none)."""
    calls = os.environ.get("DETECTIVE_MAX_TOOL_CALLS", "").strip()
    seconds = os.environ.get("DETECTIVE_MAX_SECONDS", "").strip()
    return (int(calls) if calls else DEFAULT_MAX_TOOL_CALLS, float(seconds) if seconds else None)


def new_case(place: Place, start: int = 2003, end: int = 2024) -> dict:
    """The `case` of a new thread, to pass in the first input with the user's question."""
    case = Session(ledger=Ledger(), place=place, catalog=(), start=start, end=end).to_state()
    return {**case, "failures": []}


def tool_specs() -> list[dict]:
    """The registry as tool definitions for `bind_tools` (name and description from `TOOLS`)."""
    out = []
    for name, spec in TOOLS.items():
        tool = convert_to_openai_tool(spec.args_schema)
        tool["function"] |= {"name": name, "description": spec.description}
        out.append(tool)
    return out


def _thread_id(config: RunnableConfig) -> str:
    return str((config.get("configurable") or {}).get("thread_id") or "default")


def _pending_calls(state: DetectiveState) -> list[dict]:
    messages = state.get("messages") or []
    last = messages[-1] if messages else None
    return list(last.tool_calls) if isinstance(last, AIMessage) and last.tool_calls else []


def _question(state: DetectiveState) -> str:
    human = [m for m in state.get("messages") or [] if isinstance(m, HumanMessage)]
    return text_of(human[-1]).strip() if human else ""


def _earlier_answer(state: DetectiveState) -> str | None:
    """The answer of the previous question in this thread (None on a first question)."""
    messages = list(state.get("messages") or [])
    last_human = max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=None)
    if last_human is None:
        return None
    before = [m for m in messages[:last_human] if isinstance(m, AIMessage) and not m.tool_calls]
    return text_of(before[-1]).strip() or None if before else None


def _place_note(case: dict) -> str:
    p = case.get("place") or {}
    where = f"lat {p.get('lat')}, lon {p.get('lon')}, box {p.get('bbox')}"
    site = f"; solved case '{p['site_id']}'" if p.get("site_id") else ""
    return f"\n\nThe place picked: {where}{site}. Years {case.get('start')}-{case.get('end')}."


def build_graph(
    model: BaseChatModel,
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
    max_seconds: float | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
    *,
    narrator: BaseChatModel | None = None,
    catalog: tuple[Variable, ...] | None = None,
    clock: Callable[[], float] = time.time,
) -> Any:
    """Compiled detective graph. `model` runs the tool loop (tools bound from `TOOLS`);
    `narrator` (default: `model`, unbound) writes the final answer."""
    catalog = load_catalog() if catalog is None else catalog
    narrator = model if narrator is None else narrator
    agent_model = model.bind_tools(tool_specs())

    def budget_left(state: DetectiveState) -> bool:
        if int(state.get("tool_calls") or 0) >= max_tool_calls:
            return False
        if max_seconds is None:
            return True
        started = (state.get("case") or {}).get("run_started")
        return started is None or clock() - float(started) < max_seconds

    def session_of(case: dict, config: RunnableConfig, with_series: bool = True) -> Session:
        return Session.from_state(case, catalog, store, _thread_id(config), with_series=with_series)

    def agent(state: DetectiveState, config: RunnableConfig) -> dict:
        messages = state.get("messages") or []
        case = dict(state["case"])
        update: dict = {}
        if messages and isinstance(messages[-1], HumanMessage):  # a new run: budget and clock restart
            case["run_started"] = clock()
            update |= {"case": case, "tool_calls": 0, "answer": None}
        try:
            reply = agent_model.invoke([SystemMessage(SYSTEM_PROMPT + _place_note(case)), *messages])
        except Exception as exc:  # noqa: BLE001 - no model: conclude answers from what the case holds
            logger.warning("agent model failed: %s", type(exc).__name__)
            failure = {"tool": "agent", "id": None, "reason": AGENT_DOWN}
            return update | {"case": {**case, "failures": [*(case.get("failures") or []), failure]}}
        return update | {"messages": [reply]}

    def tools(state: DetectiveState, config: RunnableConfig) -> dict:
        case = state["case"]
        session = session_of(case, config)
        known = set(session.series)
        made = int(state.get("tool_calls") or 0)
        failures = list(case.get("failures") or [])
        out: list[ToolMessage] = []
        for call in _pending_calls(state):
            if made >= max_tool_calls:
                out.append(ToolMessage(BUDGET_REACHED, tool_call_id=call["id"], name=call.get("name")))
                continue
            made += 1
            try:
                out.append(tool_message(session, call, run_call(session, call)))
            except ToolFailure as exc:
                failures.append({"tool": call.get("name"), "id": call["id"], "reason": str(exc)})
                out.append(failed_message(call, str(exc)))
        if store is not None:  # the store is the only place series live, and holds every test of the thread
            for sid, series in session.series.items():
                if sid not in known:
                    save_series(store, _thread_id(config), sid, series)
            save_tests(store, _thread_id(config), session.ledger.keyed_tests())
        new_case = {**case, **session.to_state(), "failures": failures}
        return {"messages": out, "case": new_case, "tool_calls": made}

    def conclude(state: DetectiveState, config: RunnableConfig) -> dict:
        case = state["case"]
        pending = [ToolMessage(BUDGET_REACHED, tool_call_id=c["id"], name=c.get("name")) for c in _pending_calls(state)]
        session = session_of(case, config, with_series=False)  # the report needs no series
        judged = case_board.evaluate(session.board, session.ledger, session.catalog)
        board_rows = case_board.as_json(judged)
        report = ledger_report(session, _question(state))
        text, checked, figures, source, rejected = narrate(
            narrator, _question(state), report, board_rows, earlier=_earlier_answer(state)
        )
        answer = {
            "text": text,
            "checked": checked,
            "figures": figures,
            "source": source,
            "rejected": rejected,
            "n_tests": n_finite_tests(session.ledger),
            "next_questions": next_questions(report, board_rows, session),
        }
        new_case = {**case, "board": json_safe({k: asdict(s) for k, s in judged.items()})}
        return {"messages": [*pending, AIMessage(text)], "case": new_case, "answer": answer}

    def after_agent(state: DetectiveState) -> str:
        return "tools" if _pending_calls(state) and budget_left(state) else "conclude"

    def after_tools(state: DetectiveState) -> str:
        return "agent" if budget_left(state) else "conclude"

    graph = StateGraph(DetectiveState)
    graph.add_node("agent", agent)
    graph.add_node("tools", tools)
    graph.add_node("conclude", conclude)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", after_agent, ["tools", "conclude"])
    graph.add_conditional_edges("tools", after_tools, ["agent", "conclude"])
    graph.add_edge("conclude", END)
    return graph.compile(checkpointer=checkpointer, store=store)
