"""The answer in everyday words, written by code: the template's sentences and the next questions.

- `change_sentence`: the trend that answers the question, with its everyday equivalent (litres of
  water on each square metre, degrees over the years tested) when a tool worked one out.
- `share_sentence`: the part the weather we measured does not explain, as "N in 10 parts" when a
  tool worked that out, always "a clue, not proof".
- `next_questions`: two or three short plain questions about what was not tested yet. Fixed
  words plus catalog labels only, so they carry no figure and no cause claim (both are checked).

Every figure here is a report value (rounded for display); every word is fixed text.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence

from app.explain.numbers import extract_numbers
from app.site_story import format_number

DIRECTIONS = frozenset({"up", "down"})
SHARE_TAIL = "not explained by the weather we measured — that's a clue, not proof"
MAX_NEXT = 3
MAX_NEXT_CHARS = 70
IMPACTS_WITH_SPLIT = frozenset({"grace_tws", "soil_moisture", "ndvi", "lst_day", "et", "snow_cover", "runoff"})


def _num(x: float) -> str:
    return format_number(abs(float(x))).replace("−", "")


def _has_trend(row: Mapping, verdicts: Iterable[str]) -> bool:
    return (
        row.get("verdict") in set(verdicts)
        and row.get("direction") in DIRECTIONS
        and row.get("sen_slope_per_decade") is not None
    )


def focus_row(report: Mapping) -> Mapping | None:
    """The real trend with a climate split, else the first real trend, else the first likely one."""
    rows = [r for r in report.get("variables") or () if isinstance(r, Mapping)]
    real = [r for r in rows if _has_trend(r, ("real",))]
    with_share = [r for r in real if r.get("residual_pct_non_climate") is not None]
    likely = [r for r in rows if _has_trend(r, ("likely",))]
    return (with_share or real or likely or [None])[0]


def _equivalent(row: Mapping) -> str:
    block = row.get("everyday") or {}
    litres = block.get("litres_per_m2_per_decade")
    if isinstance(litres, (int, float)) and litres:
        return f", which is about {_num(litres)} litres of water on each square metre every decade"
    change = block.get("change_over_period_c")
    years = block.get("over_years")
    if isinstance(change, (int, float)) and change and isinstance(years, int):
        return f", about {_num(change)} °C {block.get('way')} over {years} years"
    return ""


def _short_label(label: str) -> str:
    return re.sub(r"\s*\(.*?\)\s*", " ", label).strip()


def change_sentence(row: Mapping) -> str:
    label = _short_label(str(row.get("label") or "It"))
    unit = str(row.get("unit") or "").strip()
    amount = f"about {_num(row['sen_slope_per_decade'])} {unit} per decade".replace("  ", " ")
    if row.get("verdict") == "real":
        return f"{label} here is going {row['direction']}: {amount}{_equivalent(row)}."
    return f"{label} here is probably going {row['direction']} ({amount}), but we are not sure yet."


def share_sentence(row: Mapping) -> str | None:
    pct = row.get("residual_pct_non_climate")
    if pct is None:
        return None
    block = row.get("residual_everyday") or {}
    n = block.get("in_ten_not_explained")
    if block.get("share_word") == "most" and isinstance(n, int):
        return (
            f"The weather we measured doesn't explain most of it, about {n} in 10 parts of that change "
            "— that's a clue, not proof."
        )
    if isinstance(n, int):
        return f"About {n} in 10 parts of that change are {SHARE_TAIL}."
    return f"About {round(float(pct))}% of that change is {SHARE_TAIL}."


def reality_sentence(row: Mapping) -> str:
    if row.get("verdict") == "real":
        return "It is too steady to be just chance."
    return "It could still be chance; more years of data would tell."


# --------------------------------------------------------------------------- next questions


def _clean(question: str, cause_check) -> bool:
    return (
        bool(question)
        and len(question) <= MAX_NEXT_CHARS
        and question.endswith("?")
        and not extract_numbers(question)
        and not cause_check(question)
    )


def _recent_tested(row: Mapping, report: Mapping) -> bool:
    if row.get("other_periods"):
        return True
    return any(c.get("var_id") == row.get("id") for c in report.get("comparisons") or ())


def next_questions(
    report: Mapping, board: Sequence[Mapping], tested_ids: Iterable[str], available: Sequence[Mapping], cause_check
) -> list[str]:
    """Two or three plain questions about what this run did not test yet (none with a figure)."""
    out: list[str] = []
    focus = focus_row(report)
    rows = [r for r in report.get("variables") or () if isinstance(r, Mapping)]
    if focus is not None and not _recent_tested(focus, report):
        out.append(f"Is it still going {focus['direction']} in recent years?")
    if focus is not None and focus.get("residual_pct_non_climate") is None and focus.get("id") in IMPACTS_WITH_SPLIT:
        out.append("What happens if we take the weather out of it?")
    for s in board:
        if s.get("status") in ("trend_only", "open", "hint"):
            name = str(s.get("label") or "").strip()
            if name:
                out.append(f"Can we test the link with {name[0].lower() + name[1:]}?")
                break
    tested = set(tested_ids)
    for var in available:
        if var.get("id") not in tested and var.get("available") is not False:
            out.append(f"What about {_short_label(str(var.get('label') or '')).lower()} here?")
    if rows and not report.get("comparisons"):
        out.append("Is a place nearby changing the same way?")
    clean = [q for q in dict.fromkeys(out) if _clean(q, cause_check)]
    return clean[:MAX_NEXT]
