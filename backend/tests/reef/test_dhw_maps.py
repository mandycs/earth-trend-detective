"""Heat-stress maps for the hot reef years. Offline."""

from __future__ import annotations

import json
import re

import httpx
import numpy as np
import pytest
from PIL import Image

from app import layers
from app.assets import maps
from app.extractors import erddap
from app.reef import dhw, dhw_maps
from app.reef.dhw import YearlyMax
from app.reef.points import REEF_POINTS, SITE_ID

BBOX = (145.5, -21.0, 150.0, -17.0)
LATS = [-20.0, -19.95, -19.9, -19.85]  # ascending, as ERDDAP answers
LONS = [147.0, 147.05, 147.1, 147.15, 147.2]


@pytest.fixture(autouse=True)
def _no_pause(monkeypatch):
    monkeypatch.setattr(erddap, "_sleep", lambda _s: None)


def _summary(entries: dict[str, dict[int, tuple[float | None, str | None]]]) -> dict:
    yearly = {pid: {y: YearlyMax(*v) for y, v in per.items()} for pid, per in entries.items()}
    return dhw.heat_stress_summary(yearly, REEF_POINTS, 2003, 2024)


def _hot_summary() -> dict:
    return _summary({
        "davies": {2016: (5.0, "2016-03-20"), 2020: (4.2, "2020-03-01"), 2010: (3.9, "2010-03-01")},
        "outer": {2020: (8.5, "2020-03-25")},
        "heron": {2017: (9.0, "2017-03-02")},  # outside the map
        "north": {2018: (10.0, "2018-03-05")},  # outside the map
    })


def test_hot_years_use_points_inside_the_map():
    assert dhw_maps.hot_years(_hot_summary(), BBOX) == {2016: "2016-03-20", 2020: "2020-03-25"}


def test_hot_year_needs_the_unrounded_value_at_or_above_4():
    summary = _summary({"davies": {2016: (3.996, "2016-03-20"), 2017: (4.0, "2017-03-21")}})
    assert summary["points"][1]["yearly_max"][13]["value"] == 4.0  # displayed rounding
    assert dhw_maps.hot_years(summary, BBOX) == {2017: "2017-03-21"}


def test_colour_classes():
    out = dhw_maps.colorize_dhw(np.array([3.99, 4.0, 8.0, np.nan]))
    assert out.dtype == np.uint8
    assert out[0].tolist() == [0xFD, 0xE6, 0x8A, 120]
    assert out[1].tolist() == [0xF9, 0x73, 0x16, 220]
    assert out[2].tolist() == [0xB9, 0x1C, 0x1C, 230]
    assert out[3, 3] == 0


def _grid_csv(day: str) -> str:
    head = "time,latitude,longitude,degree_heating_week\nUTC,degrees_north,degrees_east,degree_Celsius_weeks\n"
    rows = []
    for i, lat in enumerate(LATS):
        for j, lon in enumerate(LONS):
            value = "NaN" if (i, j) == (3, 4) else "9.0" if (i, j) == (0, 0) else "5.0" if i == 1 else "1.0"
            rows.append(f"{day}T12:00:00Z,{lat},{lon},{value}")
    return head + "\n".join(rows) + "\n"


def _handler(calls):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        day = re.search(r"(\d{4}-\d\d-\d\d)T12", str(request.url)).group(1)
        return httpx.Response(200, text=_grid_csv(day))

    return handler


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_meta_is_an_observed_layer(tmp_path):
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    calls: list[str] = []
    summary = _hot_summary()
    written = dhw_maps.write_dhw_maps(summary, BBOX, site_dir, tmp_path / "cache", _client(_handler(calls)))
    years = dhw_maps.hot_years(summary, BBOX)
    assert len(calls) == 2 and "%5B" in calls[0] and "[" not in calls[0]
    assert sorted(p.name for p in written) == [
        "dhw_2016.png", "dhw_2016_values.png", "dhw_2020.png", "dhw_2020_values.png", "meta.json",
    ]
    meta = json.loads((site_dir / "layers/dhw/meta.json").read_text())
    assert meta["years"] == list(years) and meta["dates"] == {str(y): d for y, d in years.items()}
    assert meta["id"] == "dhw" and meta["pixel_m"] == 5000 and meta["months"] is None
    assert meta["range"] == [0, 12] and meta["unit"] == "°C-weeks"
    assert meta["stops"] == ["#fde68a", "#f97316", "#b91c1c"]
    assert meta["source"] == dhw.SOURCE
    layer = next(x for x in layers.build_layers(SITE_ID, site_dir)["layers"] if x["id"] == "dhw")
    assert layer["status"] == "observed" and layer["var"] == "dhw"
    assert layer["years"] == list(years)
    assert layer["legend"]["range"] == [0, 12]


def test_overlay_aligns_with_bbox_corners_and_flips_north_south(tmp_path):
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    dhw_maps.write_dhw_maps(_hot_summary(), BBOX, site_dir, tmp_path / "c", _client(_handler([])))
    meta = json.loads((site_dir / "layers/dhw/meta.json").read_text())
    with Image.open(site_dir / "layers/dhw/dhw_2016_values.png") as im:
        width, height = im.size
        code = np.asarray(im).astype(float)
    assert (width, height) == maps.overlay_size(site_dir, BBOX)
    values = meta["value_offset"] + meta["value_scale"] * code
    # southernmost row (lat -20.0) is the last of 4 rows; first column is the west
    assert values[int(3.5 * height / 4), int(0.5 * width / 5)] == pytest.approx(9.0, abs=1e-3)
    assert values[int(0.5 * height / 4), int(0.5 * width / 5)] == pytest.approx(1.0, abs=1e-3)
    assert code[int(0.5 * height / 4), int(4.5 * width / 5)] == 0  # NaN corner NE: no data
    with Image.open(site_dir / "layers/dhw/dhw_2016.png") as im:
        rgba = np.asarray(im.convert("RGBA"))
    assert rgba[int(3.5 * height / 4), int(0.5 * width / 5), 3] == 230


def test_failed_day_is_skipped_not_cached_and_listed(tmp_path):
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    cache = tmp_path / "cache"

    def handler(request):
        if "2016-03-20" in str(request.url):
            return httpx.Response(503, text="busy")
        return httpx.Response(200, text=_grid_csv("2020-03-25"))

    dhw_maps.write_dhw_maps(_hot_summary(), BBOX, site_dir, cache, _client(handler))
    meta = json.loads((site_dir / "layers/dhw/meta.json").read_text())
    assert meta["years"] == [2020] and meta["missing_years"] == [2016]
    assert len(list(cache.rglob("*.csv"))) == 1


def test_all_days_failing_raises_and_writes_nothing(tmp_path):
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    with pytest.raises(erddap.ErddapError):
        dhw_maps.write_dhw_maps(
            _hot_summary(), BBOX, site_dir, tmp_path / "c", _client(lambda r: httpx.Response(503))
        )
    assert not (site_dir / "layers").exists()


def test_offline_uses_the_cache_and_never_calls_out(tmp_path):
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    cache = tmp_path / "cache"
    dhw_maps.write_dhw_maps(_hot_summary(), BBOX, site_dir, cache, _client(_handler([])))
    other = tmp_path / "site2"
    other.mkdir()
    out = dhw_maps.write_dhw_maps(_hot_summary(), BBOX, other, cache, None, offline=True)
    assert any(p.name == "meta.json" for p in out)
    with pytest.raises(erddap.ErddapError):
        dhw_maps.write_dhw_maps(_hot_summary(), BBOX, other, tmp_path / "empty", None, offline=True)


def test_no_hot_year_writes_no_layer(tmp_path):
    summary = _summary({"davies": {2016: (3.0, "2016-03-20")}})
    assert dhw_maps.write_dhw_maps(summary, BBOX, tmp_path, tmp_path / "c", None) == []
    assert not (tmp_path / "layers").exists()
