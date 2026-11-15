"""Heat stress (NOAA Coral Reef Watch degree heating weeks) at the five reefs, as a counted record.

DHW is not a trend: no slope, no p, outside the FDR. The yearly maximum of the daily value
(January to June, the southern warm season) is counted against the NOAA Coral Reef Watch
thresholds of 4 and 8 °C-weeks, in the two halves of the study period. A reef-year whose
fetch failed or had no valid day is listed as missing, never counted as "below 4".

Fetching reuses `erddap` (one request per year, sequential, cached for past years, retries).
It is heat stress, not bleaching or coral death.
"""

from __future__ import annotations

import calendar
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.extractors import erddap
from app.reef.points import ReefPoint

DHW_BASE = "https://coastwatch.noaa.gov/erddap/griddap"
DHW_DATASET = "noaacrwdhwDaily"
DHW_VAR = "degree_heating_week"
THRESHOLDS = (4.0, 8.0)
THRESHOLD_LABELS = {
    4.0: "NOAA Coral Reef Watch Alert Level 1",
    8.0: "NOAA Coral Reef Watch Alert Level 2",
}
LABEL = "Heat stress (degree heating weeks)"
UNIT = "°C-weeks"
SOURCE = {
    "name": "NOAA Coral Reef Watch daily degree heating weeks (not NASA)",
    "url": "https://coastwatch.noaa.gov/erddap/griddap/noaacrwdhwDaily.html",
}


@dataclass(frozen=True)
class YearlyMax:
    value: float | None
    date: str | None


def _key(threshold: float) -> str:
    return str(int(threshold))


def yearly_max(
    point: ReefPoint,
    years: Sequence[int],
    cache_dir: Path | None,
    client: httpx.Client | None,
) -> dict[int, YearlyMax]:
    """Peak daily DHW (unrounded) and its date per requested year. A year with no valid day is
    `YearlyMax(None, None)`; a year whose fetch failed is absent (ERDDAP raises if the first
    years all fail)."""
    ordered = sorted(years)
    peaks, _cell, _failed = erddap.fetch_point_yearly_peaks(
        DHW_DATASET, DHW_VAR, point.lat, point.lon, ordered[0], ordered[-1],
        erddap.warm_season(point.lat), client, cache_dir,
    )  # fmt: skip
    wanted = set(ordered)
    return {
        year: YearlyMax(value, date)
        for year, (value, date) in peaks.items()
        if year in wanted
    }


def _window_text(points: Sequence[ReefPoint]) -> str:
    windows = {erddap.warm_season(p.lat) for p in points}
    if len(windows) != 1:
        raise ValueError(
            "reef points with different warm-season windows need their own method text"
        )
    first, last = windows.pop()
    return f"{calendar.month_name[first]} to {calendar.month_name[last]}"


def heat_stress_summary(
    yearly: Mapping[str, Mapping[int, YearlyMax]],
    points: Sequence[ReefPoint],
    start: int,
    end: int,
) -> dict:
    """Counts of reef-years at or above each threshold, in two halves of the study period.

    Thresholds are tested on the unrounded value; values are rounded to 2 decimals for display only.
    """
    years = list(range(start, end + 1))
    rows = []
    raw: dict[tuple[str, int], float | None] = {}
    for p in points:
        got = yearly.get(p.id, {})
        series = []
        for y in years:
            entry = got.get(y) or YearlyMax(None, None)
            raw[(p.id, y)] = entry.value
            shown = None if entry.value is None else round(entry.value, 2)
            series.append({"year": y, "value": shown, "date": entry.date})
        above = {
            _key(t): [y for y in years if (v := raw[(p.id, y)]) is not None and v >= t]
            for t in THRESHOLDS
        }
        rows.append(
            {
                "id": p.id,
                "name": p.name,
                "lat": p.lat,
                "lon": p.lon,
                "yearly_max": series,
                "years_at_or_above": above,
            }
        )
    mid = start + (end - start + 1) // 2 - 1
    periods = []
    for lo, hi in ((start, mid), (mid + 1, end)):
        values = [raw[(p.id, y)] for p in points for y in range(lo, hi + 1)]
        measured = [v for v in values if v is not None]
        periods.append(
            {
                "years": [lo, hi],
                "reef_years_at_or_above": {
                    _key(t): sum(1 for v in measured if v >= t) for t in THRESHOLDS
                },
                "reef_years_measured": len(measured),
                "reef_years_missing": len(values) - len(measured),
            }
        )
    return {
        "label": LABEL,
        "unit": UNIT,
        "thresholds": [{"value": t, "label": THRESHOLD_LABELS[t]} for t in THRESHOLDS],
        "points": rows,
        "periods": periods,
        "method": f"Yearly maximum of the daily degree heating weeks, {_window_text(points)}, at each reef point.",
        "source": dict(SOURCE),
    }


def worst_reef_series(summary: dict) -> list[dict]:
    """Per year the highest value over the points; years without any point value are left out."""
    best: dict[int, float] = {}
    for row in summary["points"]:
        for r in row["yearly_max"]:
            v = r["value"]
            if v is not None and not math.isnan(v):
                best[r["year"]] = max(v, best.get(r["year"], v))
    return [{"year": y, "value": best[y]} for y in sorted(best)]
