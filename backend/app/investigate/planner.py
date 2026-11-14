"""Question + kind of place -> investigation plan (LLM picks from the closed menu)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from app.explain.llm import LLM
from app.investigate.menu import MAX_STEPS, MIN_STEPS, PlannedStep, clean_plan, menu_text, plan_schema

logger = logging.getLogger(__name__)

PLAN_SYSTEM = f"""You plan a short investigation of one place on Earth with NASA data.
Pick {MIN_STEPS} to {MAX_STEPS} steps ONLY from the menu, in the order that best answers the user's question
for this kind of place. For each step, write one short plain-English reason ("why") tied to the question.
Never write numbers, dates, years or measurements in a reason: no data has been read yet.
A summary step is always added at the end; do not add it yourself.

Menu:
{menu_text()}"""


@dataclass(frozen=True)
class Plan:
    steps: tuple[PlannedStep, ...]
    source: str  # "llm" | "default"

    def to_dict(self) -> dict:
        return {"source": self.source, "steps": [s.to_dict() for s in self.steps]}


def plan_user(question: str, place: str, tags: Sequence[str]) -> str:
    kind = ", ".join(tags) if tags else "unknown"
    return f"Place: {place}\nKind of place (from NASA land cover): {kind}\nQuestion: {question}"


def make_plan(question: str, place: str, tags: Sequence[str], llm: LLM | None) -> Plan:
    if llm is not None:
        raw = llm.json(PLAN_SYSTEM, plan_user(question, place, tags), plan_schema())
        if raw is not None and isinstance(raw.get("steps"), list):
            ids = [s.get("id") for s in raw["steps"] if isinstance(s, dict)]
            steps = clean_plan(raw["steps"], tags)
            # clean_plan falls back to the default plan when fewer than MIN_STEPS survive.
            usable = len({i for i in ids if i in {s.id for s in steps}}) >= MIN_STEPS
            if usable:
                return Plan(steps, "llm")
        logger.info("planner: LLM plan unusable, using default")
    return Plan(clean_plan([], tags), "default")
