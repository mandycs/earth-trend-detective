"""layers.json: inventory of the map layers a site actually has on disk."""

from __future__ import annotations

import json
from pathlib import Path

from app.layers import build_layers, write_layers


def _touch(path: Path, doc: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if doc is None:
        path.write_bytes(b"x")
    else:
        path.write_text(json.dumps(doc), encoding="utf-8")


TREND = {
    "var": "lst_day",
    "label": "Daytime ground temperature",
    "kind": "trend",
    "unit": "°C per decade",
    "vmin": -1.6,
    "vmax": 1.6,
    "stops": ["#000000", "#ffffff"],
    "legend": {"more": "↑ more heat", "less": "↓ less heat"},
    "years": [2003, 2024],
    "source": "MOD11A2.061",
}
YEARLY = {
    "var": "lst_day",
    "label": "Daytime ground temperature",
    "kind": "anomaly",
    "unit": "°C",
    "vmin": -1.9,
    "vmax": 1.9,
    "stops": ["#000000", "#ffffff"],
    "legend": {"more": "↑ warmer than usual"},
    "years": [2003, 2004],
    "file_pattern": "year_lst_day_{YYYY}.png",
    "source": "MOD11A2.061",
}


def _ids(doc: dict) -> list[str]:
    return [layer["id"] for layer in doc["layers"]]


def test_empty_dir_gives_no_layers(tmp_path: Path) -> None:
    doc = build_layers("nowhere", tmp_path / "nowhere")
    assert doc["site"] == "nowhere"
    assert doc["layers"] == []


def test_relief_and_bases_are_visual_only(tmp_path: Path) -> None:
    site = tmp_path / "s"
    _touch(site / "base.jpg")
    _touch(site / "base_hq.jpg")
    _touch(site / "base_hq.json", {"scenes": [["2024-06-04", "HLS_L30"], ["2024-08-23", "HLS_S30"]]})
    _touch(site / "heightmap_rgb.png")
    _touch(site / "heightmap.json", {"min_m": 1.0, "max_m": 9.0, "source": "NASADEM_HGT v001"})
    _touch(site / "hillshade.png")
    doc = build_layers("s", site)
    by_id = {layer["id"]: layer for layer in doc["layers"]}
    assert set(by_id) == {"base", "base_hq", "relief", "hillshade"}
    assert all(layer["status"] == "visual_only" for layer in by_id.values())
    assert by_id["base_hq"]["dates"] == ["2024-06-04", "2024-08-23"]
    assert by_id["relief"]["encoding"] == "terrain-rgb"
    assert by_id["relief"]["range_m"] == [1.0, 9.0]
    assert "NASADEM" in by_id["relief"]["source"]["name"]


def test_trend_and_yearly_layers_are_analysed_with_legend(tmp_path: Path) -> None:
    site = tmp_path / "s"
    _touch(site / "trend_lst_day.png")
    _touch(site / "trend_lst_day.json", TREND)
    _touch(site / "year_lst_day.json", YEARLY)
    _touch(site / "year_lst_day_2003.png")
    _touch(site / "year_lst_day_2004.png")
    doc = build_layers("s", site)
    by_id = {layer["id"]: layer for layer in doc["layers"]}
    trend = by_id["trend_lst_day"]
    assert trend["status"] == "analysed"
    assert trend["file"] == "trend_lst_day.png"
    assert trend["legend"]["stops"] == TREND["stops"]
    assert trend["legend"]["range"] == [-1.6, 1.6]
    assert trend["legend"]["unit"] == "°C per decade"
    assert trend["years"] == [2003, 2024]
    assert "MODIS" in trend["source"]["name"]
    yearly = by_id["year_lst_day"]
    assert yearly["kind"] == "yearly"
    assert yearly["file_pattern"] == "year_lst_day_{YYYY}.png"
    assert yearly["years"] == [2003, 2004]


def test_yearly_lists_only_years_whose_png_exists(tmp_path: Path) -> None:
    site = tmp_path / "s"
    _touch(site / "year_lst_day.json", YEARLY)
    _touch(site / "year_lst_day_2004.png")
    doc = build_layers("s", site)
    assert doc["layers"][0]["years"] == [2004]


def test_trend_png_without_sidecar_is_skipped(tmp_path: Path) -> None:
    site = tmp_path / "s"
    _touch(site / "trend_lst_day.png")
    assert build_layers("s", site)["layers"] == []


def test_before_after_pair(tmp_path: Path) -> None:
    site = tmp_path / "s"
    _touch(site / "before.jpg")
    _touch(site / "after.jpg")
    _touch(
        site / "before_after.json",
        {
            "layer": "MODIS_Terra_CorrectedReflectance_TrueColor",
            "before": {"year": 2003, "dates": ["2003-07-01"]},
            "after": {"year": 2024, "dates": ["2024-07-02"]},
        },
    )
    doc = build_layers("s", site)
    pair = {layer["id"]: layer for layer in doc["layers"]}["before_after"]
    assert pair["kind"] == "before_after"
    assert pair["status"] == "visual_only"
    assert pair["before"] == {"file": "before.jpg", "year": 2003, "dates": ["2003-07-01"]}
    assert pair["after"]["file"] == "after.jpg"


def test_layer_order_is_stable(tmp_path: Path) -> None:
    site = tmp_path / "s"
    _touch(site / "base.jpg")
    _touch(site / "trend_lst_day.png")
    _touch(site / "trend_lst_day.json", TREND)
    _touch(site / "hillshade.png")
    assert _ids(build_layers("s", site)) == ["base", "hillshade", "trend_lst_day"]


def test_write_layers_round_trips(tmp_path: Path) -> None:
    site = tmp_path / "s"
    _touch(site / "base.jpg")
    path = write_layers("s", site)
    assert path == site / "layers.json"
    assert json.loads(path.read_text(encoding="utf-8"))["layers"][0]["id"] == "base"


def test_detail_crop_listed_only_when_complete(tmp_path: Path) -> None:
    site = tmp_path / "s"
    _touch(site / "detail" / "heightmap_rgb.png")
    _touch(site / "detail" / "detail.json", {"bbox": [0, 0, 1, 1], "drawable_years": [2003], "sources": []})
    assert build_layers("s", site)["layers"] == []
    _touch(site / "detail" / "base.jpg")
    layer = build_layers("s", site)["layers"][0]
    assert layer["id"] == "detail" and layer["status"] == "visual_only"
    assert layer["files"]["base"] == "detail/base.jpg"
    assert layer["drawable_years"] == [2003]
