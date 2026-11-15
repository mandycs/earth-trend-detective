"""Numbers in generated text vs numbers the report allows.

`extract_numbers` finds every figure in prose (digits, signs, percentages, number words,
simple fractions). `allowed_numbers` lists the figures a site report actually contains.
`find_match` accepts a figure only if it is an allowed value, possibly rounded to 1-3
significant digits or 0-2 decimals. Unit conversions (0.84 for 84%) are not accepted.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from app.site_story import round_sig

# Fractions are vaguer than digits: "about half" may stand for 45-55 %.
FRACTION_TOLERANCE_PCT = 5.0


@dataclass(frozen=True)
class FoundNumber:
    text: str
    value: float
    percent: bool
    fraction: bool = False


@dataclass(frozen=True)
class AllowedNumber:
    value: float
    percent: bool
    origin: str


_PCT_SUFFIX = r"(?P<pct>\s*(?:%|percent\b|per\s+cent\b))?"
_DIGITS = re.compile(r"(?P<sign>[−\-–])?(?P<num>\d+(?:,\d{3})*(?:\.\d+)?)" + _PCT_SUFFIX)

_UNITS = {
    "zero": 0, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_ONES = {"one": 1, **{k: v for k, v in _UNITS.items() if v < 10 and v > 0}}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
}
# Bare "one" is skipped: it is mostly a pronoun ("no one", "one of the").
_WORDS = re.compile(
    r"\b(?:(?P<tens>" + "|".join(_TENS) + r")(?:[-\s](?P<ones>" + "|".join(_ONES) + r"))?"
    r"|(?P<unit>" + "|".join(_UNITS) + r"))\b" + _PCT_SUFFIX,
    re.IGNORECASE,
)
_FRACTIONS: Mapping[str, float] = {
    "three quarters": 75.0, "three-quarters": 75.0, "two thirds": 66.7, "two-thirds": 66.7,
    "half": 50.0, "a third": 33.3, "one third": 33.3, "a quarter": 25.0, "one quarter": 25.0,
}
_FRACTION_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(k) for k in sorted(_FRACTIONS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
_STEP_PREFIX = re.compile(r"\bstep\s*$", re.IGNORECASE)


def _digit_numbers(text: str) -> list[tuple[int, FoundNumber]]:
    found = []
    for m in _DIGITS.finditer(text):
        start = m.start("num")
        before = text[start - 1] if start > 0 else ""
        if m.group("sign"):
            sign_pos = m.start("sign")
            sign_before = text[sign_pos - 1] if sign_pos > 0 else ""
            negative = not sign_before.isalnum()  # "2003-2024" is a range, not a sign
            if not negative:
                before = text[sign_pos]
        else:
            negative = False
        if before.isalpha():  # identifiers such as "CO2", "m2"
            continue
        value = float(m.group("num").replace(",", ""))
        if value in (1.0, 2.0, 3.0) and _STEP_PREFIX.search(text[:start]):
            continue  # "Step 1", "step 3"
        text_span = m.group(0).strip() if negative else text[start : m.end()].strip()
        found.append((m.start(), FoundNumber(text_span, -value if negative else value, bool(m.group("pct")))))
    return found


def _word_numbers(text: str) -> list[tuple[int, FoundNumber]]:
    found = []
    fraction_spans = [m.span() for m in _FRACTION_RE.finditer(text)]
    for m in _WORDS.finditer(text):
        if any(lo <= m.start() < hi for lo, hi in fraction_spans):
            continue  # "three" inside "three quarters"
        if m.group("tens"):
            value = _TENS[m.group("tens").lower()] + _ONES.get((m.group("ones") or "").lower(), 0)
        else:
            value = _UNITS[m.group("unit").lower()]
        found.append((m.start(), FoundNumber(m.group(0).strip(), float(value), bool(m.group("pct")))))
    for m in _FRACTION_RE.finditer(text):
        value = _FRACTIONS[m.group(0).lower()]
        found.append((m.start(), FoundNumber(m.group(0), value, percent=True, fraction=True)))
    return found


def extract_numbers(text: str) -> tuple[FoundNumber, ...]:
    """Every figure in `text`, in reading order."""
    found = _digit_numbers(text) + _word_numbers(text)
    return tuple(n for _, n in sorted(found, key=lambda p: p[0]))


def _as_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _report_years(report: Mapping) -> tuple[int, int] | None:
    years = report.get("years")
    if isinstance(years, Sequence) and len(years) == 2:
        return int(years[0]), int(years[1])
    if isinstance(report.get("start"), int) and isinstance(report.get("end"), int):
        return report["start"], report["end"]
    return None


def allowed_numbers(report: Mapping) -> tuple[AllowedNumber, ...]:
    """Every figure a narrative of `report` may quote (plus the climate-share complement)."""
    out: list[AllowedNumber] = []

    def add(value: object, percent: bool, origin: str) -> None:
        number = _as_number(value)
        if number is not None:
            out.append(AllowedNumber(number, percent, origin))

    for row in report.get("variables") or ():
        vid = row.get("id", "?")
        for key in ("sen_slope_per_decade", "ci_low", "ci_high", "years_needed"):
            add(row.get(key), False, f"{vid}.{key}")
        pct = _as_number(row.get("residual_pct_non_climate"))
        if pct is not None:
            add(pct, True, f"{vid}.residual_pct_non_climate")
            add(100.0 - pct, True, f"{vid}.climate_share")
        for i, bound in enumerate(row.get("residual_pct_range") or ()):
            add(bound, True, f"{vid}.residual_pct_range[{i}]")
    years = _report_years(report)
    if years is not None:
        start, end = years
        add(start, False, "start_year")
        add(end, False, "end_year")
        add(end - start, False, "period_years")
        add(end - start + 1, False, "period_years_inclusive")
    for i, figure in enumerate(report.get("figures") or ()):
        add(figure, False, f"figure[{i}]")  # detective: every number a tool returned
    validation = report.get("validation")
    if isinstance(validation, Mapping):
        for key in ("r", "n_months", "elevation_trend_m_per_decade"):
            add(validation.get(key), False, f"validation.{key}")
    return tuple(out)


def _roundings(value: float) -> set[float]:
    """|value| and its 1-3 significant-digit and 0-2 decimal roundings (never a fake 0)."""
    out = {abs(value)}
    for digits in (1, 2, 3):
        out.add(abs(float(round_sig(value, digits))))  # type: ignore[arg-type]
    for decimals in (0, 1, 2):
        rounded = abs(round(value, decimals))
        if rounded != 0 or value == 0:
            out.add(rounded)
    return out


def find_match(number: FoundNumber, allowed: Iterable[AllowedNumber]) -> AllowedNumber | None:
    """The allowed figure `number` stands for, or None if it is invented.

    Percentages only match percentages, plain values only plain values. The sign is
    ignored here ("falling by 6.5 cm" quotes -6.47); direction is checked elsewhere.
    """
    target = abs(number.value)
    for candidate in allowed:
        if candidate.percent != number.percent:
            continue
        if number.fraction:
            if abs(target - abs(candidate.value)) <= FRACTION_TOLERANCE_PCT:
                return candidate
            continue
        if any(math.isclose(target, r, rel_tol=1e-9, abs_tol=1e-9) for r in _roundings(candidate.value)):
            return candidate
    return None
