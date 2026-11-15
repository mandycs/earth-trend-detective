"""Land-cover proportions reach the model as percentages, and the checker accepts "60 %"."""

from app.catalog import load_catalog
from app.detective.ledger import Ledger
from app.detective.place import Place
from app.detective.report import ledger_report
from app.detective.session import Session
from app.detective.tools import context
from app.detective.tools import data as tools
from app.detective.wording import screen_problems
from app.investigate import landcover
from app.investigate.landcover import LandCover


def _session() -> Session:
    place = Place(lat=37.0, lon=-4.5, bbox=(-4.6, 36.9, -4.4, 37.1), tags=())
    return Session(ledger=Ledger(), place=place, catalog=load_catalog(), series={})


def test_land_cover_change_gives_percentages_and_points(monkeypatch):
    pair = [LandCover(2003, {"Cropland": 0.6, "Savanna": 0.4}), LandCover(2023, {"Cropland": 0.412, "Savanna": 0.588})]
    monkeypatch.setattr(landcover, "land_cover_pair", lambda lat, lon, years: pair)
    out = context.land_cover_change(_session())
    crop = next(r for r in out["changes"] if r["class"] == "Cropland")
    assert crop == {
        "class": "Cropland", "before_pct": 60.0, "after_pct": 41.2, "change_points": -18.8,
        "everyday": {"in_ten_before": 6, "in_ten_after": 4, "out_of": "ten", "class": "Cropland"},  # exact rounding, done by code
    }
    assert "before" not in crop and "change" not in crop


def test_report_carries_the_biggest_land_cover_moves_with_their_share_in_ten(monkeypatch):
    from app.detective.nodes import check

    pair = [LandCover(2003, {"Cropland": 0.2, "Savanna": 0.8}), LandCover(2023, {"Cropland": 0.7, "Savanna": 0.3})]
    monkeypatch.setattr(landcover, "land_cover_pair", lambda lat, lon, years: pair)
    s = _session()
    context.land_cover_change(s)
    report = ledger_report(s, "Has this land turned into fields?")
    crop = next(r for r in report["land_cover"] if r["class"] == "Cropland")
    assert crop["everyday"]["in_ten_after"] == 7 and crop["years"] == [2003, 2023]
    assert {"in_ten_before": 2, "in_ten_after": 7, "out_of": "ten", "class": "Cropland"} in report["everyday"]
    # "7 in 10" is a tool's share in ten; "6 in 10" is not
    assert check("Now about 7 in 10 parts of the land are cropland.", report)[0]
    ok, _, rejected = check("Now about 6 in 10 parts of the land are cropland.", report)
    assert not ok and rejected


def test_a_quoted_cover_percentage_passes_the_checker(monkeypatch):
    cover = LandCover(year=2023, shares={"Cropland": 0.637, "Grassland": 0.363})
    monkeypatch.setattr(landcover, "fetch_land_cover", lambda lat, lon, year, client=None: cover)
    s = _session()
    tools.profile_place(s)
    report = ledger_report(s)
    assert screen_problems("Cropland covers 63.7 % of the area around the point.", report) == []
    assert screen_problems("Cropland covers about 64 percent of the area.", report) == []
    # an invented percentage is still caught
    assert screen_problems("Cropland covers 71 % of the area.", report) != []


def test_a_percentage_point_change_passes_the_checker(monkeypatch):
    pair = [LandCover(2003, {"Cropland": 0.6, "Savanna": 0.4}), LandCover(2023, {"Cropland": 0.412, "Savanna": 0.588})]
    monkeypatch.setattr(landcover, "land_cover_pair", lambda lat, lon, years: pair)
    s = _session()
    context.land_cover_change(s)
    report = ledger_report(s)
    assert screen_problems("Cropland fell from 60 % to 41.2 %, down 18.8 percentage points.", report) == []
