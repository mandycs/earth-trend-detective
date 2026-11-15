"""What the detective may put on screen in its own words: the checks on model text.

Used by the conclude check (`nodes.check`), and as a light check on the other model text
the user sees: the `thinking` line before a tool call and the note of a board suspect.
Everything here is detective-only; `/explain` keeps `app/explain/validator.py` as it is.

- `cause_problems`: cause claims, never excused by a hedge or a "not" in the clause.
- `screen_problems`: figures not in the report, "proof", cause claims, "this part is human".
- `screen_note` / `screen_thinking`: that check applied to a board note / a thinking line.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from app.detective.report import ledger_report
from app.detective.session import Session
from app.explain.numbers import allowed_numbers, extract_numbers, find_match
from app.explain.vocab import NEGATED_PROOF, PROOF_WORDS

RESIDUAL_WORDING = "not explained by the climate we measured"

# Cause claims, in any clause (a hedge or a "not" elsewhere in the clause does not excuse them).
CAUSE_WORDS = re.compile(
    r"\b(?:"
    r"caus(?:e|es|ed|ing)|because|due to|owing to|thanks to|"
    r"driven by|driv(?:e|es|ing)\b|"
    r"responsib(?:le|ility)\s+for|"
    r"result(?:s|ed|ing)?\s+(?:from|of)|as a result|"
    r"(?:comes?|came|coming)\s+from|"
    r"explain(?:s|ing)?\b|explanation|explained by(?! the climate we measured)|"
    r"blam(?:e|es|ed|ing)|culprits?|"
    r"(?:lead|leads|led|leading)\s+to|"
    r"account(?:s|ed|ing)?\s+for|"
    r"(?<!not )(?<!never )(?<!n't )linked\s+to|"
    r"(?:is|are|was|were|be|been)\s+behind\b(?!\s+(?:the\s+|a\s+)?(?:dam|dams|wall|barrage)\b)|"
    r"attributable\s+to|"
    r"contribut(?:e|es|ed|ing)\s+to"
    r")",
    re.IGNORECASE,
)
# A cause word about the DATA, not the world ("because the record is short") is not a cause claim.
_DATA_SUBJECT = (
    r"(?:records?|series|data(?:\s+cells?)?|dataset|samples?|window|tests?|correction|gaps?|cells?|"
    r"(?:too\s+)?few\s+years|missing\s+(?:years|months))"
)
DATA_CAUSE = re.compile(
    r"\b(?:because(?:\s+of)?|due\s+to|owing\s+to)\s+"
    r"(?:(?:the|this|that|our|its|a|an|one|each)\s+)?"
    r"(?:(?:short|shorter|limited|small|coarse|noisy|patchy|missing|few|too|big|large)\s+)*"
    rf"{_DATA_SUBJECT}\b",
    re.IGNORECASE,
)
# Who may not be the subject of a drain verb ("irrigation is draining the aquifer").
# A single "dam" or "reservoir" is a place ("the reservoir behind the dam dried up"), not an actor.
ACTORS = (
    "irrigation", "irrigating", "farm", "farms", "farmers", "farming", "agriculture", "crops", "orchards",
    "people", "humans", "human", "wells", "pumping", "pumps", "cities", "city", "towns", "dams",
    "mines", "mining", "industry", "tourism", "tourists",
)
# Words of a suspect's label that never make it an actor: places and plain words ("water use").
_NOT_ACTORS = frozenset({
    "dam", "reservoir", "reservoirs", "lake", "lakes", "river", "rivers", "basin", "aquifer", "sea", "coast",
    "water", "use", "uses", "used", "usage", "less", "more", "the", "and", "for", "from", "with", "change",
    "changes", "level", "levels", "area", "land", "cover", "local", "other", "factor", "factors", "not",
    "modelled", "modeled", "releases", "release",
})
_DRAIN_VERBS = (
    r"(?:drain(?:s|ed|ing)?|deplet(?:e|es|ed|ing)|empt(?:y|ies|ied|ying)|dr(?:y|ies|ied|ying)\s+(?:up|out)|"
    r"suck(?:s|ed|ing)?|us(?:e|es|ed|ing)\s+up|draw(?:s|ing)?\s+down|pump(?:s|ed|ing)?\s+(?:out|away))"
)
_WORD = re.compile(r"[a-z]+")
HUMAN_CLAIM = re.compile(
    r"\b(?:is|are|was|were)\s+(?:(?:mostly|largely|partly|all|clearly)\s+)?human\b"
    r"|\b(?:hu)?man[- ]made\b|\bhuman[- ]caused\b",
    re.IGNORECASE,
)
LEAD_NOT_PROOF = re.compile(r"\ba lead,? not (?:a )?proof\b", re.IGNORECASE)
NO_CHANGE_CLAIM = re.compile(
    r"\bnothing\b[^.]{0,30}\bchanging\b|\bno (?:clear |real )?change\b|\b(?:isn'?t|aren'?t|is not|are not) changing\b",
    re.IGNORECASE,
)


def _actors(suspects: Iterable[Mapping]) -> tuple[str, ...]:
    words = {w for s in suspects for k in ("id", "label") for w in _WORD.findall(str(s.get(k) or "").lower())}
    return tuple(sorted(set(ACTORS) | {w for w in words if len(w) > 2 and w not in _NOT_ACTORS}))


def cause_problems(text: str, suspects: Iterable[Mapping] = ()) -> list[str]:
    """One plain rejection per cause claim in `text` (suspects' names count as actors).
    A cause word about the data ("because the record is short") is not a claim about the world."""
    about_world = DATA_CAUSE.sub(" ", text)
    out = [
        f"'{hit.group(0)}' claims a cause; say what changed and what the tests found, never why"
        for hit in CAUSE_WORDS.finditer(about_world)
    ]
    actors = "|".join(re.escape(a) for a in _actors(suspects))
    drain = re.compile(rf"\b(?:{actors})\b(?:\s+\w+){{0,2}}?\s+{_DRAIN_VERBS}\b", re.IGNORECASE)
    out += [f"'{hit.group(0)}' claims a cause; never say a suspect drains or uses up the water" for hit in drain.finditer(text)]
    return out


def _number_problems(text: str, report: Mapping) -> list[str]:
    allowed = allowed_numbers(report)
    return [f"'{n.text}' is not a number any tool returned" for n in extract_numbers(text) if find_match(n, allowed) is None]


def screen_problems(text: str, report: Mapping, suspects: Iterable[Mapping] = ()) -> list[str]:
    """Why `text` may not go on screen as it is (empty list: it may)."""
    problems = _number_problems(text, report)
    for hit in PROOF_WORDS.finditer(NEGATED_PROOF.sub(" ", text)):
        problems.append(f"'{hit.group(0)}': a clue is never proof")
    problems += cause_problems(text, suspects)
    hit = HUMAN_CLAIM.search(text)
    if hit:
        problems.append(f"'{hit.group(0)}': never say a part is human; say '{RESIDUAL_WORDING}'")
    return problems


def _suspect_rows(session: Session) -> list[dict]:
    return [{"id": s.id, "label": s.label} for s in session.board.values()]


def screen_note(note: str | None, session: Session) -> str:
    """The board note as it may be shown: the note itself, or "" when it fails the check."""
    text = (note or "").strip()
    if text and screen_problems(text, ledger_report(session), _suspect_rows(session)):
        return ""
    return text


def screen_thinking(text: str, tools: Iterable[str], session: Session) -> str:
    """The thinking line as it may be shown: the line itself, or a neutral "Next: <tool>." line."""
    text = (text or "").strip()
    if text and screen_problems(text, ledger_report(session), _suspect_rows(session)):
        names = [t for t in dict.fromkeys(str(n) for n in tools) if t]
        return f"Next: {', '.join(names)}." if names else ""
    return text


def answer_problems(text: str, report: Mapping, suspects: Iterable[Mapping] = ()) -> list[str]:
    """The detective's own rules for the final answer, on top of the shared validator."""
    problems = cause_problems(text, suspects)
    hit = HUMAN_CLAIM.search(text)
    if hit:
        problems.append(f"'{hit.group(0)}': never say a part is human; say '{RESIDUAL_WORDING}'")
    if LEAD_NOT_PROOF.search(text):
        problems.append(f"say '{RESIDUAL_WORDING} — a clue, not proof', not 'a lead, not proof'")
    has_share = any(row.get("residual_pct_non_climate") is not None for row in report.get("variables") or ())
    if has_share and RESIDUAL_WORDING not in text.lower():
        problems.append(f"a share not explained by climate must be said as '{RESIDUAL_WORDING} — a clue, not proof'")
    if not report.get("n_tests"):
        hit = NO_CHANGE_CLAIM.search(text)
        if hit:
            problems.append(f"'{hit.group(0)}': nothing was measured, so say that nothing could be measured here, not that nothing changes")
    return problems
