"""Report JSON -> plain-English narrative, checked by the figure validator.

LLM draft -> validate -> one retry with the error list -> validate -> else template.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass

from app.explain.llm import LLM
from app.explain.prompts import NARRATIVE_SYSTEM, narrative_user
from app.explain.template import template_narrative
from app.explain.validator import Rejection, ValidationResult, validate_narrative

logger = logging.getLogger(__name__)

MAX_LLM_ATTEMPTS = 2  # first draft + one retry


@dataclass(frozen=True)
class NarrativeResult:
    text: str
    source: str  # "llm" | "template"
    validation: ValidationResult
    attempts: tuple[ValidationResult, ...] = ()  # rejected LLM drafts, if any

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "source": self.source,
            "validation": self.validation.to_dict(),
            "rejected_attempts": [a.to_dict() for a in self.attempts],
        }


def _template(report: Mapping, attempts: tuple[ValidationResult, ...]) -> NarrativeResult:
    text = template_narrative(report)
    validation = validate_narrative(text, report)
    if not validation.ok:
        logger.error("template narrative failed validation: %s", [r.kind for r in validation.rejected])
    return NarrativeResult(text, "template", validation, attempts)


def explain_report(report: Mapping, llm: LLM | None) -> NarrativeResult:
    if llm is None:
        return _template(report, ())
    previous: str | None = None
    errors: tuple[Rejection, ...] = ()
    attempts: list[ValidationResult] = []
    for _ in range(MAX_LLM_ATTEMPTS):
        text = llm.text(NARRATIVE_SYSTEM, narrative_user(report, previous, errors))
        if text is None:
            break
        validation = validate_narrative(text, report)
        if validation.ok:
            return NarrativeResult(text, "llm", validation, tuple(attempts))
        logger.info("narrative draft rejected: %s", [r.kind for r in validation.rejected])
        attempts.append(validation)
        previous, errors = text, validation.rejected
    return _template(report, tuple(attempts))
