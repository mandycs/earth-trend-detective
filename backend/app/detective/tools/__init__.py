"""Registry of the detective's tools: function, description for the model, argument schema.

Each tool is `fn(session, **args) -> dict`; `args_schema` lists the model-facing
arguments only (never `session`). Later plans add entries here.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

from pydantic import BaseModel, Field

from app.detective.tools import analysis, data


class ToolSpec(NamedTuple):
    fn: Callable[..., dict]
    description: str
    args_schema: type[BaseModel]


class NoArgs(BaseModel):
    pass


class GetSeriesArgs(BaseModel):
    var_id: str = Field(description="Variable id from list_variables, e.g. 't2m'.")
    start: int | None = Field(default=None, description="First year (default 2003).")
    end: int | None = Field(default=None, description="Last year (default 2024).")


class TrendTestArgs(BaseModel):
    series_id: str = Field(description="series_id returned by get_series.")
    start: int | None = Field(default=None, description="First year of the window (default: start of the series).")
    end: int | None = Field(default=None, description="Last year of the window (default: end of the series).")


class ClimateResidualArgs(BaseModel):
    var_id: str = Field(description="Impact variable id from list_variables, e.g. 'grace_tws'.")


class CorrelateArgs(BaseModel):
    series_a: str = Field(description="series_id (from get_series) of the series to explain.")
    series_b: str = Field(description="series_id (from get_series) of the suspect series.")
    max_lag: int = Field(default=2, ge=0, le=5, description="Test lags 0..max_lag years (b earlier than a).")


class CompareSide(BaseModel):
    lat: float | None = Field(default=None, description="Latitude of this side's place (omit for this place).")
    lon: float | None = Field(default=None, description="Longitude of this side's place (omit for this place).")
    start: int | None = Field(default=None, description="First year of this side's period (default 2003).")
    end: int | None = Field(default=None, description="Last year of this side's period (default 2024).")


class CompareArgs(BaseModel):
    var_id: str = Field(description="Variable id from list_variables.")
    a: CompareSide = Field(description="Side a: a place {lat, lon} and/or a period {start, end}.")
    b: CompareSide = Field(description="Side b: a place {lat, lon} and/or a period {start, end}.")


class YearsNeededArgs(BaseModel):
    series_id: str = Field(description="series_id returned by get_series.")


TOOLS: dict[str, ToolSpec] = {
    "profile_place": ToolSpec(
        data.profile_place,
        "Call this first. Profiles the picked place: land-cover shares and the dominant class "
        "(MODIS, ~20 km box), the tags that decide which variables apply, and the size of the data "
        "cells. Coarse sources average over big cells (GRACE ~300 km, POWER ~50 km), so a single "
        "field or street is never resolved.",
        NoArgs,
    ),
    "list_variables": ToolSpec(
        data.list_variables,
        "Lists the catalog variables that apply to this place, each with a plain definition, its "
        "source, its spatial resolution and whether it can be fetched here (with the reason when "
        "not). Call after profile_place and before get_series; only fetch variables marked available.",
        NoArgs,
    ),
    "get_series": ToolSpec(
        data.get_series,
        "Fetches the monthly series of one variable at this place and returns a series_id, unit, "
        "number of months with data and year span (or status not_available with a reason). The "
        "values stay on the server; pass the series_id to trend_test. The value covers the whole "
        "data cell of its source, not the exact point.",
        GetSeriesArgs,
    ),
    "trend_test": ToolSpec(
        data.trend_test,
        "Tests a fetched series for a long-term trend after removing the seasonal cycle "
        "(Mann-Kendall with Sen slope). Returns slope per decade with its 95% range, p-value, the "
        "q-value corrected over every test of this investigation, the verdict (real / likely / "
        "unknown), direction and how many more years would be needed. Every call counts as a test "
        "and makes the correction stricter, so test only what the question needs. Quote only the "
        "returned numbers.",
        TrendTestArgs,
    ),
    "climate_residual": ToolSpec(
        analysis.climate_residual,
        "For an impact variable (water stored, vegetation, soil moisture...), fits it on its catalog "
        "climate drivers and returns the share of its change the climate we measured does not explain "
        "(pct_not_explained, with a range over driver models), the drivers used and the residual trend "
        "with its corrected q-value and verdict. Say it as 'not explained by the climate we measured — "
        "a clue, not proof'; never as a cause. When 'withheld' is returned, give that reason and no "
        "share. One residual per variable per investigation; it counts as one test.",
        ClimateResidualArgs,
    ),
    "correlate": ToolSpec(
        analysis.correlate,
        "Checks whether two fetched series move together from year to year: Pearson r and p of "
        "year-on-year changes at lags 0..max_lag years (lag k: series_b k years earlier), each with "
        "its corrected q-value and verdict. Each lag counts as one test, so keep max_lag small. "
        "Moving together is a clue, not proof that one drives the other.",
        CorrelateArgs,
    ),
    "compare": ToolSpec(
        analysis.compare,
        "Tests whether one variable trends differently in two places or two periods: each side is "
        "{lat, lon} (another place) and/or {start, end} (a period). Returns both trends (slope per "
        "decade, verdict, direction) and difference_per_decade = slope a - slope b. A variable can "
        "trend one way in one region and the opposite way in another. Each side counts as one test.",
        CompareArgs,
    ),
    "years_needed_for": ToolSpec(
        analysis.years_needed_for,
        "How many more years of data would be needed before the current trend of a fetched series "
        "could be told apart from natural ups and downs (null when no trend is in sight). Does not "
        "count as a test.",
        YearsNeededArgs,
    ),
}

__all__ = ["TOOLS", "ToolSpec"]
