import math

import pytest

from app.catalog import load_catalog
from app.detective import board as board_mod
from app.detective.board import Suspect, apply_update, evaluate
from app.detective.ledger import Ledger, TestRecord
from app.detective.place import Place
from app.detective.session import Session
from app.detective.tools import TOOLS, mapping


def _record(test_id: str, p: float, slope: float | None = 0.1, too_short: bool = False) -> TestRecord:
    return TestRecord(
        id=test_id, var_id="t2m", label="Air temperature", kind="trend",
        p_value=p, slope=slope, too_short=too_short, result=None,
    )


def _link(test_id: str, p: float) -> TestRecord:
    """A correlate test between the target (water stored) and the suspect (air temperature)."""
    return TestRecord(
        id=test_id, var_id="grace_tws~t2m", label="Water stored vs Air temperature", kind="correlate",
        p_value=p, slope=0.7, too_short=False, result=None,
    )


def _ledger(*records: TestRecord) -> Ledger:
    ledger = Ledger()
    for r in records:
        ledger.add_test(r)
        ledger.remember(f"trend_test:{r.id}", {"test_id": r.id, "status": "ok"})
    return ledger


@pytest.fixture
def ledger_with_one_weak_test() -> Ledger:
    ledger = Ledger()
    ledger.add_test(_record("t_weak", 0.2))
    return ledger


def _session(site_id: str | None = None) -> Session:
    place = Place(lat=37.0, lon=-4.5, bbox=(-4.6, 36.9, -4.4, 37.1), tags=("agriculture",), site_id=site_id)
    return Session(ledger=Ledger(), place=place, catalog=load_catalog(), series={})


# --------------------------------------------------------------------------- board


def test_supported_without_corrected_evidence_becomes_hint(ledger_with_one_weak_test):
    board = apply_update({}, {"suspect": "irrigation", "status": "supported",
                              "evidence_ids": ["t_weak"], "note": "x"}, ledger_with_one_weak_test)
    assert board["irrigation"].status == "hint"
    assert board["irrigation"].downgraded.startswith("fails correction over")
    assert board["irrigation"].downgraded == "fails correction over 1 test"


def test_supported_with_corrected_evidence_stays_supported():
    ledger = _ledger(_link("t1", 0.001))  # evidence e1 -> test t1, a link to the target
    board = apply_update({}, {"suspect": "irrigation", "status": "supported",
                              "evidence_ids": ["e1"], "note": "x", "suspect_var": "t2m"}, ledger)
    assert board["irrigation"].status == "supported"
    assert board["irrigation"].downgraded is None
    assert board["irrigation"].evidence == ["e1"]


def test_evidence_with_several_test_ids_uses_any_of_them():
    ledger = Ledger()
    ledger.add_test(_link("t1", 0.5))
    ledger.add_test(_link("t2", 0.0001))
    ledger.remember("correlate:x", {"test_ids": ["t1", "t2"], "status": "ok"})
    board = apply_update({}, {"suspect": "dams", "status": "supported", "evidence_ids": ["e1"], "note": "", "suspect_var": "t2m"}, ledger)
    assert board["dams"].status == "supported"


def test_n_in_downgrade_counts_only_tests_with_a_finite_p():
    ledger = _ledger(_record("t1", 0.3), _record("t2", math.nan, slope=None, too_short=True), _record("t3", 0.4))
    board = apply_update({}, {"suspect": "s", "status": "supported", "evidence_ids": ["e1"], "note": ""}, ledger)
    assert board["s"].downgraded == "fails correction over 2 tests"


def test_ruled_out_needs_a_long_enough_flat_test():
    ledger = _ledger(_record("t1", math.nan, slope=None, too_short=True), _record("t2", 0.7))
    short = apply_update({}, {"suspect": "rain", "status": "ruled_out", "evidence_ids": ["e1"], "note": ""}, ledger)
    assert short["rain"].status == "open"
    long_enough = apply_update({}, {"suspect": "rain", "status": "ruled_out", "evidence_ids": ["e2"], "note": ""}, ledger)
    assert long_enough["rain"].status == "ruled_out"
    assert long_enough["rain"].downgraded is None


def test_ruled_out_with_a_clear_trend_stays_open():
    ledger = _ledger(_record("t1", 0.0001))
    board = apply_update({}, {"suspect": "rain", "status": "ruled_out", "evidence_ids": ["e1"], "note": ""}, ledger)
    assert board["rain"].status == "open"


def test_unknown_evidence_ids_are_dropped_and_noted():
    ledger = _ledger(_record("t1", 0.001))
    board = apply_update({}, {"suspect": "s", "status": "supported", "evidence_ids": ["e1", "e99"], "note": ""}, ledger)
    assert board["s"].evidence == ["e1"]
    assert board["s"].dropped == ["e99"]


def test_supported_with_no_evidence_becomes_hint():
    board = apply_update({}, {"suspect": "s", "status": "supported", "evidence_ids": [], "note": ""}, Ledger())
    assert board["s"].status == "hint"
    assert board["s"].downgraded == "fails correction over 0 tests"


def test_apply_update_returns_a_new_dict():
    ledger = _ledger(_record("t1", 0.5))
    before: dict[str, Suspect] = {}
    after = apply_update(before, {"suspect": "s", "status": "open", "evidence_ids": [], "note": "n"}, ledger)
    assert before == {} and after is not before
    again = apply_update(after, {"suspect": "t", "status": "hint", "evidence_ids": ["e1"], "note": ""}, ledger)
    assert set(after) == {"s"} and set(again) == {"s", "t"}


def test_unknown_status_raises():
    with pytest.raises(ValueError):
        apply_update({}, {"suspect": "s", "status": "proven", "evidence_ids": [], "note": ""}, Ledger())


def test_evaluate_rejudges_after_later_tests_change_the_correction():
    ledger = _ledger(_link("t1", 0.01))
    board = apply_update({}, {"suspect": "s", "status": "supported", "evidence_ids": ["e1"], "note": "", "suspect_var": "t2m"}, ledger)
    assert board["s"].status == "supported"
    for i in range(2, 12):
        ledger.add_test(_record(f"t{i}", 0.9))
    later = evaluate(board, ledger)
    assert later["s"].status == "hint"
    assert later["s"].downgraded == "fails correction over 11 tests"
    assert board["s"].status == "supported"  # the old board is untouched


def test_update_board_tool_writes_session_and_returns_n_tests():
    s = _session()
    s.ledger = _ledger(_record("t1", 0.3))
    out = TOOLS["update_board"].fn(s, suspect="irrigation", status="supported", evidence_ids=["e1"], note="wells")
    assert out["status"] == "hint" and out["n_tests"] == 1
    assert out["downgraded"] == "fails correction over 1 test"
    assert s.board["irrigation"].status == "hint"
    assert board_mod.as_json(s.board)[0]["id"] == "irrigation"


def test_update_board_tool_rejects_unknown_status():
    s = _session()
    out = TOOLS["update_board"].fn(s, suspect="x", status="proven", evidence_ids=[], note="")
    assert out["status"] == "rejected" and s.board == {}


def test_board_tool_is_not_cached_and_logs_no_tests():
    s = _session()
    TOOLS["update_board"].fn(s, suspect="x", status="open", evidence_ids=[], note="")
    TOOLS["update_board"].fn(s, suspect="x", status="open", evidence_ids=[], note="")
    assert s.ledger.results == {} and s.ledger.n_tests == 0


# --------------------------------------------------------------------------- map


def test_show_layer_rejects_unknown_ids():
    s = _session()
    out = mapping.show_layer(s, "not_a_layer")
    assert out == {"status": "rejected", "reason": "unknown layer"}
    assert s.map == []


def test_show_layer_accepts_catalog_ids_and_land_cover():
    s = _session()
    out = mapping.show_layer(s, "land_cover", year=2020)
    assert out["status"] == "shown"
    assert s.map == [{"op": "show_layer", "layer_id": "land_cover", "year": 2020, "opacity": 0.8}]
    mapping.show_layer(s, "ndvi", date="2015-06-01", opacity=0.5)
    assert s.map[-1] == {"op": "show_layer", "layer_id": "ndvi", "date": "2015-06-01", "opacity": 0.5}


def test_show_layer_accepts_the_case_layers_only_inside_that_case():
    assert mapping.show_layer(_session(), "trend_lst_day")["status"] == "rejected"
    s = _session("aletsch")
    out = mapping.show_layer(s, "relief")
    assert out["status"] == "shown"
    assert s.map[-1]["layer_id"] == "relief"


def test_show_layer_rejects_dates_outside_the_layer():
    s = _session()
    assert mapping.show_layer(s, "land_cover", year=1990)["status"] == "rejected"
    assert mapping.show_layer(s, "night_lights", year=2014)["status"] == "rejected"
    assert mapping.show_layer(s, "night_lights", year=2016)["status"] == "shown"
    assert mapping.show_layer(s, "ndvi", date="June 2015")["status"] == "rejected"


def test_show_layer_result_to_the_model_carries_no_figures():
    s = _session()
    out = mapping.show_layer(s, "lst_day", year=2010)
    assert out["source"] and out["resolution"]
    assert "legend" not in out and "opacity" not in out


def test_every_map_layer_has_legend_source_and_dates():
    rows = mapping.load_map_layers()
    assert len(rows) >= 10
    ids = [r["id"] for r in rows.values()]
    assert len(ids) == len(set(ids))
    assert "land_cover" in rows
    for row in rows.values():
        assert row["gibs_layer"] and row["title"] and row["source"] and row["resolution"]
        assert row["kind"] in {"wmts", "wms"}
        assert set(row["legend"]) >= {"unit", "min", "max"}
        assert row["dates"]["start"] and row["dates"]["end"]
        assert row["dates"]["step"] in {"daily", "8day", "monthly", "annual"}
        assert row["zones"] and set(row["zones"]) <= mapping.ZONES


def test_every_zone_of_the_spec_has_a_layer():
    rows = mapping.load_map_layers()
    covered = {z for r in rows.values() for z in r["zones"]}
    assert covered == mapping.ZONES


def test_set_year_and_before_after():
    s = _session()
    assert mapping.set_year(s, 2010)["status"] == "shown"
    assert s.map[-1] == {"op": "set_year", "year": 2010}
    assert mapping.show_before_after(s, "true_colour", 2003, 2024)["status"] == "shown"
    assert s.map[-1] == {"op": "show_before_after", "layer_id": "true_colour", "year_a": 2003, "year_b": 2024}
    assert mapping.show_before_after(s, "nope", 2003, 2024)["status"] == "rejected"
    assert mapping.show_before_after(s, "true_colour", 2010, 2010)["status"] == "rejected"


def test_fly_to_validates_the_box():
    s = _session()
    out = mapping.fly_to(s, [-4.6, 36.9, -4.4, 37.1])
    assert out["status"] == "shown"
    assert s.map[-1] == {"op": "fly_to", "bbox": [-4.6, 36.9, -4.4, 37.1], "pitch": 55.0, "bearing": 0.0}
    assert mapping.fly_to(s, [1, 2, 3])["status"] == "rejected"
    assert mapping.fly_to(s, [3, 2, 1, 4])["status"] == "rejected"
    assert mapping.fly_to(s, [0, -95, 1, 0])["status"] == "rejected"
    mapping.fly_to(s, [0, 0, 1, 1], pitch=120, bearing=400)
    assert s.map[-1]["pitch"] == 85.0 and s.map[-1]["bearing"] == 40.0


def test_show_footprint_draws_the_data_cell():
    s = _session()
    out = mapping.show_footprint(s, "grace")
    assert out["status"] == "shown" and out["size"] == "~300 km"
    op = s.map[-1]
    assert op["op"] == "show_footprint" and op["source"] == "grace" and op["approximate"] is True
    assert "approximate data cell" in op["label"]
    w, so, e, n = op["bbox"]
    assert w < -4.5 < e and so < 37.0 < n
    assert mapping.show_footprint(s, "modis")["status"] == "rejected"


def test_map_tools_are_registered_not_cached_and_log_no_tests():
    names = {"show_layer", "set_year", "show_before_after", "fly_to", "show_footprint", "update_board"}
    assert names <= set(TOOLS)
    s = _session()
    TOOLS["show_layer"].fn(s, layer_id="ndvi")
    TOOLS["show_layer"].fn(s, layer_id="ndvi")
    assert len(s.map) == 2
    assert s.ledger.results == {} and s.ledger.n_tests == 0
    for name in names:
        schema = TOOLS[name].args_schema.model_json_schema()
        assert "session" not in schema.get("properties", {})
