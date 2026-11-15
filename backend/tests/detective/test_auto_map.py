"""The map follows the investigation on its own: the camera flies to the place when it is profiled,
a layer shown without a date shows the year of the tested period, and a solved case offers its own layers."""

import pytest

from app.catalog import load_catalog
from app.detective.ledger import Ledger
from app.detective.nodes import run_call
from app.detective.place import Place
from app.detective.session import Session
from app.detective.tools import mapping
from app.investigate import landcover
from app.investigate.landcover import LandCover

PLACE = Place(lat=37.0, lon=-4.5, bbox=(-4.6, 36.9, -4.4, 37.1), tags=("agriculture",))


@pytest.fixture
def offline(monkeypatch):
    cover = LandCover(year=2023, shares={"Croplands": 0.6, "Grasslands": 0.4})
    monkeypatch.setattr(landcover, "fetch_land_cover", lambda lat, lon, year, client=None: cover)


def _session(place=PLACE) -> Session:
    return Session(ledger=Ledger(), place=place, catalog=load_catalog())


def _profile(s):
    return run_call(s, {"name": "profile_place", "args": {}, "id": "c1"})


# --------------------------------------------------------------------------- fly_to when profiling


def test_profiling_flies_the_camera_to_the_place_once(offline):
    s = _session()
    out = _profile(s)
    assert s.map == [{"op": "fly_to", "bbox": [-4.6, 36.9, -4.4, 37.1], "pitch": 55.0, "bearing": 0.0}]
    assert out["map"] == mapping.AUTO_FLY_NOTE
    _profile(s)
    assert [op["op"] for op in s.map] == ["fly_to"]


def test_no_automatic_flight_when_the_camera_already_moved(offline):
    s = _session()
    mapping.fly_to(s, [-5, 36, -4, 37], pitch=40)
    _profile(s)
    assert [op["op"] for op in s.map] == ["fly_to"] and s.map[0]["pitch"] == 40.0


def test_a_solved_case_profile_lists_the_cases_own_layers(offline):
    s = _session(Place(lat=36.1, lon=-114.4, bbox=(-114.9, 35.9, -114.0, 36.5), site_id="lake_mead"))
    out = _profile(s)
    ids = [row["layer_id"] for row in out["case_layers"]]
    assert "trend_lst_day" in ids and "before_after" in ids
    assert all(set(row) == {"layer_id", "title", "kind"} for row in out["case_layers"])


def test_a_point_profile_has_no_case_layers(offline):
    assert "case_layers" not in _profile(_session())


# --------------------------------------------------------------------------- show_layer without a date


def _tested(s, start, end):
    s.ledger.remember(f"trend_test:{start}-{end}", {"test_id": "t1", "years": [start, end], "status": "ok"})


def test_show_layer_without_a_date_shows_the_last_year_of_the_tested_period():
    s = _session()
    _tested(s, 2003, 2020)
    out = mapping.show_layer(s, "ndvi")
    assert s.map[-1]["year"] == 2020 and "date" not in s.map[-1]
    assert out["year"] == 2020 and out["year_note"] == mapping.TESTED_YEAR_NOTE


def test_show_layer_without_any_test_shows_the_end_of_the_investigation():
    s = _session()
    mapping.show_layer(s, "land_cover")
    assert s.map[-1]["year"] == 2024


def test_a_given_date_or_year_is_kept():
    s = _session()
    _tested(s, 2003, 2020)
    mapping.show_layer(s, "ndvi", date="2015-06-01")
    assert s.map[-1]["date"] == "2015-06-01" and "year" not in s.map[-1]
    mapping.show_layer(s, "land_cover", year=2010)
    assert s.map[-1]["year"] == 2010


def test_a_default_year_the_layer_does_not_have_is_left_out():
    s = _session()
    out = mapping.show_layer(s, "night_lights")  # only 2012 and 2016
    assert out["status"] == "shown" and "year" not in s.map[-1]


def test_a_case_yearly_layer_gets_the_tested_year_and_a_trend_layer_none():
    s = _session(Place(lat=36.1, lon=-114.4, bbox=(-114.9, 35.9, -114.0, 36.5), site_id="lake_mead"))
    _tested(s, 2003, 2019)
    mapping.show_layer(s, "year_lst_day")
    assert s.map[-1]["year"] == 2019
    mapping.show_layer(s, "trend_lst_day")
    assert "year" not in s.map[-1]
