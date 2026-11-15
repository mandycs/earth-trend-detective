"""Everyday equivalents of tool figures: exact arithmetic, done by code, never by the model.

Each tool result that has one carries an `everyday` block. The narrator may quote these
values; the checker (`wording.everyday_rejections`) accepts a litres figure, an "N in ten"
share or "most of it" only when it matches a value found in one of these blocks.

- water (cm, kg/m², mm of water): 1 cm on one square metre = 10 litres; 1 kg/m² = 1 litre.
  Per decade (the slope) and over the period tested (slope x years / 10, the fitted line).
- temperature (°C): the change over the period tested (slope x years / 10).
- greenness (NDVI): a word only ("greener" / "browner"), no new figure.
- land cover and the climate split: a percent as "about N in ten".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

# Litres of water on one square metre per unit of the variable.
LITRES_PER_M2 = {"grace_tws": 10.0, "soil_moisture": 1.0}
TEMPERATURE = frozenset({"t2m", "t2m_upstream", "lst_day", "lst_gibs", "sst"})
GREENNESS = frozenset({"ndvi", "ndvi_gibs"})
# "Most of it" only when even the low end of the model range is above this share.
MOST_PCT = 55.0


def _nice(x: float) -> float:
    """Whole numbers from ten up, one decimal below."""
    return float(round(x)) if abs(x) >= 10 else round(x, 1)


def _span(years: Any) -> int | None:
    if isinstance(years, Sequence) and not isinstance(years, str) and len(years) == 2:
        span = int(years[1]) - int(years[0])
        return span if span > 0 else None
    return None


def for_trend(var_id: str, units: str, slope: float | None, years: Any) -> dict | None:
    """The everyday block of one trend (None: nothing honest to add)."""
    if slope is None or slope == 0:
        return None
    if var_id in GREENNESS:
        return {"way": "greener" if slope > 0 else "browner"}
    span = _span(years)
    if span is None:
        return None
    if var_id in LITRES_PER_M2:
        litres = slope * LITRES_PER_M2[var_id]
        return {
            "litres_per_m2_per_decade": _nice(litres),
            "litres_per_m2_over_period": _nice(litres * span / 10),
            "over_years": span,
            "way": "more" if slope > 0 else "less",
        }
    if var_id in TEMPERATURE and "°C" in (units or ""):
        return {
            "change_over_period_c": round(slope * span / 10, 1),
            "over_years": span,
            "way": "warmer" if slope > 0 else "cooler",
        }
    return None


def with_trend_everyday(result: Mapping) -> dict:
    """A copy of a trend_test result with its `everyday` block (unchanged when there is none)."""
    out = dict(result)
    block = for_trend(
        str(result.get("var_id") or ""),
        str(result.get("unit") or ""),
        result.get("slope_per_decade"),
        result.get("years"),
    )
    if block:
        out["everyday"] = block
    return out


def _in_ten(pct: Any) -> int | None:
    if not isinstance(pct, (int, float)) or isinstance(pct, bool):
        return None
    n = round(float(pct) / 10)
    return n if 1 <= n <= 10 else None


SMALL_MOVE_POINTS = 10.0  # under this, rounding to tenths can turn a small move into "9 in ten -> 10 in ten"


def _small_move(row: Mapping) -> bool:
    before, after = row.get("before_pct"), row.get("after_pct")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (before, after)):
        return False
    return abs(float(after) - float(before)) < SMALL_MOVE_POINTS


def with_land_cover_everyday(row: Mapping) -> dict:
    """A copy of one land cover change row with its shares as "N in ten".

    A move under ten points keeps only today's share and says the move was small, so the
    rounding never reads as a jump.
    """
    small = _small_move(row)
    block: dict[str, Any] = {}
    for key, name in (("before_pct", "in_ten_before"), ("after_pct", "in_ten_after")):
        if small and name == "in_ten_before":
            continue
        n = _in_ten(row.get(key))
        if n is not None:
            block[name] = n
    out = dict(row)
    if block:
        out["everyday"] = {**block, "out_of": "ten", "class": str(row.get("class") or "")}
        if small:
            out["everyday"]["move"] = "small"
    return out


def for_residual(pct: float | None, pct_range: Sequence[float] | None) -> dict | None:
    """The share not explained by the climate as "N in ten", and "most" when every model says so."""
    n = _in_ten(pct)
    if n is None:
        return None
    block: dict[str, Any] = {"in_ten_not_explained": n}
    low = min(pct_range) if pct_range else pct
    if low is not None and low > MOST_PCT:
        block["share_word"] = "most"
    return {**block, "out_of": "ten"}


def blocks(value: Any) -> list[dict]:
    """Every `everyday` block inside a tool result (nested rows included)."""
    out: list[dict] = []
    if isinstance(value, Mapping):
        for k, v in value.items():
            if k == "everyday" and isinstance(v, Mapping):
                out.append(dict(v))
            else:
                out += blocks(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            out += blocks(v)
    return out
