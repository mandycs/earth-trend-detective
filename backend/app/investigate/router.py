"""POST /investigate: the investigation as a Server-Sent Events stream."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from app.explain.llm import LLM
from app.explain.router import get_llm
from app.investigate.runner import Event, investigate
from app.sites import load_sites

router = APIRouter(tags=["investigate"])


class InvestigateRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    site_id: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def _one_place(self) -> "InvestigateRequest":
        coords = (self.lat is not None, self.lon is not None)
        if (self.site_id is not None and not any(coords)) or (self.site_id is None and all(coords)):
            return self
        raise ValueError("Send either a site_id or both lat and lon, not both and not neither.")


def get_investigate() -> Callable[..., Iterator[Event]]:
    """The investigation runner (overridden in tests)."""
    return investigate


def sse(events: Iterator[Event]) -> Iterator[str]:
    for e in events:
        yield f"event: {e['event']}\ndata: {json.dumps(e['data'], ensure_ascii=False, allow_nan=False)}\n\n"


@router.post("/investigate")
def post_investigate(
    body: InvestigateRequest,
    llm: LLM | None = Depends(get_llm),
    run: Callable[..., Iterator[Event]] = Depends(get_investigate),
) -> StreamingResponse:
    """Stream: place -> plan -> step_start/step_done|step_failed per step -> done."""
    if body.site_id is not None and load_sites().get(body.site_id) is None:
        known = ", ".join(s.id for s in load_sites().sites)
        raise HTTPException(404, f"We don't know a site called '{body.site_id}'. Pick one of: {known}.")
    events = run(body.question, lat=body.lat, lon=body.lon, site_id=body.site_id, llm=llm)
    return StreamingResponse(
        sse(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
