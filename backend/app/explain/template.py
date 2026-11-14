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
    return (
        f"About {round(float(pct))}% of the change in {row['label'].lower()} is not explained "
        "by climate, which is a lead, not proof."
    )


def template_narrative(report: Mapping) -> str:
    """3-5 plain sentences: What's changing? Is it real? Is it the climate?"""
    rows = _trend_rows(report)
    focus = _focus(rows)
    unknown = _unknown_sentence(rows)
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
