"""Figure validator: a narrative may only say what the report says.

Rules (each failure is one `Rejection`):
- number:    every figure must be an allowed report number (rounding ok, conversions not).
- direction: a clause about a real/likely trend must not use words of the opposite direction.
- certainty: a clause about a non-"real" trend must not sound certain.
- proof:     "proves"/"proof" anywhere, unless negated ("a lead, not proof").
- causal:    unhedged cause claims ("is caused by").
- jargon:    statistics words (Mann-Kendall, FDR, p-value, ...).
- lead:      if the report has a non-climate share, the text must say "a lead, not proof".
- length:    empty text or more than MAX_SENTENCES sentences.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.explain.numbers import FoundNumber, allowed_numbers, extract_numbers, find_match
from app.explain.vocab import (
    CAUSAL_WORDS,
    CERTAINTY_WORDS,
    DOWN_WORDS,
    HEDGE_WORDS,
    JARGON_WORDS,
    LEAD_PHRASE,
    NEGATED_PROOF,
    PROOF_WORDS,
    UP_WORDS,
    VARIABLE_ALIASES,
)

MAX_SENTENCES = 5
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")
_CLAUSE_SPLIT = re.compile(r"[;:,()—]|\s–\s|\b(?:while|but|whereas|although|though|and|yet)\b", re.IGNORECASE)
_PRONOUN_START = re.compile(r"^\s*(?:it|this|that|the change|the drop|the rise|its)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Rejection:
    kind: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "detail": self.detail}


@dataclass(frozen=True)
class ValidationResult:
    checked_numbers: tuple[str, ...]
    rejected: tuple[Rejection, ...]

    @property
    def ok(self) -> bool:
        return not self.rejected

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "checked_numbers": list(self.checked_numbers),
            "rejected": [r.to_dict() for r in self.rejected],
        }


@dataclass(frozen=True)
class _Trend:
    id: str
    verdict: str
    direction: str
    patterns: tuple[re.Pattern[str], ...]


def _trends(report: Mapping) -> tuple[_Trend, ...]:
    out = []
    for row in report.get("variables") or ():
        vid = str(row.get("id", ""))
        names = {str(row.get("label", "")).lower(), *VARIABLE_ALIASES.get(vid, ())} - {""}
        patterns = tuple(re.compile(r"\b" + re.escape(n), re.IGNORECASE) for n in names)
        out.append(_Trend(vid, str(row.get("verdict", "")), str(row.get("direction", "")), patterns))
    return tuple(out)


def _mentioned(clause: str, trends: Sequence[_Trend]) -> list[_Trend]:
    return [t for t in trends if any(p.search(clause) for p in t.patterns)]


def _check_numbers(text: str, report: Mapping) -> tuple[list[str], list[Rejection]]:
    allowed = allowed_numbers(report)
    checked, rejected = [], []
    for number in extract_numbers(text):
        checked.append(number.text)
        if find_match(number, allowed) is None:
            rejected.append(Rejection("number", f"'{number.text}' is not a number in the report"))
    return checked, rejected


def _check_clause(clause: str, subject: _Trend) -> list[Rejection]:
    rejected = []
    snippet = clause.strip()
    if subject.verdict in ("real", "likely"):
        wrong = DOWN_WORDS if subject.direction == "up" else UP_WORDS if subject.direction == "down" else None
        hit = wrong.search(clause) if wrong is not None else None
        if hit:
            rejected.append(
                Rejection("direction", f"'{hit.group(0)}' contradicts {subject.id} going {subject.direction}: '{snippet}'")
            )
    if subject.verdict != "real":
        hit = CERTAINTY_WORDS.search(clause)
        if hit:
            rejected.append(
                Rejection("certainty", f"'{hit.group(0)}' is too sure for {subject.id} ({subject.verdict}): '{snippet}'")
            )
    return rejected


def _check_trends(text: str, report: Mapping) -> list[Rejection]:
    trends = _trends(report)
    rejected: list[Rejection] = []
    subject: _Trend | None = None
    for sentence in _SENTENCE_SPLIT.split(text):
        if not _PRONOUN_START.match(sentence):
            subject = None
        for clause in _CLAUSE_SPLIT.split(sentence):
            if not clause or not clause.strip():
                continue
            mentioned = _mentioned(clause, trends)
            if len(mentioned) == 1:
                subject = mentioned[0]
            elif len(mentioned) > 1:
                subject = None  # ambiguous clause: no direction check
                continue
            if subject is not None:
                rejected.extend(_check_clause(clause, subject))
    return rejected


def _check_language(text: str, report: Mapping) -> list[Rejection]:
    rejected = []
    without_negated = NEGATED_PROOF.sub(" ", text)
    for hit in PROOF_WORDS.finditer(without_negated):
        rejected.append(Rejection("proof", f"'{hit.group(0)}': the climate split is a lead, never proof"))
    clauses = [c for s in _SENTENCE_SPLIT.split(text) for c in _CLAUSE_SPLIT.split(s)]
    for clause in clauses:
        hit = CAUSAL_WORDS.search(clause or "")
        if hit and not HEDGE_WORDS.search(clause):
            rejected.append(Rejection("causal", f"'{hit.group(0)}' claims a cause: '{clause.strip()}'"))
    for hit in JARGON_WORDS.finditer(text):
        rejected.append(Rejection("jargon", f"'{hit.group(0)}' is jargon, say it in plain words"))
    has_share = any(
        row.get("residual_pct_non_climate") is not None for row in report.get("variables") or ()
    )
    if has_share and not LEAD_PHRASE.search(text):
        rejected.append(Rejection("lead", "must say the climate split is 'a lead, not proof'"))
    return rejected


def validate_narrative(text: str, report: Mapping) -> ValidationResult:
    """Check `text` against `report`; `ok` only if nothing is rejected."""
    if not text or not text.strip():
        return ValidationResult((), (Rejection("length", "the text is empty"),))
    checked, rejected = _check_numbers(text, report)
    rejected += _check_trends(text, report)
    rejected += _check_language(text, report)
    sentences = [s for s in _SENTENCE_SPLIT.split(text.strip()) if s.strip()]
    if len(sentences) > MAX_SENTENCES:
        rejected.append(Rejection("length", f"{len(sentences)} sentences, keep it to 3-5"))
    return ValidationResult(tuple(checked), tuple(rejected))


__all__ = ["FoundNumber", "Rejection", "ValidationResult", "validate_narrative"]
