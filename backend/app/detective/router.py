"""POST /detective: the investigation as Server-Sent Events; GET to re-open, replay and fork it.

- `POST /detective` streams one run (see `events`). With `thread_id` it is a follow-up on the
  same case; with `checkpoint_id` too, a fork from that step.
- `GET /detective/{thread_id}/history`: the steps a run can be forked from, newest first.
- `GET /detective/{thread_id}`: the case as it stands (board, map ops, answer).

The checkpointer and store are opened and closed once per process by the app's lifespan
(`startup_persistence` / `shutdown_persistence`). The GET endpoints read the checkpointer
directly (no model, no graph). Tests override `get_persistence` and `get_detective_model`.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable, Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

from app.detective.events import (
    NO_MODEL,
    UNEXPECTED,
    DetectiveRequest,
    Event,
    RunRefused,
    current_case,
    event,
    history,
    place_for,
    prepare_run,
    stream_run,
)
from app.detective.graph import build_graph, limits_from_env
from app.detective.model import make_chat_model
from app.detective.persistence import close_persistence, open_persistence
from app.investigate.router import sse

router = APIRouter(tags=["detective"])

Persistence = tuple[BaseCheckpointSaver, BaseStore]
UNKNOWN_THREAD = "We could not find that investigation."
NOT_READY = "The investigator is not ready yet. Try again in a moment."
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

_lock = threading.Lock()
_persistence: Persistence | None = None


def get_detective_model() -> BaseChatModel | None:
    """The agent's chat model, or None without a key (overridden in tests)."""
    return make_chat_model()


def startup_persistence() -> None:
    """Open the process-wide checkpointer and store (the app's lifespan calls this)."""
    global _persistence
    with _lock:
        if _persistence is None:
            _persistence = open_persistence()


def get_persistence() -> Persistence:
    """The process-wide checkpointer and store opened by the lifespan (overridden in tests)."""
    with _lock:
        if _persistence is None:
            raise HTTPException(503, NOT_READY)
        return _persistence


def shutdown_persistence() -> None:
    """Close the process-wide checkpointer and store (the app's lifespan calls this)."""
    global _persistence
    with _lock:
        if _persistence is not None:
            close_persistence(*_persistence)
            _persistence = None


def _graph(model: BaseChatModel, persistence: Persistence):  # noqa: ANN202
    saver, store = persistence
    return build_graph(model, *limits_from_env(), checkpointer=saver, store=store)


def _stream(events: Iterable[Event]) -> StreamingResponse:
    return StreamingResponse(sse(iter(events)), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/detective")
def post_detective(
    body: DetectiveRequest,
    model: BaseChatModel | None = Depends(get_detective_model),
    persistence: Persistence = Depends(get_persistence),
) -> StreamingResponse:
    """Stream: place -> thinking / tool_start / tool_done | tool_failed / map / board -> board -> answer -> done."""
    try:
        place_for(body)  # an unknown case is a 422, with or without a model
    except RunRefused as exc:
        raise HTTPException(exc.status, exc.message) from None
    if model is None:
        return _stream([event("error", message=NO_MODEL)])
    try:
        graph = _graph(model, persistence)
        run = prepare_run(graph, body)
    except RunRefused as exc:
        raise HTTPException(exc.status, exc.message) from None
    except Exception:  # noqa: BLE001 - a plain message, never a trace
        return _stream([event("error", message=UNEXPECTED)])
    events: Iterator[Event] = stream_run(graph, run)
    return _stream(events)


@router.get("/detective/{thread_id}/history")
def get_history(
    thread_id: str,
    persistence: Persistence = Depends(get_persistence),
) -> list[dict]:
    steps = history(persistence[0], thread_id)
    if steps is None:
        raise HTTPException(404, UNKNOWN_THREAD)
    return steps


@router.get("/detective/{thread_id}")
def get_case(
    thread_id: str,
    persistence: Persistence = Depends(get_persistence),
) -> dict:
    case = current_case(persistence[0], thread_id)
    if case is None:
        raise HTTPException(404, UNKNOWN_THREAD)
    return case
