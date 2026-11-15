import pytest

from app.catalog import load_catalog
from app.detective.ledger import Ledger
from app.detective.place import Place
from app.detective.session import Session
from app.detective.tools import TOOLS, context
from app.investigate import landcover, thennow
from app.investigate.landcover import LandCover

CAVEAT = "At 500 m, orchards and tree crops may be classed as savanna or woody vegetation, not cropland."


def _session() -> Session:
    place = Place(lat=37.0, lon=-4.5, bbox=(-4.6, 36.9, -4.4, 37.1), tags=("agriculture",))
    return Session(ledger=Ledger(), place=place, catalog=load_catalog(), series={})


def test_land_cover_always_carries_orchard_caveat(monkeypatch):
    pair = [LandCover(2003, {"Cropland": 0.6, "Savanna": 0.4}), LandCover(2023, {"Cropland": 0.4, "Savanna": 0.6})]
    monkeypatch.setattr(landcover, "land_cover_pair", lambda lat, lon, years: pair)
    s = _session()
    out = context.land_cover_change(s)
    assert out["caveat"] == CAVEAT
    assert {r["class"] for r in out["changes"]} == {"Cropland", "Savanna"}
    assert out["layer"] == "land_cover"
    assert s.map == [{"op": "show_layer", "layer_id": "land_cover", "year": 2023}]


def test_land_cover_source_failure_not_remembered(monkeypatch):
    def boom(lat, lon, years):
        raise RuntimeError("gibs down")

    monkeypatch.setattr(landcover, "land_cover_pair", boom)
    s = _session()
    out = context.land_cover_change(s)
    assert out["status"] == "not_available" and out["caveat"] == CAVEAT
    assert "evidence_id" not in out and s.map == []


def test_satellite_picture_is_visual_only_and_maps(monkeypatch):
    seen = {}

    def fake(lat, lon, years, tags):
        seen["args"] = (lat, lon, years, tuple(tags))
        return {
            "layer": "L", "bbox": [1, 2, 3, 4], "status": "visual_only",
            "before": {"year": 2003, "date": "2003-07-01", "url": "http://b"},
            "after": {"year": 2024, "date": "2024-07-01", "url": "http://a"},
        }

    monkeypatch.setattr(thennow, "then_and_now", fake)
    s = _session()
    out = context.satellite_picture(s)
    assert out["status"] == "visual_only"
    assert seen["args"] == (37.0, -4.5, (2003, 2024), ("agriculture",))
    assert s.map == [{
        "op": "show_before_after", "layer_id": "L", "year_a": 2003, "year_b": 2024,
        "before_url": "http://b", "after_url": "http://a", "bbox": [1, 2, 3, 4],
    }]


def test_satellite_picture_failure(monkeypatch):
    def boom(*a):
        raise RuntimeError("down")

    monkeypatch.setattr(thennow, "then_and_now", boom)
    s = _session()
    assert context.satellite_picture(s)["status"] == "not_available"
    assert s.map == []


def test_solved_case_reads_site_json():
    s = _session()
    out = context.solved_case(s, site_id="lake_mead")
    row = next(v for v in out["variables"] if v["id"] == "grace_tws")
    assert row["verdict"] == "real" and row["sen_slope_per_decade"] == -6.47
    assert "residual_pct_non_climate" in row and "series" not in row
    assert out["precomputed"] is True and out["caveats"]
    assert s.ledger.n_tests == 0


@pytest.mark.parametrize("bad", ["nope", "../etc", "", "_example", "lake_mead\n"])
def test_unknown_case_is_not_available(bad):
    out = context.solved_case(_session(), site_id=bad)
    assert out["status"] == "not_available"


def test_registered():
    for name in ("land_cover_change", "satellite_picture", "solved_case"):
        assert name in TOOLS


def test_example_case_is_not_a_solved_case():
    out = context.solved_case(_session(), site_id="_example")
    assert out["status"] == "not_available" and "Not a solved case." in out["reason"]


def test_cache_hit_same_result_and_no_duplicate_map(monkeypatch):
    pair = [LandCover(2003, {"Cropland": 0.6, "Savanna": 0.4}), LandCover(2023, {"Cropland": 0.4, "Savanna": 0.6})]
    monkeypatch.setattr(landcover, "land_cover_pair", lambda lat, lon, years: pair)
    s = _session()
    first = context.land_cover_change(s)
    second = context.land_cover_change(s)
    assert first == second
    assert len(s.map) == 1
