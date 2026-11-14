"""The closed menu of investigation steps and the rules a plan must follow.

The LLM may only pick step ids from MENU; `clean_plan` enforces order, dependencies,
length and wording, so whatever comes back is always a plan the runner can execute.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    id: str
    title: str  # shown in the UI while the step runs
    does: str  # one plain sentence: what it looks at (also the default "why")
    seconds: int  # rough cost, for the UI and the planner
    needs: tuple[str, ...] = ()  # steps that must run before


MENU: Mapping[str, Step] = {
    s.id: s
    for s in (
        Step(
            "land_cover",
            "What covers the ground",
            "Reads NASA MODIS land cover around the point at the start and end of the period.",
            2,
        ),
        Step(
            "climate",
            "Climate trends",
            "Checks NASA POWER temperature, rain and sunshine over the study period for a real trend.",
            5,
        ),
        Step(
            "water_storage",
            "Water stored underground and on the surface",
            "Checks the GRACE satellites' total water storage and how much of its trend climate explains.",
            4,
            needs=("climate",),
        ),
        Step(
            "then_and_now",
            "Then and now",
            "Finds clear MODIS satellite pictures of the same season at the start and end of the period.",
            6,
        ),
        Step(
            "soil_and_runoff",
            "Soil moisture and runoff",
            "Checks the NASA GLDAS land model for soil moisture and runoff trends (slow).",
            90,
            needs=("climate",),
        ),
    )
}
FINAL_STEP = "explain"
FINAL = Step(FINAL_STEP, "What it means", "Writes a short plain-English summary, checked figure by figure.", 5)
MIN_STEPS = 2
MAX_STEPS = 5  # before the final explain step
MAX_WHY_CHARS = 140
_DIGIT = re.compile(r"\d")

# Default plans by kind of place (first matching tag wins), used when the LLM is off or fails.
DEFAULT_PLANS: Sequence[tuple[str, tuple[str, ...]]] = (
    ("water_body", ("land_cover", "then_and_now", "climate", "water_storage")),
    ("glacier", ("land_cover", "then_and_now", "climate", "water_storage")),
    ("wetland", ("land_cover", "then_and_now", "climate", "water_storage")),
    ("agriculture", ("land_cover", "climate", "water_storage", "then_and_now")),
    ("urban", ("land_cover", "then_and_now", "climate")),
    ("desert", ("land_cover", "climate", "water_storage", "then_and_now")),
)
FALLBACK_PLAN = ("land_cover", "climate", "water_storage", "then_and_now")


@dataclass(frozen=True)
class PlannedStep:
    id: str
    why: str

    @property
    def step(self) -> Step:
        return FINAL if self.id == FINAL_STEP else MENU[self.id]

    def to_dict(self) -> dict:
        s = self.step
        return {"id": self.id, "title": s.title, "why": self.why, "seconds": s.seconds}


def default_plan(tags: Iterable[str]) -> tuple[str, ...]:
    tags = set(tags)
    return next((plan for tag, plan in DEFAULT_PLANS if tag in tags), FALLBACK_PLAN)


def _clean_why(raw: object, step: Step) -> str:
    """The LLM's reason if it is short plain text with no figures; else the menu sentence.

    No digits at all: every figure on screen must come from the data, never from the plan.
    """
    if not isinstance(raw, str):
        return step.does
    text = " ".join(raw.split())
    if not text or len(text) > MAX_WHY_CHARS or _DIGIT.search(text):
        return step.does
    return text


def clean_plan(raw: object, tags: Iterable[str]) -> tuple[PlannedStep, ...]:
    """Validated plan: menu ids only, no repeats, dependencies first, 2-5 steps, then explain.

    Too short or unusable -> the default plan for this kind of place.
    """
    items = raw if isinstance(raw, list) else []
    picked: dict[str, object] = {}
    for item in items:
        sid = item.get("id") if isinstance(item, dict) else None
        if isinstance(sid, str) and sid in MENU and sid not in picked:
            picked[sid] = item.get("why")
    if len(picked) < MIN_STEPS:
        picked = {sid: None for sid in default_plan(tags)}

    ordered: list[str] = []

    def add(sid: str) -> None:
        for dep in MENU[sid].needs:
            if dep not in ordered:
                add(dep)
        if sid not in ordered:
            ordered.append(sid)

    for sid in picked:
        add(sid)
    # Dependencies may push the plan past the limit: keep the first MAX_STEPS that still
    # have their dependencies inside the cut.
    kept: list[str] = []
    for sid in ordered:
        if len(kept) < MAX_STEPS and all(d in kept for d in MENU[sid].needs):
            kept.append(sid)
    steps = tuple(PlannedStep(sid, _clean_why(picked.get(sid), MENU[sid])) for sid in kept)
    return (*steps, PlannedStep(FINAL_STEP, FINAL.does))


def plan_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "enum": list(MENU)},
                        "why": {"type": "string"},
                    },
                    "required": ["id", "why"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["steps"],
        "additionalProperties": False,
    }


def menu_text() -> str:
    lines = []
    for s in MENU.values():
        needs = f" Needs: {', '.join(s.needs)}." if s.needs else ""
        lines.append(f"- {s.id}: {s.does} About {s.seconds} s.{needs}")
    return "\n".join(lines)
