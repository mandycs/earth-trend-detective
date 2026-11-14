"""Story-mode text pieces built only from numbers: badges, headline, rounding.

No free text is invented here. The narrative is written by a human (left null).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

BADGE_UNKNOWN = "? Can't tell yet"
_ARROWS: Mapping[str, str] = {"up": "↑", "down": "↓"}
_VERDICT_WORD: Mapping[str, str] = {"real": "Real", "likely": "Likely"}
MINUS = "−"  # U+2212, typographic minus for display text


def badge(verdict: str, direction: str) -> str:
    """UX badge: icon + text, never colour only (PLAN.md §5)."""
    word = _VERDICT_WORD.get(verdict)
    arrow = _ARROWS.get(direction)
    if word is None or arrow is None:
        return BADGE_UNKNOWN
    return f"{arrow} {word}"


def round_sig(value: object, digits: int = 3) -> object:
    """Floats to `digits` significant figures, NaN/inf -> None; other values unchanged."""
    if isinstance(value, bool) or not isinstance(value, float):
        return value
    if not math.isfinite(value):
        return None
    if value == 0:
        return 0.0
    decimals = digits - 1 - math.floor(math.log10(abs(value)))
    return round(value, decimals)


def round_floats(obj: object, digits: int = 3) -> object:
    """Deep copy of dicts/lists with every float rounded by `round_sig`."""
    if isinstance(obj, Mapping):
        return {k: round_floats(v, digits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [round_floats(v, digits) for v in obj]
    return round_sig(obj, digits)


def format_number(value: float, digits: int = 2) -> str:
    """`digits` significant figures, plain notation, typographic minus, no trailing zeros noise."""
    rounded = round_sig(float(value), digits)
    if rounded == 0:
        return "0"
    decimals = max(0, digits - 1 - math.floor(math.log10(abs(rounded))))
    text = f"{abs(rounded):.{decimals}f}"
    return f"{MINUS}{text}" if rounded < 0 else text


def headline(rows: Sequence[Mapping], impact_ids: frozenset[str]) -> str | None:
    """Template sentence for the top-ranked real impact with a non-climate share, else None.

    `rows` must be in sweep rank order.
    """
    for row in rows:
        pct = row.get("residual_pct_non_climate")
        slope = row.get("sen_slope_per_decade")
        if (
            row.get("id") not in impact_ids
            or row.get("verdict") != "real"
            or row.get("direction") not in _ARROWS
            or pct is None
            or slope is None
        ):
            continue
        return (
            f"{row['label']} is going {row['direction']} for real "
            f"({format_number(slope)} {row['unit']} per decade). "
            f"About {round(pct)}% of that change is not explained by climate."
        )
    return None
