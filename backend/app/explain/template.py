"""Deterministic narrative from a site report: the fallback when the LLM is off or fails.

Same rule as site_story.headline: every figure comes straight from the report
(rounded for display), every word is fixed text. Follows the 3 story steps.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.site_story import format_number

_DIRECTIONS = frozenset({"up", "down"})


def _trend_rows(report: Mapping) -> list[Mapping]:
    return [r for r in report.get("variables") or () if isinstance(r, Mapping)]


def _has_trend(row: Mapping, verdicts: frozenset[str]) -> bool:
    return (
        row.get("verdict") in verdicts
        and row.get("direction") in _DIRECTIONS
        and row.get("sen_slope_per_decade") is not None
    )


def _focus(rows: Sequence[Mapping]) -> Mapping | None:
    """Top real trend with a non-climate share, else the top real/likely trend (rank order)."""
    with_share = [r for r in rows if _has_trend(r, frozenset({"real"})) and r.get("residual_pct_non_climate") is not None]
    if with_share:
        return with_share[0]
    trends = [r for r in rows if _has_trend(r, frozenset({"real", "likely"}))]
    return trends[0] if trends else None


def _change(row: Mapping) -> str:
    slope = format_number(float(row["sen_slope_per_decade"]))
    return f"{row['label']} is going {row['direction']} ({slope} {row.get('unit', '')} per decade)."


def _reality(row: Mapping) -> str:
    if row.get("verdict") == "real":
        return "This change is real: it is too steady to be just chance."
    return "This change is likely real, but we are not sure yet."


def _unknown_sentence(rows: Sequence[Mapping]) -> str | None:
    for row in rows:
        needed = row.get("years_needed")
        if row.get("verdict") == "unknown" and isinstance(needed, int) and needed > 0:
            return f"For {row['label'].lower()}, we can't tell yet: about {needed} more years of data are needed."
    return None


def _climate(row: Mapping) -> str:
    pct = row.get("residual_pct_non_climate")
    if pct is None:
        return "We can't yet tell how much of this change comes from the climate."
    pct_range = row.get("residual_pct_range")
    if pct_range and round(float(pct_range[0])) != round(float(pct_range[1])):
        lo, hi = (round(float(x)) for x in pct_range)
        share = f"Between {lo}% and {hi}%, depending on the climate model,"
        return f"{share} of the change in {row['label'].lower()} is not explained by climate, which is a lead, not proof."
    return (
        f"About {round(float(pct))}% of the change in {row['label'].lower()} is not explained "
        "by climate, which is a lead, not proof."
    )


def _answer_parts(
    rows: Sequence[Mapping], opening: list[str], focus: Mapping | None, unknown: str | None
) -> list[str]:
    """Sentences for a question: the asked trend first, then the climate split of the
    top impact (a climate variable has no split of its own)."""
    parts = list(opening)
    if focus is None:
        return parts + ([unknown] if unknown else [])
    change = _change(focus)
    parts.append(f"What we can see: {change[0].lower()}{change[1:]}" if opening else change)
    parts.append(_reality(focus))
    if focus.get("residual_pct_non_climate") is not None:
        parts.append(_climate(focus))
        return parts
    impact = next(
        (r for r in rows if r is not focus and _has_trend(r, frozenset({"real"}))
         and r.get("residual_pct_non_climate") is not None),
        None,
    )
    if impact is not None:
        other = _change(impact)
        parts.append(f"Over the same years, {other[0].lower()}{other[1:]}")
        parts.append(_climate(impact))
    return parts


def template_narrative(report: Mapping) -> str:
    """3-5 plain sentences: What's changing? Is it real? Is it the climate?

    With `focus_ids` in the report (the variables a user question is about), the first
    sentence is about them.
    """
    rows = _trend_rows(report)
    asked_ids = list(report.get("focus_ids") or ())
    asked = sorted((r for r in rows if r.get("id") in asked_ids), key=lambda r: asked_ids.index(r["id"]))
    opening: list[str] = []
    focus = None
    if asked:
        focus = next((r for r in asked if _has_trend(r, frozenset({"real", "likely"}))), None)
        if focus is None:
            opening.append(
                f"For {asked[0]['label'].lower()}, we can't tell yet whether it is going up or down here."
            )
    focus = focus or _focus(rows)
    unknown = _unknown_sentence(rows)
    if asked:
        return " ".join(_answer_parts(rows, opening, focus, unknown)[:5])
    if focus is None:
        parts = ["Nothing here is changing in a clear way yet."]
        parts.append(unknown or "The changes we see are still too small to tell apart from chance.")
        return " ".join(parts)
    parts = [_change(focus), _reality(focus), _climate(focus)]
    other = next((r for r in rows if r is not focus and _has_trend(r, frozenset({"real"}))), None)
    if other is not None:
        change = _change(other)
        parts.append(f"Over the same years, {change[0].lower()}{change[1:]}")
    if unknown is not None:
        parts.append(unknown)
    return " ".join(parts[:5])
