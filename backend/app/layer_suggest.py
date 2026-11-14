"""POST /layers/suggest: which map layers to show for a question (the LLM picks, code checks).

The choice is closed: only layer ids from the site's layers.json. The answer is cleaned
like the investigator's plan: unknown ids dropped, at most MAX_LAYERS, reasons and
caption without figures, year only from the site's timeline. A picture layer is always
kept at the bottom so the map is never empty. Without an LLM, keywords pick the stack.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.explain.llm import LLM
from app.explain.router import get_llm, get_sites_dir
from app.sites import load_sites

logger = logging.getLogger(__name__)

MAX_LAYERS = 4
MAX_WHY = 140
_DIGIT = re.compile(r"\d")
BASE_IDS = {"overview": ("base_hq", "base"), "drone": ("detail", "base_hq", "base")}
DEFAULT_CAPTION = "These layers show what the question is about. Change any of them in the layer list."
KEYWORDS: Sequence[tuple[tuple[str, ...], tuple[str, ...]]] = (
    (("green", "vegetat", "plant", "crop", "farm", "ndvi", "forest", "grass"), ("ndvi_gibs", "year_ndvi", "trend_ndvi")),
    (("hot", "heat", "warm", "temperat", "cool"), ("year_lst_day", "trend_lst_day", "lst_gibs")),
    (("water", "lake", "dry", "shore", "flood", "marsh", "lagoon", "wet"), ("before_after", "detail", "year_water")),
    (("ice", "glacier", "snow", "melt"), ("detail", "year_snow_cover", "lst_gibs")),
    (("land", "change", "built", "city", "urban"), ("before_after", "detail", "hillshade")),
)
FALLBACK = ("lst_gibs", "ndvi_gibs", "hillshade")

SYSTEM = f"""You choose map layers for a question about one place, like a GIS expert.
Pick 1 to {MAX_LAYERS} layers ONLY from the list, top layer first. For each, set an opacity
between 0.3 and 1 and write one short plain-English reason ("why") tied to the question.
Pick a "year" from the list of years if one year shows the answer best, else null.
Write a one-sentence "caption" telling the viewer what to look for.
Never write numbers, dates or measurements in "why" or "caption": no data has been read.
Prefer "analysed" layers (trend-tested) over "observed" (measured, not tested) over
"visual_only" (pictures)."""


class SuggestRequest(BaseModel):
    site_id: str
    question: str = Field(min_length=1, max_length=500)
    mode: str = Field(default="overview", pattern="^(overview|drone)$")


@dataclass(frozen=True)
class Suggestion:
    stack: tuple[dict, ...]
    year: int | None
    caption: str
    source: str

    def to_dict(self) -> dict:
        return {"source": self.source, "stack": list(self.stack), "year": self.year, "caption": self.caption}


def _clean_text(raw: object, fallback: str, limit: int = MAX_WHY) -> str:
    if not isinstance(raw, str):
        return fallback
    text = " ".join(raw.split())
    return text if text and len(text) <= limit and not _DIGIT.search(text) else fallback


def _base_id(layers: Mapping[str, dict], mode: str) -> str | None:
    return next((i for i in BASE_IDS[mode] if i in layers), None)


def clean_stack(
    raw: object, layers: Mapping[str, dict], years: Sequence[int], mode: str
) -> tuple[tuple[dict, ...], int | None, str]:
    data = raw if isinstance(raw, dict) else {}
    base = _base_id(layers, mode)
    stack: list[dict] = []
    for item in data.get("stack") or []:
        if not isinstance(item, dict):
            continue
        lid = item.get("id")
        if lid not in layers or lid == base or any(s["id"] == lid for s in stack):
            continue
        try:
            opacity = float(item.get("opacity", 0.8))
        except (TypeError, ValueError):
            opacity = 0.8
        default_why = f"Shows {layers[lid]['title'].lower()}."
        stack.append({"id": lid, "opacity": round(min(1.0, max(0.3, opacity)), 2),
                      "why": _clean_text(item.get("why"), default_why)})
        if len(stack) == MAX_LAYERS - (1 if base else 0):
            break
    if base is not None:
        stack.append({"id": base, "opacity": 1.0, "why": "The real ground underneath, for orientation."})
    year = data.get("year")
    year = year if isinstance(year, int) and year in years else None
    caption = _clean_text(data.get("caption"), DEFAULT_CAPTION, limit=200)
    return tuple(stack), year, caption


def keyword_stack(question: str, layers: Mapping[str, dict]) -> dict:
    q = question.lower()
    picks: list[str] = []
    for words, ids in KEYWORDS:
        if any(w in q for w in words):
            picks += [i for i in ids if i in layers and i not in picks]
    if not picks:
        picks = [i for i in FALLBACK if i in layers]
    return {"stack": [{"id": i, "opacity": 0.8} for i in picks]}


def suggest_layers(question: str, layers_doc: Mapping, mode: str, llm: LLM | None) -> Suggestion:
    layers = {la["id"]: la for la in layers_doc.get("layers", [])}
    years = list(layers_doc.get("timeline", {}).get("years", []))
    if llm is not None:
        listing = "\n".join(
            f"- {la['id']}: {la['title']} [{la['status']}]" for la in layers.values()
        )
        schema = {
            "type": "object",
            "properties": {
                "stack": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"id": {"type": "string", "enum": list(layers)},
                                   "opacity": {"type": "number"}, "why": {"type": "string"}},
                    "required": ["id", "opacity", "why"], "additionalProperties": False}},
                "year": {"anyOf": [{"type": "integer", "enum": years}, {"type": "null"}]} if years else {"type": "null"},
                "caption": {"type": "string"},
            },
            "required": ["stack", "year", "caption"],
            "additionalProperties": False,
        }
        user = f"View: {mode}\nLayers:\n{listing}\nYears: {years}\nQuestion: {question}"
        raw = llm.json(SYSTEM, user, schema)
        if raw is not None:
            stack, year, caption = clean_stack(raw, layers, years, mode)
            if any(s["id"] != _base_id(layers, mode) for s in stack):
                return Suggestion(stack, year, caption, "llm")
        logger.info("layer suggest: LLM answer unusable, using keywords")
    stack, year, caption = clean_stack(keyword_stack(question, layers), layers, years, mode)
    return Suggestion(stack, year, caption, "default")


router = APIRouter(tags=["layers"])


@router.post("/layers/suggest")
def post_suggest(
    body: SuggestRequest, llm: LLM | None = Depends(get_llm), sites_dir: Path = Depends(get_sites_dir)
) -> dict:
    site = load_sites().get(body.site_id)
    if site is None:
        known = ", ".join(s.id for s in load_sites().sites)
        raise HTTPException(404, f"We don't know a site called '{body.site_id}'. Pick one of: {known}.")
    path = sites_dir / site.id / "layers.json"
    if not path.is_file():
        raise HTTPException(404, f"No layers for '{site.id}' yet.")
    doc = json.loads(path.read_text(encoding="utf-8"))
    return suggest_layers(body.question, doc, body.mode, llm).to_dict()
