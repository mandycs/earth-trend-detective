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
    assert crop == {"class": "Cropland", "before_pct": 60.0, "after_pct": 41.2, "change_points": -18.8}
    assert "before" not in crop and "change" not in crop


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
