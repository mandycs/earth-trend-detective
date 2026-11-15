"""Reservoir water extent at 30 m (OPERA DSWx-HLS via GIBS): classes, cloudy scenes, years, the tool."""

from dataclasses import replace
from pathlib import Path

import httpx
import numpy as np
import pytest
from PIL import Image

from app.assets import gibs_layers
from app.assets.gibs_layers import TileFailed
from app.catalog import load_catalog
from app.detective.ledger import Ledger
from app.detective.place import Place
from app.detective.session import Session
from app.detective.tools import TOOLS
from app.detective.tools import data as tools
from app.detective.tools import water
from app.extractors import erddap
from app.extractors import water_extent as wx

@pytest.fixture(autouse=True)
def _land_box(monkeypatch):
    """GEBCO never reached in tests: by default the box is land (lowest point 100 m)."""
    monkeypatch.setattr(erddap, "fetch_min_elevation", lambda bbox, **k: 100.0)


FIXTURE = Path(__file__).parent / "fixtures" / "opera_dswx_vinuela.png"
VINUELA = (-4.27, 36.77, -4.07, 36.97)  # the ~20 km box the detective draws around 36.87 N, 4.17 W

WHITE, BLUE, PALE, CYAN, GREY = (255, 255, 255), (0, 0, 255), (180, 213, 244), (0, 255, 255), (175, 175, 175)


def _rgba(grid: list[list[tuple[int, int, int] | None]]) -> np.ndarray:
    out = np.zeros((len(grid), len(grid[0]), 4), dtype=np.uint8)
    for i, row in enumerate(grid):
        for j, colour in enumerate(row):
            if colour is not None:
                out[i, j] = (*colour, 255)
    return out


# --------------------------------------------------------------------------- one scene


def test_water_area_from_class_raster():
    rgba = _rgba([[WHITE, BLUE, PALE, WHITE]] * 10)  # 10 x 4, half the pixels water (classes 1 and 2)
    classes = wx.classes_from_rgba(rgba)
    assert set(np.unique(classes)) == {wx.NOT_WATER, wx.OPEN_WATER, wx.PARTIAL_WATER}
    area = np.full(classes.shape, 0.0009)  # 30 m x 30 m in km²
    assert wx.scene_water_area(classes, area) == pytest.approx(20 * 0.0009)  # partial beside open water counts


def test_scattered_partial_water_away_from_open_water_is_left_out():
    grid = [[WHITE] * 8 for _ in range(8)]
    grid[1][1] = BLUE
    grid[1][2] = PALE  # the shore of the open water: counted
    grid[6][6] = PALE  # a lone speck on a hillside: not counted
    classes = wx.classes_from_rgba(_rgba(grid))
    assert int(wx.water_mask(classes).sum()) == 2
    assert wx.scene_water_area(classes, np.ones(classes.shape)) == pytest.approx(2.0)


def test_unknown_colour_and_transparent_are_no_data():
    rgba = _rgba([[BLUE, (10, 20, 30), None]])
    assert list(wx.classes_from_rgba(rgba)[0]) == [wx.OPEN_WATER, wx.NO_DATA, wx.NO_DATA]


def test_cloudy_scene_skipped():
    area = np.full((10, 10), 0.0009)
    cloudy = [[GREY] * 3 + [BLUE] * 7] * 10  # 30 % cloud
    assert wx.scene_water_area(wx.classes_from_rgba(_rgba(cloudy)), area) is None
    snowy = [[CYAN] * 3 + [WHITE] * 7] * 10  # snow or ice hides water too
    assert wx.scene_water_area(wx.classes_from_rgba(_rgba(snowy)), area) is None
    edge = [[None] * 5 + [WHITE] * 5] * 10  # half the box outside the swath: would undercount
    assert wx.scene_water_area(wx.classes_from_rgba(_rgba(edge)), area) is None
    clear = [[BLUE] * 5 + [WHITE] * 5] * 10
    assert wx.scene_water_area(wx.classes_from_rgba(_rgba(clear)), area) == pytest.approx(50 * 0.0009)


def test_la_vinuela_bbox_area_in_plausible_range():
    """A real picture: GIBS `OPERA_L3_Dynamic_Surface_Water_Extent-HLS`, 2017-01-17, the La Viñuela box at
    593 x 741 px (fetched once on 2026-11-15). It carries ~20 km² of scattered partial-water specks on the
    hills, so counting every class-2 pixel would give ~24 km²."""
    rgba = np.asarray(Image.open(FIXTURE).convert("RGBA"))
    classes = wx.classes_from_rgba(rgba)
    area = wx.pixel_area_km2(VINUELA, classes.shape)
    km2 = wx.scene_water_area(classes, area)
    assert km2 is not None, "the fixture scene is a clear one"
    assert 0.5 < km2 < 6.0  # the reservoir is 5.65 km² when full (iAgua)


def test_pixel_area_sums_to_box_area():
    area = wx.pixel_area_km2(VINUELA, (737, 594))
    box_km2 = 0.2 * 111.195 * 0.2 * 111.195 * np.cos(np.radians(36.87))
    assert area.sum() == pytest.approx(box_km2, rel=1e-3)
    assert wx.grid_size(VINUELA) == pytest.approx((594, 741), abs=3)  # ~30 m pixels


def test_tries_are_spread_over_the_month():
    days = [f"2017-05-{d:02d}" for d in range(1, 31)]
    tries = wx.tries_for_month(days, max_tries=4)
    assert len(tries) == 4 and tries[0] == days[0] and tries[-1] == days[-1]
    assert wx.tries_for_month(days[:2], max_tries=4) == days[:2]
    assert wx.tries_for_month(days) == days  # by default every scene day of the month is tried


def test_year_value_is_median_of_clear_months_and_needs_enough():
    months = {m: float(m) for m in range(1, 10)}
    assert wx.year_value(months) == 5.0
    assert wx.year_value({1: 1.0, 2: 2.0}) is None


# --------------------------------------------------------------------------- yearly series


class _FakeSky:
    """CMR and GIBS answers per year: `scenes[year]` = {day: picture or 'fail' or None}."""

    def __init__(self, scenes, cmr_fail=()):
        self.scenes = scenes
        self.cmr_fail = set(cmr_fail)
        self.gets = 0

    def days(self, client, bbox, year):
        if year in self.cmr_fail:
            raise httpx.ConnectError("down")
        return sorted(self.scenes.get(year, {}))

    def fetch(self, client, layer, bbox, date, size):
        self.gets += 1
        pic = self.scenes[int(date[:4])][date]
        if pic == "fail":
            raise TileFailed(f"GIBS {date}: HTTP 503")
        if pic is None:
            return None
        w, h = size
        out = np.zeros((h, w, 4), dtype=np.uint8)
        out[...] = (*WHITE, 255)
        if pic == "cloud":
            out[...] = (*GREY, 255)
        else:
            out[:, : int(w * pic)] = (*BLUE, 255)  # `pic` = share of the box that is water
        return out


@pytest.fixture
def sky(monkeypatch, tmp_path):
    def install(scenes, cmr_fail=()):
        fake = _FakeSky(scenes, cmr_fail)
        monkeypatch.setattr(wx, "scene_days", fake.days)
        monkeypatch.setattr(gibs_layers, "_fetch", fake.fetch)
        monkeypatch.setattr(wx, "cache_dir_default", tmp_path / "cache")
        monkeypatch.setattr(wx, "last_complete_year", lambda: 2025)
        return fake

    return install


SMALL = (-4.172, 36.868, -4.168, 36.872)  # a tiny box keeps the fake pictures small


def _year(share, months=12, cloudy_first=False):
    out = {}
    for m in range(1, months + 1):
        if cloudy_first:
            out[f"{{y}}-{m:02d}-01"] = "cloud"
        out[f"{{y}}-{m:02d}-15"] = share
    return out


def _scenes(per_year: dict[int, dict]) -> dict[int, dict]:
    return {y: {k.format(y=y): v for k, v in days.items()} for y, days in per_year.items()}


def test_yearly_series_uses_one_clear_scene_a_month(sky):
    fake = sky(_scenes({2016: _year(0.5, cloudy_first=True), 2017: _year(0.25)}))
    s = wx.fetch_yearly_water(SMALL, 2016, 2017, client=httpx.Client())
    full = wx.pixel_area_km2(SMALL, wx.grid_size(SMALL)[::-1]).sum()
    assert list(s.index.year) == [2016, 2017]
    assert s.loc["2016-01-01"] == pytest.approx(full * 0.5, rel=0.05)
    assert s.loc["2017-01-01"] == pytest.approx(full * 0.25, rel=0.05)
    assert s.attrs["temporal"] == "annual" and s.attrs["clear_months"] == {2016: 12, 2017: 12}
    assert fake.gets == 12 * 2 + 12  # 2016: cloudy try then clear one, every month


def test_product_gap_and_too_few_months_are_said(sky):
    sky(_scenes({2016: _year(0.5), 2019: _year(0.5, months=5)}))  # 2017-2018: no scene at all
    s = wx.fetch_yearly_water(SMALL, 2016, 2019, client=httpx.Client())
    assert list(s.index.year) == [2016]
    assert s.attrs["no_scene_years"] == [2017, 2018]
    assert s.attrs["dropped_years"] == [2019]
    assert s.attrs["missing_years"] == []


def test_failed_request_is_a_gap_never_cached(sky, tmp_path):
    scenes = _scenes({2016: _year(0.5), 2017: _year(0.5)})
    scenes[2017]["2017-03-15"] = "fail"
    sky(scenes, cmr_fail={2018})
    s = wx.fetch_yearly_water(SMALL, 2016, 2018, client=httpx.Client())
    assert list(s.index.year) == [2016]
    assert s.attrs["missing_years"] == [2017, 2018]
    cached = list((tmp_path / "cache").glob("*.json"))
    assert len(cached) == 1  # only 2016


def test_cached_year_is_not_fetched_again(sky):
    fake = sky(_scenes({2016: _year(0.5)}))
    first = wx.fetch_yearly_water(SMALL, 2016, 2016, client=httpx.Client())
    gets = fake.gets
    again = wx.fetch_yearly_water(SMALL, 2016, 2016, client=httpx.Client())
    assert fake.gets == gets
    assert again.equals(first)


def test_corrupt_cache_is_refetched(sky, tmp_path):
    fake = sky(_scenes({2016: _year(0.5)}))
    wx.fetch_yearly_water(SMALL, 2016, 2016, client=httpx.Client())
    (path,) = (tmp_path / "cache").glob("*.json")
    path.write_text("{not json", encoding="utf-8")
    gets = fake.gets
    s = wx.fetch_yearly_water(SMALL, 2016, 2016, client=httpx.Client())
    assert fake.gets > gets and list(s.index.year) == [2016]


def test_all_failed_raises_failed(sky):
    sky({}, cmr_fail={2016, 2017})
    with pytest.raises(wx.WaterExtentError) as err:
        wx.fetch_yearly_water(SMALL, 2016, 2017, client=httpx.Client())
    assert err.value.failed is True


# --------------------------------------------------------------------------- the tool


def _session(tags=("water", "vegetated")) -> Session:
    lat, lon = 36.87, -4.17
    place = Place(lat=lat, lon=lon, bbox=(lon - 0.1, lat - 0.1, lon + 0.1, lat + 0.1), tags=tuple(tags))
    return Session(ledger=Ledger(), place=place, catalog=load_catalog(), series={})


def _yearly_areas(years, start_km2=5.0, step=-0.3):
    import pandas as pd

    s = pd.Series(
        [start_km2 + step * k for k in range(len(years))], index=pd.to_datetime([f"{y}-01-01" for y in years]), dtype=float
    )
    s.attrs = {
        "temporal": "annual",
        "clear_months": {y: 11 for y in years},
        "dropped_years": [],
        "no_scene_years": [2021, 2022],
        "missing_years": [],
    }
    return s


@pytest.fixture
def fetch(monkeypatch):
    calls = []

    def fake(bbox, start, end, client=None, cache_dir=None):
        calls.append((tuple(bbox), start, end))
        years = [y for y in range(max(start, 2016), end + 1) if y not in (2021, 2022)]
        return _yearly_areas(years)

    monkeypatch.setattr(wx, "fetch_yearly_water", fake)
    monkeypatch.setattr(wx, "last_complete_year", lambda: 2025)
    return calls


def test_tool_is_registered():
    assert "water_extent" in TOOLS
    fields = TOOLS["water_extent"].args_schema.model_fields
    assert set(fields) == {"year_a", "year_b"}


def test_tool_returns_yearly_areas_and_a_series_for_trend_test(fetch):
    s = _session()
    got = water.water_extent(s)
    assert got["status"] == "ok", got
    assert fetch == [(tuple(s.place.bbox), 2016, 2024)]  # session period, clipped to the product start
    assert got["resolution"] == "30 m" and got["unit"] == "km²"
    assert "OPERA" in got["source"] and got["basis"] == "annual"
    assert got["years"] == [2016, 2024]
    assert [r["year"] for r in got["yearly"]] == [2016, 2017, 2018, 2019, 2020, 2023, 2024]
    assert got["yearly"][0] == {"year": 2016, "area_km2": 5.0, "clear_months": 11}
    assert got["no_scene_years"] == [2021, 2022]
    assert got["caveat"] and got["evidence_id"]
    assert got["series_id"] in s.series

    test = tools.trend_test(s, got["series_id"])
    assert test["basis"] == "annual"
    assert test["unit"] == "km² per decade"
    assert test["too_short"] is True  # 7 years: fewer than the 10 an annual trend needs
    assert s.ledger.test(test["test_id"]).label == f"{water.LABEL} ({wx.METHOD})"


def test_tool_repeats_from_the_ledger(fetch):
    s = _session()
    first = water.water_extent(s, year_a=2016, year_b=2025)
    again = water.water_extent(s, year_a=2016, year_b=2025)
    assert len(fetch) == 1 and again["evidence_id"] == first["evidence_id"]


def test_tool_refetches_a_lost_series(fetch):
    s = _session()
    first = water.water_extent(s)
    s.series.clear()
    again = water.water_extent(s)
    assert len(fetch) == 2 and again["evidence_id"] == first["evidence_id"]
    assert first["series_id"] in s.series


@pytest.mark.parametrize("tags", [("ocean",), ("coast", "water"), ("coast", "reef")])
def test_tool_refuses_a_box_that_reaches_the_sea(fetch, tags):
    got = water.water_extent(_session(tags=tags))
    assert got["status"] == "not_available" and got["reason"] == water.AT_SEA_REASON
    assert fetch == []


def test_tool_before_the_product_starts(fetch):
    got = water.water_extent(_session(), year_a=2003, year_b=2010)
    assert got["status"] == "not_available" and "2016" in got["reason"]
    assert fetch == []


def test_tool_partial_answer_is_not_cached(monkeypatch):
    def partial(bbox, start, end, client=None, cache_dir=None):
        s = _yearly_areas([2016, 2017])
        s.attrs["missing_years"] = [2018]
        return s

    monkeypatch.setattr(wx, "fetch_yearly_water", partial)
    monkeypatch.setattr(wx, "last_complete_year", lambda: 2025)
    s = _session()
    got = water.water_extent(s, year_a=2016, year_b=2018)
    assert got["status"] == "ok" and got["transient"] is True and got["missing_years"] == [2018]
    assert "evidence_id" not in got


def test_tool_source_down_is_transient(monkeypatch):
    def down(*a, **k):
        raise wx.WaterExtentError("requests failed", failed=True)

    monkeypatch.setattr(wx, "fetch_yearly_water", down)
    monkeypatch.setattr(wx, "last_complete_year", lambda: 2025)
    got = water.water_extent(_session())
    assert got["status"] == "not_available" and got["transient"] is True
    assert got["reason"] == water.FAILED_REASON


def test_tool_no_clear_year_is_a_plain_answer(monkeypatch):
    def cloudy(*a, **k):
        raise wx.WaterExtentError("no year with enough clear scenes", failed=False)

    monkeypatch.setattr(wx, "fetch_yearly_water", cloudy)
    monkeypatch.setattr(wx, "last_complete_year", lambda: 2025)
    got = water.water_extent(_session())
    assert got["status"] == "not_available" and "transient" not in got and got["evidence_id"]


# --------------------------------------------------------------------------- fix round 1


def test_tool_refuses_an_unprofiled_place(fetch):
    got = water.water_extent(_session(tags=()))
    assert got["status"] == "not_available" and got["reason"] == water.PROFILE_FIRST_REASON
    assert "profile_place" in got["reason"] and fetch == []


def test_tool_refuses_when_the_sea_check_fails(fetch, monkeypatch):
    def down(*a, **k):
        raise erddap.ErddapError("GEBCO down")

    monkeypatch.setattr(erddap, "fetch_min_elevation", down)
    got = water.water_extent(_session())
    assert got["status"] == "not_available" and got["reason"] == water.SEA_UNKNOWN_REASON
    assert got["transient"] is True and fetch == []


def test_tool_refuses_when_the_box_dips_below_sea_level(fetch, monkeypatch):
    monkeypatch.setattr(erddap, "fetch_min_elevation", lambda bbox, **k: -40.0)
    got = water.water_extent(_session())  # tags say land: the profile's own sea check had failed
    assert got["status"] == "not_available" and got["reason"] == water.AT_SEA_REASON and fetch == []


def test_tool_clips_caller_years_to_the_product(fetch):
    s = _session()
    got = water.water_extent(s, year_a=2010, year_b=2030)
    assert fetch == [(tuple(s.place.bbox), 2016, 2025)]
    assert got["years"] == [2016, 2025] and got["series_id"] == "water_extent:2016-2025"
    assert got["yearly"][0]["year"] == 2016


def test_tool_start_after_end(fetch):
    got = water.water_extent(_session(), year_a=2020, year_b=2018)
    assert got["status"] == "not_available" and "after" in got["reason"] and fetch == []


def test_caveat_says_cloudy_months_are_left_out():
    assert "winter" in water.CAVEAT and "drier" in water.CAVEAT


def test_a_flaky_day_does_not_drop_the_year(sky):
    scenes = _scenes({2016: _year(0.5)})
    for m in range(1, 13):
        scenes[2016][f"2016-{m:02d}-01"] = "fail"  # tried first, then the clear day of the 15th
    sky(scenes)
    s = wx.fetch_yearly_water(SMALL, 2016, 2016, client=httpx.Client())
    assert list(s.index.year) == [2016] and s.attrs["missing_years"] == []


def test_a_month_failing_with_no_clear_scene_is_a_gap(sky):
    scenes = _scenes({2016: _year(0.5), 2017: _year(0.5)})
    scenes[2016]["2016-03-15"] = "fail"
    sky(scenes)
    s = wx.fetch_yearly_water(SMALL, 2016, 2017, client=httpx.Client())
    assert s.attrs["missing_years"] == [2016] and list(s.index.year) == [2017]


def test_a_year_at_the_edge_of_the_product_gap_is_not_cached(sky, tmp_path):
    fake = sky(_scenes({2020: _year(0.5, months=8)}))  # scenes stop in August: dropped, not forever
    with pytest.raises(wx.WaterExtentError):
        wx.fetch_yearly_water(SMALL, 2020, 2020, client=httpx.Client())
    assert not list((tmp_path / "cache").glob("*.json"))
    gets = fake.gets
    with pytest.raises(wx.WaterExtentError):
        wx.fetch_yearly_water(SMALL, 2020, 2020, client=httpx.Client())
    assert fake.gets > gets


def test_a_cloudy_year_with_scenes_every_month_is_cached_as_dropped(sky, tmp_path):
    scenes = _scenes({2016: {f"{{y}}-{m:02d}-15": ("cloud" if m <= 4 else 0.5) for m in range(1, 13)}})
    sky(scenes)
    with pytest.raises(wx.WaterExtentError):
        wx.fetch_yearly_water(SMALL, 2016, 2016, client=httpx.Client())  # 8 clear months: dropped
    assert len(list((tmp_path / "cache").glob("*.json"))) == 1


# --------------------------------------------------------------------------- final review fixes


def test_profile_first_refusal_is_not_cached(fetch):
    """Told to call profile_place first, the model does; the next call must not replay the refusal."""
    s = _session(tags=())
    first = water.water_extent(s)
    assert first["reason"] == water.PROFILE_FIRST_REASON and "evidence_id" not in first
    s.place = replace(s.place, tags=("water", "vegetated"))  # what profile_place does
    again = water.water_extent(s)
    assert again["status"] == "ok" and fetch != []
