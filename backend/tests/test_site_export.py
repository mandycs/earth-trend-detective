"""site.json exporter: shape, badges, headline rules, assets on disk (no network)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.catalog import load_catalog
from app.gather import GatherResult
from app.site_export import build_site_json, find_assets, write_site_json
from app.site_story import BADGE_UNKNOWN, badge, format_number, headline, round_sig
from app.sites import load_sites

EXAMPLE = Path(__file__).resolve().parents[2] / "sites" / "_example" / "site.json"
IDX = pd.date_range("2003-01-01", "2024-12-01", freq="MS")
TODAY = dt.date(2026, 11, 14)


def seasonal(seed: int, slope: float = 0.0) -> pd.Series:
    rng = np.random.default_rng(seed)
    t = np.arange(len(IDX))
    return pd.Series(10 + 3 * np.sin(2 * np.pi * t / 12) + slope * t + rng.normal(0, 0.3, len(IDX)), index=IDX)


def gather_with_decline(site, catalog, start, end) -> GatherResult:
    series = {"t2m": seasonal(1), "precip": seasonal(2), "solar": seasonal(3), "grace_tws": seasonal(4, -0.05)}
    return GatherResult(series=series, missing={"lst_day": "pending"}, sources=("power", "grace"))


def gather_flat(site, catalog, start, end) -> GatherResult:
    series = {"t2m": seasonal(1), "precip": seasonal(2), "solar": seasonal(3), "grace_tws": seasonal(4)}
    return GatherResult(series=series, missing={}, sources=("power", "grace"))


def fake_validator(series, start, end) -> dict:
    return {"source": "USBR", "url": "u", "metric": "m", "r": 0.70123, "n_months": 250, "elevation_trend_m_per_decade": float("nan")}


@pytest.fixture
def lake():
    return load_sites().get("lake_mead")


def build(lake, tmp_path, gather=gather_with_decline, validators=None):
    validators = {"lake_mead": ("grace_tws", fake_validator)} if validators is None else validators
    return build_site_json(lake, load_catalog(), 2003, 2024, tmp_path, gather=gather, validators=validators, today=TODAY)


def test_shape_contains_example_keys(lake, tmp_path):
    doc = build(lake, tmp_path)
    example = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert set(example) - {"_note"} <= set(doc)
    example_var_keys = set(example["variables"][0])
    for row in doc["variables"]:
        assert example_var_keys <= set(row)
        assert {"badge", "ci_low", "ci_high", "q_value"} <= set(row)
    # Story contract (frontend/src/story/types.ts): steps may be objects (Ale's copy) or plain
    # titles (pipeline output); the pipeline never writes step bodies itself.
    titles = [st["title"] if isinstance(st, dict) else st for st in example["steps"]]
    assert doc["steps"] == titles
    assert doc["country"] == "United States"
    assert doc["elevation_m"] == doc["assets"]["heightmap_range_m"]
    assert doc["caveats"][0] == "The leftover share is a clue, not an attribution."
    for row in doc["variables"]:
        assert all(set(pt) == {"year", "value"} for pt in row["series"])
    assert doc["narrative"] is None
    assert doc["years"] == [2003, 2024] and doc["vertical_exaggeration"] == 3
    assert doc["generated_at"] == "2026-11-14" and doc["pipeline_version"] == "0.1"
    assert doc["missing"] == {"lst_day": "pending"}


def test_validation_and_sources(lake, tmp_path):
    doc = build(lake, tmp_path)
    assert doc["validation"]["r"] == 0.701
    assert doc["validation"]["elevation_trend_m_per_decade"] is None  # NaN -> null
    assert doc["sources"][-1]["validation"] is True
    assert all(s["title"] and s["url"] for s in doc["sources"])


def test_no_validation_for_other_sites(tmp_path):
    aletsch = load_sites().get("aletsch")
    doc = build_site_json(aletsch, load_catalog(), 2003, 2024, tmp_path, gather=gather_flat, today=TODAY)
    assert doc["validation"] is None and doc["vertical_exaggeration"] == 1.5


@pytest.mark.parametrize(
    ("verdict", "direction", "expected"),
    [
        ("real", "up", "↑ Real"),
        ("real", "down", "↓ Real"),
        ("likely", "up", "↑ Likely"),
        ("likely", "down", "↓ Likely"),
        ("unknown", "flat", BADGE_UNKNOWN),
        ("real", "flat", BADGE_UNKNOWN),
    ],
)
def test_badge_mapping(verdict, direction, expected):
    assert badge(verdict, direction) == expected
    assert BADGE_UNKNOWN == "? Can't tell yet"


def test_headline_one(lake, tmp_path):
    doc = build(lake, tmp_path)
    text = doc["headline"]
    assert text.startswith("Total water stored is going down for real (−")
    assert "cm per decade). About " in text and text.endswith("% of that change is not explained by climate.")


def test_headline_none_when_no_real_impact(lake, tmp_path):
    assert build(lake, tmp_path, gather=gather_flat)["headline"] is None


def test_headline_skips_rows_without_residual_and_drivers():
    rows = [
        {"id": "t2m", "label": "Air temperature", "unit": "°C", "verdict": "real", "direction": "up",
         "sen_slope_per_decade": 0.4, "residual_pct_non_climate": None},
        {"id": "soil_moisture", "label": "Topsoil moisture", "unit": "kg/m²", "verdict": "real", "direction": "down",
         "sen_slope_per_decade": -1.0, "residual_pct_non_climate": None},
        {"id": "grace_tws", "label": "Total water stored", "unit": "cm", "verdict": "real", "direction": "down",
         "sen_slope_per_decade": -6.4949, "residual_pct_non_climate": 84.4},
    ]
    impacts = frozenset({"soil_moisture", "grace_tws"})
    assert headline(rows, impacts) == (
        "Total water stored is going down for real (−6.5 cm per decade). "
        "About 84% of that change is not explained by climate."
    )
    assert headline(rows[:2], impacts) is None


def test_assets_only_listed_when_files_exist(tmp_path):
    empty = find_assets(tmp_path)
    assert empty == {"heightmap": None, "heightmap_range_m": None, "base": None, "trend": {}, "yearly": {}}
    for name in ("heightmap.png", "trend_grace_tws.png", "year_ndvi_2003.png", "year_ndvi_2004.png", "notes.txt"):
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "heightmap.json").write_text('{"min_m": 165.0, "max_m": 2373.0}')
    got = find_assets(tmp_path)
    assert got == {
        "heightmap": "heightmap.png",
        "heightmap_range_m": [165.0, 2373.0],
        "base": None,
        "trend": {"grace_tws": "trend_grace_tws.png"},
        "yearly": {"ndvi": "year_ndvi_{YYYY}.png"},
    }
    assert find_assets(tmp_path / "nope")["trend"] == {}


def test_trend_sidecar_pngs_are_not_variables(tmp_path):
    for name in ("trend_sst.png", "trend_sst_values.png", "trend_sst_significant.png"):
        (tmp_path / name).write_bytes(b"x")
    assert find_assets(tmp_path)["trend"] == {"sst": "trend_sst.png"}


def test_written_file_is_utf8_without_fake_or_nan(lake, tmp_path):
    doc = build(lake, tmp_path)
    path = write_site_json(doc, tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "FAKE" not in text.upper()
    assert "NaN" not in text and "\\u" not in text
    assert "−" in text  # non-ASCII kept as is
    assert json.loads(text) == doc


def test_rounding_helpers():
    assert round_sig(0.0123456) == 0.0123
    assert round_sig(-6.4949) == -6.49
    assert round_sig(float("nan")) is None and round_sig(5) == 5 and round_sig(True) is True
    assert format_number(-6.4949) == "−6.5" and format_number(0.04213) == "0.042" and format_number(123.4) == "120"
    assert not math.isnan(round_sig(1e-12))


def test_find_assets_lists_optional_relief_files_only_when_present(tmp_path):
    from app.site_export import find_assets

    (tmp_path / "base.jpg").write_bytes(b"x")
    (tmp_path / "hillshade.png").write_bytes(b"x")
    assets = find_assets(tmp_path)
    assert assets["hillshade"] == "hillshade.png"
    assert "heightmap_rgb" not in assets and "base_hq" not in assets


def test_headline_uses_the_range_when_driver_models_disagree():
    rows = [
        {"id": "grace_tws", "label": "Total water stored", "unit": "cm", "verdict": "real", "direction": "down",
         "sen_slope_per_decade": -6.47, "residual_pct_non_climate": 83.7, "residual_pct_range": [53.6, 83.7]},
    ]
    assert headline(rows, frozenset({"grace_tws"})) == (
        "Total water stored is going down for real (−6.5 cm per decade). "
        "Between 54% and 84% of that change is not explained by climate, depending on the climate model."
    )


def test_rows_carry_their_footprint():
    from app.site_export import FOOTPRINTS

    assert FOOTPRINTS["grace"]["km"] == 300
    assert set(FOOTPRINTS) >= {"grace", "power", "gldas", "appeears"}


def test_headline_never_says_about_zero_percent():
    rows = [
        {"id": "lst_day", "label": "Daytime ground temperature", "unit": "°C", "verdict": "real", "direction": "up",
         "sen_slope_per_decade": 0.49, "residual_pct_non_climate": 0.0, "residual_pct_range": None},
    ]
    assert headline(rows, frozenset({"lst_day"})) == (
        "Daytime ground temperature is going up for real (0.49 °C per decade). "
        "The climate we measured explains nearly all of that change."
    )
