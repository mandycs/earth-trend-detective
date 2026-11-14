"""The investigation's answer block: one headline, one key figure, one note.

Built in code from the report, never by the LLM, so the screen can lead with it
before the narrator's paragraph. Every figure comes straight from the report,
rounded for display; every word is fixed text.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.site_story import format_number

_DIRECTIONS = frozenset({"up", "down"})
_TRENDS = frozenset({"real", "likely"})
CLUE_NOTE = "A clue, not proof."


def _rows(report: Mapping) -> list[Mapping]:
    return [r for r in report.get("variables") or () if isinstance(r, Mapping) and r.get("label")]


def _has_trend(row: Mapping) -> bool:
    return (
        row.get("verdict") in _TRENDS
        and row.get("direction") in _DIRECTIONS
        and row.get("sen_slope_per_decade") is not None
    )


def _main_row(rows: Sequence[Mapping], focus_ids: Sequence[str]) -> Mapping | None:
    """First variable the question is about; without one, the top real/likely trend."""
    by_id = {r.get("id"): r for r in rows}
    focused = [by_id[i] for i in focus_ids if i in by_id]
    if focused:
        return focused[0]
    trends = [r for r in rows if _has_trend(r)]
    if trends:
        return trends[0]
    return rows[0] if rows else None


def _headline(row: Mapping) -> str:
    label = str(row["label"])
    if not _has_trend(row):
        return f"We can't tell yet whether {label.lower()} is changing."
    direction = row["direction"]
    if row["verdict"] == "real":
        return f"{label} is going {direction}, for real."
    return f"{label} is probably going {direction}, but we are not sure yet."


def _share(row: Mapping) -> tuple[str, str] | None:
    """Climate split of a real trend, as (figure, label); None when there is none."""
    pct = row.get("residual_pct_non_climate")
    if row.get("verdict") != "real" or pct is None:
        return None
    label = f"of the change in {str(row['label']).lower()} is not explained by climate"
    pct_range = row.get("residual_pct_range")
    if pct_range and len(pct_range) == 2:
        low, high = (round(float(x)) for x in pct_range)
        if low != high:
            return f"{low}–{high}%", f"{label}, depending on the climate model"
    return f"{round(float(pct))}%", label


def _slope(row: Mapping, years: Sequence) -> tuple[str, str]:
    value = float(row["sen_slope_per_decade"])
    sign = "+" if value > 0 else ""
    unit = f" {row['unit']}" if row.get("unit") else ""
    figure = f"{sign}{format_number(value)}{unit} per decade"
    span = f", {years[0]}–{years[1]}" if len(years) == 2 and all(years) else ""
    return figure, f"{row['label']}{span}"


def build_answer(report: Mapping) -> dict | None:
    """Answer block for the investigation, or None when nothing was measured."""
    rows = _rows(report)
    row = _main_row(rows, report.get("focus_ids") or ())
    if row is None:
        return None
    trend = _has_trend(row)
    figure = figure_label = note = None
    share = _share(row) if trend else None
    if share is not None:
        (figure, figure_label), note = share, CLUE_NOTE
    elif trend:
        years = report.get("years") or [report.get("start"), report.get("end")]
        figure, figure_label = _slope(row, years)
    return {
        "headline": _headline(row),
        "verdict": row.get("verdict") if trend else "unknown",
        "direction": row.get("direction") if trend else None,
        "figure": figure,
        "figure_label": figure_label,
        "note": note,
    }
