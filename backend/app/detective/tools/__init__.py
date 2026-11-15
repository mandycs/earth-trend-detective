"""Registry of the detective's tools: function, description for the model, argument schema.

Each tool is `fn(session, **args) -> dict`; `args_schema` lists the model-facing
arguments only (never `session`). Later plans add entries here.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, NamedTuple

from pydantic import BaseModel, Field

from app.detective.tools import analysis, case_board, context, data, mapping


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


class LandCoverArgs(BaseModel):
    year_a: int = Field(default=2003, description="Earlier year (default 2003).")
    year_b: int = Field(default=2023, description="Later year (default 2023; the land cover map ends in 2023).")


class SatellitePictureArgs(BaseModel):
    year_a: int = Field(default=2003, description="Year of the 'before' picture (default 2003).")
    year_b: int = Field(default=2024, description="Year of the 'after' picture (default 2024).")


class SolvedCaseArgs(BaseModel):
    site_id: str = Field(description="Id of a solved case, e.g. 'lake_mead'.")


class YearsNeededArgs(BaseModel):
    series_id: str = Field(description="series_id returned by get_series.")


class ShowLayerArgs(BaseModel):
    layer_id: str = Field(
        description="Map layer id: one of the curated GIBS layers (true_colour, true_colour_viirs, land_cover, "
        "precipitation, ndvi, lst_day, soil_moisture, snow_cover, night_lights, active_fires, sst, chlorophyll) "
        "or, inside a solved case, one of that case's layers (e.g. 'trend_lst_day', 'relief', 'base_hq')."
    )
    date: str | None = Field(default=None, description="Day to show, YYYY-MM-DD (for daily, 8-day or monthly layers).")
    year: int | None = Field(default=None, description="Year to show (for yearly layers such as land_cover).")
    opacity: float = Field(default=0.8, ge=0, le=1, description="Layer opacity, 0 to 1.")


class SetYearArgs(BaseModel):
    year: int = Field(description="Year to move the map's year slider to.")


class BeforeAfterArgs(BaseModel):
    layer_id: str = Field(description="Map layer id (same ids as show_layer).")
    year_a: int = Field(description="Year on the 'before' side of the curtain.")
    year_b: int = Field(description="Year on the 'after' side of the curtain.")


class FlyToArgs(BaseModel):
    bbox: list[float] = Field(description="[min_lon, min_lat, max_lon, max_lat] in degrees.")
    pitch: float = Field(default=55, description="Camera tilt in degrees (0 = straight down, up to 85).")
    bearing: float = Field(default=0, description="Camera heading in degrees (0 = north up).")


class ShowFootprintArgs(BaseModel):
    source: Literal["grace", "power", "gldas"] = Field(
        description="Source whose data cell to outline: grace (~300 km), power (~50 km) or gldas (~25 km)."
    )


class UpdateBoardArgs(BaseModel):
    suspect: str = Field(description="Short name of the suspect, e.g. 'irrigation' or 'less rain'.")
    status: Literal["open", "supported", "hint", "ruled_out"] = Field(
        description="Status you propose; the code may downgrade it (supported -> trend_only or hint, "
        "ruled_out -> open)."
    )
    evidence_ids: list[str] = Field(
        description="evidence_id values of the tool results that back this status. For 'supported', include the "
        "test that links the suspect to target_var: the correlate(target, suspect) result, or for a non_climate "
        "suspect the climate_residual result of target_var."
    )
    note: str = Field(description="One plain sentence on why, using only figures from tool results.")
    target_var: str | None = Field(
        default=None,
        description="Always give it: the variable id whose change this suspect would explain (the variable under "
        "investigation), e.g. 'grace_tws'. The same for every suspect of one question.",
    )
    kind: Literal["climate", "non_climate"] | None = Field(
        default=None,
        description="Always give it: 'climate' for weather and climate suspects (rain, temperature, snow, sunlight), "
        "'non_climate' for water use, irrigation, dams, land change and anything else the climate data does not "
        "measure. A climate suspect can only be supported by a correlate test with target_var; a non_climate one "
        "also by a real climate_residual of target_var.",
    )
    suspect_var: str | None = Field(
        default=None,
        description="The catalog variable that measures this suspect, e.g. 'precip' for 'less rain'. Give it "
        "whenever one exists: a correlate test counts as a link only when it pairs target_var with this variable. "
        "Omit it for a suspect no catalog variable measures (it can then only be supported by the residual).",
    )
    expects: Literal["up", "down"] | None = Field(
        default=None,
        description="Always give it when suspect_var is given: the way suspect_var must go for this suspect to "
        "hold, e.g. 'down' for 'less rain', 'up' for 'warmer air'. If the suspect's own trend is real and goes "
        "the other way, the board rules the suspect out.",
    )


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
        "Only the exact same call is reused: swapping series_a and series_b or raising max_lag "
        "runs again and adds new tests to the correction. Moving together is a clue, not proof that one drives the other.",
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
    "land_cover_change": ToolSpec(
        context.land_cover_change,
        "Shows how the land cover around this place changed between two years (MODIS, 500 m): the "
        "classes whose share moved most, with before and after shares, and shows the land cover layer "
        "on the map. Always repeat the returned caveat: at 500 m, orchards and tree crops can be "
        "classed as savanna or woody vegetation. Not a statistical test.",
        LandCoverArgs,
    ),
    "satellite_picture": ToolSpec(
        context.satellite_picture,
        "Shows a clear before and after satellite picture of this place on the map. Visual only: no "
        "figure comes from it, so describe what it is, never measure from it. Not a test.",
        SatellitePictureArgs,
    ),
    "solved_case": ToolSpec(
        context.solved_case,
        "Reads the precomputed findings of one of the solved cases (for example 'lake_mead'): per "
        "variable the verdict, direction, slope per decade with its range and the share not explained "
        "by the climate we measured, plus the case caveats. Already corrected inside the case; it logs "
        "no new tests. Use it to compare with a similar place, not as evidence about this place.",
        SolvedCaseArgs,
    ),
    "show_layer": ToolSpec(
        mapping.show_layer,
        "Puts one layer on the map: the evidence of the current step (the variable just tested, for its year "
        "or day), with its legend, source and resolution shown to the user. Unknown ids or dates outside the "
        "layer are rejected. A map instruction: not a test, no figure comes from it.",
        ShowLayerArgs,
    ),
    "set_year": ToolSpec(
        mapping.set_year,
        "Moves the map's year slider (yearly layers follow it). A map instruction, not a test.",
        SetYearArgs,
    ),
    "show_before_after": ToolSpec(
        mapping.show_before_after,
        "Shows a before/after curtain of one map layer for two years, to compare by eye. Visual only: never "
        "measure from it. A map instruction, not a test.",
        BeforeAfterArgs,
    ),
    "fly_to": ToolSpec(
        mapping.fly_to,
        "Moves the map camera to a box, with a 3D tilt (pitch) and heading (bearing), e.g. to show the upstream "
        "basin or the place itself. A map instruction, not a test.",
        FlyToArgs,
    ),
    "show_footprint": ToolSpec(
        mapping.show_footprint,
        "Outlines on the map the data cell of a coarse source (GRACE ~300 km, POWER ~50 km, GLDAS ~25 km) around "
        "this place, to show that one value covers that whole cell. Use it whenever you cite a value from a "
        "source whose cell is bigger than the place. A map instruction, not a test.",
        ShowFootprintArgs,
    ),
    "update_board": ToolSpec(
        case_board.update_board,
        "Writes one suspect on the case board with a status (open / supported / hint / ruled_out), the "
        "evidence_ids that back it, a short note, the target_var under investigation and the suspect's kind "
        "(climate / non_climate). The code keeps the board honest: 'supported' needs an evidence test that LINKS "
        "the suspect to target_var and survives the correction over every test of this investigation: a "
        "correlate test between target_var and suspect_var (the variable that measures the suspect), or "
        "(non_climate suspects only) a real "
        "climate_residual of target_var. A suspect whose own trend is real but has no such link is shown as "
        "'trend_only' (TREND REAL, NOT LINKED); otherwise it is shown as 'hint' with the reason. 'ruled_out' "
        "needs a test with no clear trend and enough years, or its own data going the other way from 'expects', "
        "otherwise 'open'; a suspect whose own data really went the other way is ruled out whatever you ask. "
        "Report the status the board returns, not the one you asked for.",
        UpdateBoardArgs,
    ),
}

__all__ = ["TOOLS", "ToolSpec"]
