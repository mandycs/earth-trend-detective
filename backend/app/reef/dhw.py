"""Heat stress (NOAA Coral Reef Watch degree heating weeks) at the five reefs, as a counted record.

DHW is not a trend: no slope, no p, outside the FDR. The yearly maximum of the daily value
(January to June, the southern warm season) is counted against the NOAA Coral Reef Watch
thresholds of 4 and 8 °C-weeks, in the two halves of the study period. A reef-year whose
fetch failed or had no valid day is listed as missing, never counted as "below 4".

Fetching reuses `erddap` (one request per year, sequential, cached for past years, retries).
It is heat stress, not bleaching or coral death.
"""

from __future__ import annotations

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
METHOD = "Yearly maximum of the daily degree heating weeks, January to June, at each reef point."
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


def dhw_point_url(lat: float, lon: float, year: int) -> str:
    """The January 1 - June 30 request for one point and year (stride 1)."""
    axes = [
        erddap._axis(f"{year}-01-01T12:00:00Z", f"{year}-06-30T12:00:00Z"),
        erddap._axis(lat),
        erddap._axis(lon),
    ]
    return erddap.griddap_url(DHW_DATASET, DHW_VAR, axes)


def yearly_max(
    point: ReefPoint,
    years: Sequence[int],
    cache_dir: Path | None,
    client: httpx.Client | None,
) -> dict[int, YearlyMax]:
    """Peak daily DHW and its date per year. A year with no valid day is `YearlyMax(None, None)`;
    a year whose fetch failed is absent (ERDDAP raises if the first years all fail)."""
    ordered = sorted(years)
    frames, _cell, _failed = erddap._point_frames(
        DHW_DATASET, DHW_VAR, point.lat, point.lon, ordered[0], ordered[-1],
        erddap.warm_season(point.lat), client, cache_dir,
    )  # fmt: skip
    wanted = set(ordered)
    out: dict[int, YearlyMax] = {}
    for frame in frames:
        year = int(frame["time"].dt.year.iloc[0])
        valid = frame.dropna(subset=["value"])
        if year not in wanted:
            continue
        if valid.empty:
            out[year] = YearlyMax(None, None)
            continue
        top = valid.loc[valid["value"].idxmax()]
        out[year] = YearlyMax(
            round(float(top["value"]), 2), top["time"].strftime("%Y-%m-%d")
        )
    return out


def heat_stress_summary(
    yearly: Mapping[str, Mapping[int, YearlyMax]],
    points: Sequence[ReefPoint],
    start: int,
    end: int,
) -> dict:
    """Counts of reef-years at or above each threshold, in two halves of the study period."""
    years = list(range(start, end + 1))
    rows = []
    for p in points:
        got = yearly.get(p.id, {})
        series = [
            {"year": y, "value": (got.get(y) or YearlyMax(None, None)).value, "date": (got.get(y) or YearlyMax(None, None)).date}
            for y in years
        ]  # fmt: skip
        above = {
            _key(t): [
                r["year"] for r in series if r["value"] is not None and r["value"] >= t
            ]
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
        cells = [r for row in rows for r in row["yearly_max"] if lo <= r["year"] <= hi]
        measured = sum(1 for r in cells if r["value"] is not None)
        periods.append(
            {
                "years": [lo, hi],
                "reef_years_at_or_above": {
                    _key(t): sum(
                        1 for r in cells if r["value"] is not None and r["value"] >= t
                    )
                    for t in THRESHOLDS
                },
                "reef_years_measured": measured,
                "reef_years_missing": len(cells) - measured,
            }
        )
    return {
        "label": LABEL,
        "unit": UNIT,
        "thresholds": [{"value": t, "label": THRESHOLD_LABELS[t]} for t in THRESHOLDS],
        "points": rows,
        "periods": periods,
        "method": METHOD,
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
