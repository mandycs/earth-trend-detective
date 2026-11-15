"""Zone tags: sea, coast, reef and city, and what each kind of place is offered."""

import pandas as pd
import pytest

from app import gather
from app.catalog import load_catalog
from app.detective.ledger import Ledger
from app.detective.place import Place
from app.detective.session import Session
from app.detective.tools import data as tools
from app.extractors import erddap
from app.investigate import landcover
from app.investigate.landcover import LandCover, tags_for, zone_tags


def _elevation(monkeypatch, low):
    """Stub the GEBCO call: `low` is the box's minimum elevation, or an exception to raise."""

    def fake(bbox, client=None, cache_dir=None, stride=4):
        if isinstance(low, Exception):
            raise low
        return low

    monkeypatch.setattr(erddap, "fetch_min_elevation", fake)


def _session(tags=("vegetated",), lat=37.0, lon=-4.5, water_share=None) -> Session:
    place = Place(lat=lat, lon=lon, bbox=(lon - 0.1, lat - 0.1, lon + 0.1, lat + 0.1), tags=tuple(tags), water_share=water_share)
    return Session(ledger=Ledger(), place=place, catalog=load_catalog(), series={})


def _rows(s: Session) -> dict[str, dict]:
    return {r["id"]: r for r in tools.list_variables(s)["variables"]}


def test_open_sea_is_ocean():
    assert zone_tags({"Water": 1.0}, 50.0) == ("ocean",)
    assert zone_tags({"Water": 0.5, "Grassland": 0.5}, 50.0) == ("ocean",)
    assert zone_tags({}, 50.0) == ("ocean",)  # no classified pixels at all: open sea
    assert zone_tags({"Water": 0.3, "Grassland": 0.7}, 50.0) == ("coast",)
    assert zone_tags({"Water": 0.05, "Grassland": 0.95}, 50.0) == ("coast",)
    assert zone_tags({"Water": 0.04, "Grassland": 0.96}, 50.0) == ()


def test_reef_latitude():
    assert zone_tags({"Water": 0.9}, 20.0) == ("ocean",)  # open sea is not reef
    assert zone_tags({"Water": 0.2}, -30.0) == ("coast", "reef")
    assert zone_tags({"Water": 0.2}, 30.1) == ("coast",)
    assert zone_tags({"Water": 1.0}, 30.0) == ("ocean",)
    assert "reef" not in zone_tags({"Grassland": 1.0}, 10.0)  # inland


def test_city_gets_atmosphere():
    assert zone_tags({"Urban and built-up land": 0.15, "Grassland": 0.85}, 40.0) == ("city", "atmosphere")
    assert zone_tags({"Urban and built-up land": 0.14, "Grassland": 0.86}, 40.0) == ()
    assert zone_tags({"Water": 0.3, "Urban and built-up land": 0.4}, 10.0) == ("coast", "reef", "city", "atmosphere")


def test_barren_next_to_ice_is_not_desert():
    shares = {"Permanent snow and ice": 0.6, "Barren": 0.4}
    assert "desert" not in tags_for(shares, lat=72.0)
    assert {"snow", "glacier"} <= set(tags_for(shares, lat=72.0))
    assert "desert" in tags_for({"Barren": 0.9, "Permanent snow and ice": 0.01}, lat=25.0)


def test_high_latitude_open_shrubland_is_not_desert():
    shares = {"Open shrubland": 0.9}
    assert "desert" not in tags_for(shares, lat=64.0)
    assert "desert" not in tags_for(shares, lat=-61.0)
    assert "desert" in tags_for(shares, lat=35.0)
    assert "desert" in tags_for(shares)  # no latitude known: unchanged behaviour


def test_sea_variable_off_land_not_available():
    rows = _rows(_session(tags=("vegetated",)))
    assert rows["sst"]["available"] is False
    assert rows["sst"]["reason"] == tools.NOT_SEA_REASON
    assert rows["chlorophyll"]["available"] is False


def test_sea_variables_available_at_sea():
    rows = _rows(_session(tags=("ocean",), lat=36.0, lon=-10.0))
    assert rows["sst"]["available"] and rows["chlorophyll"]["available"]


def test_profile_place_merges_zone_tags(monkeypatch):
    cover = LandCover(year=2023, shares={"Water": 0.7, "Grassland": 0.3})
    monkeypatch.setattr(landcover, "fetch_land_cover", lambda lat, lon, year, client=None: cover)
    _elevation(monkeypatch, -3000.0)
    s = _session(tags=(), lat=20.0, lon=-80.0)
    got = tools.profile_place(s)
    assert {"water_body", "ocean", "vegetated"} <= set(got["tags"])
    assert "reef" not in got["tags"]
    assert s.place.water_share == 0.7


def test_open_sea_hides_land_sources_and_keeps_grace_unavailable(monkeypatch):
    cover = LandCover(year=2023, shares={"Water": 1.0})
    monkeypatch.setattr(landcover, "fetch_land_cover", lambda lat, lon, year, client=None: cover)
    _elevation(monkeypatch, -4000.0)
    s = _session(tags=(), lat=30.0, lon=-40.0)
    tools.profile_place(s)
    assert "ocean" in s.place.tags and "reef" not in s.place.tags
    rows = _rows(s)
    for land_only in ("soil_moisture", "runoff", "ndvi", "lst_day", "et", "snow_cover", "water_area"):
        assert land_only not in rows
    assert rows["grace_tws"]["available"] is False
    assert rows["grace_tws"]["reason"] == tools.GRACE_AT_SEA_REASON
    assert rows["sst"]["available"] and rows["t2m"]["available"]


def test_coast_keeps_land_sources(monkeypatch):
    cover = LandCover(year=2023, shares={"Water": 0.3, "Grassland": 0.7})
    monkeypatch.setattr(landcover, "fetch_land_cover", lambda lat, lon, year, client=None: cover)
    _elevation(monkeypatch, -20.0)
    s = _session(tags=(), lat=45.0, lon=-1.0)
    tools.profile_place(s)
    rows = _rows(s)
    assert "soil_moisture" in rows and rows["grace_tws"]["available"] is True


def _profile(monkeypatch, shares, low, lat=25.0, lon=-80.0, site_id=None):
    cover = LandCover(year=2023, shares=shares)
    monkeypatch.setattr(landcover, "fetch_land_cover", lambda lat, lon, year, client=None: cover)
    _elevation(monkeypatch, low)
    s = _session(tags=(), lat=lat, lon=lon)
    if site_id:
        s.place = Place(lat=lat, lon=lon, bbox=s.place.bbox, site_id=site_id)
    tools.profile_place(s)
    return s


SEA_TAGS = {"ocean", "coast", "reef"}


def test_a_lake_gets_no_sea_tags(monkeypatch):
    s = _profile(monkeypatch, {"Water": 0.7, "Barren": 0.3}, 300.0, lat=36.1, lon=-114.7)
    assert not SEA_TAGS & set(s.place.tags)
    assert s.place.water_share is None
    rows = _rows(s)
    assert rows["sst"]["available"] is False and "soil_moisture" in rows


def test_atlantic_is_ocean(monkeypatch):
    s = _profile(monkeypatch, {"Water": 1.0}, -4000.0, lat=30.0, lon=-40.0)
    assert "ocean" in s.place.tags and s.place.water_share == 1.0


def test_coastal_box_is_coast_and_reef_in_the_tropics(monkeypatch):
    s = _profile(monkeypatch, {"Water": 0.2, "Grassland": 0.8}, -20.0, lat=25.0)
    assert {"coast", "reef"} <= set(s.place.tags)
    north = _profile(monkeypatch, {"Water": 0.2, "Grassland": 0.8}, -20.0, lat=50.0)
    assert "coast" in north.place.tags and "reef" not in north.place.tags


def test_a_solved_case_gets_no_sea_tags(monkeypatch):
    s = _profile(monkeypatch, {"Water": 0.7}, -4000.0, lat=36.1, lon=-114.7, site_id="lake_mead")
    assert not SEA_TAGS & set(s.place.tags)


def test_gebco_failure_means_no_sea_tags(monkeypatch):
    s = _profile(monkeypatch, {"Water": 1.0}, erddap.ErddapError("down"))
    assert not SEA_TAGS & set(s.place.tags)
    assert s.place.water_share is None


def test_get_series_refuses_land_only_variables_at_open_sea(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("must not fetch")

    monkeypatch.setattr(gather, "FETCHERS", {k: boom for k in gather.FETCHERS})
    s = _profile(monkeypatch, {"Water": 1.0}, -4000.0, lat=30.0, lon=-40.0)
    grace = tools.get_series(s, var_id="grace_tws")
    soil = tools.get_series(s, var_id="soil_moisture")
    assert grace["status"] == soil["status"] == "not_available"
    assert grace["reason"] == tools.GRACE_AT_SEA_REASON
    assert soil["reason"] == tools.LAND_AT_SEA_REASON


@pytest.mark.parametrize("share", [None, 0.97])
def test_session_state_round_trip_keeps_water_share(share):
    s = _session(water_share=share)
    back = Session.from_state(s.to_state(), s.catalog, None, "t")
    assert back.place.water_share == share
    assert back.place == s.place
