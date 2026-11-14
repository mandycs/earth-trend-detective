"""Registry of the detective's tools: function, description for the model, argument schema.

Each tool is `fn(session, **args) -> dict`; `args_schema` lists the model-facing
arguments only (never `session`). Later plans add entries here.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

from pydantic import BaseModel, Field

from app.detective.tools import data


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
}

__all__ = ["TOOLS", "ToolSpec"]
