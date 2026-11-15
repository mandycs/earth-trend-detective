"""A suspect is `supported` only by a test that LINKS it to the variable under investigation."""

import pytest

from app.catalog import load_catalog
from app.detective import board as board_mod
from app.detective.board import Suspect, apply_update, evaluate
from app.detective.ledger import Ledger, TestRecord
from app.detective.place import Place
from app.detective.session import Session
from app.detective.tools import TOOLS
from app.detective.tools import UpdateBoardArgs

CATALOG = load_catalog()
TARGET_LABEL = next(v.label for v in CATALOG if v.id == "grace_tws")
NOT_LINKED = f"its own trend is real, but no test links it to {TARGET_LABEL}"


def _rec(test_id: str, var_id: str, kind: str, p: float, slope: float | None = -0.5) -> TestRecord:
    return TestRecord(id=test_id, var_id=var_id, label=var_id, kind=kind, p_value=p, slope=slope,
                      too_short=False, result=None)


def _ledger(*records: TestRecord) -> Ledger:
    """Each record is also a tool result: record i is evidence e<i>."""
    ledger = Ledger()
    for r in records:
        ledger.add_test(r)
        ledger.remember(f"{r.kind}:{r.id}", {"test_id": r.id, "test_ids": [r.id], "status": "ok"})
    return ledger


def _update(suspect, evidence, target="grace_tws", kind="climate", status="supported"):
    out = {"suspect": suspect, "status": status, "evidence_ids": evidence, "note": ""}
    if target is not None:
        out["target_var"] = target
    if kind is not None:
        out["kind"] = kind
    return out


# --------------------------------------------------------------------------- climate suspects


def test_climate_suspect_with_only_its_own_real_trend_is_trend_only():
    ledger = _ledger(_rec("t1", "grace_tws", "trend", 0.001), _rec("t2", "precip", "trend", 0.001))
    board = apply_update({}, _update("less rain", ["e2"]), ledger, CATALOG)
    s = board["less rain"]
    assert s.status == "trend_only"
    assert s.downgraded == NOT_LINKED
    assert s.claimed == "supported" and s.target_var == "grace_tws" and s.kind == "climate"


def test_climate_suspect_with_a_corrected_link_is_supported():
    ledger = _ledger(_rec("t1", "grace_tws", "trend", 0.001), _rec("t2", "grace_tws~precip", "correlate", 0.0001, 0.8))
    board = apply_update({}, _update("less rain", ["e2"]), ledger, CATALOG)
    assert board["less rain"].status == "supported" and board["less rain"].downgraded is None


def test_a_correlate_link_at_any_lag_and_either_order_counts():
    ledger = _ledger(_rec("t1", "precip~grace_tws", "correlate", 0.6, 0.1),
                     _rec("t2", "precip~grace_tws", "correlate", 0.0001, 0.8))
    board = apply_update({}, _update("less rain", ["e1", "e2"]), ledger, CATALOG)
    assert board["less rain"].status == "supported"


def test_climate_link_failing_correction_is_hint():
    weak = [_rec(f"t{i}", "ndvi", "trend", 0.9) for i in range(3, 13)]
    ledger = _ledger(_rec("t1", "grace_tws", "trend", 0.2), _rec("t2", "grace_tws~precip", "correlate", 0.04, 0.8), *weak)
    board = apply_update({}, _update("less rain", ["e2"]), ledger, CATALOG)
    assert board["less rain"].status == "hint"
    assert board["less rain"].downgraded == "fails correction over 12 tests"


def test_climate_suspect_is_never_supported_by_the_residual():
    ledger = _ledger(_rec("t1", "grace_tws", "residual", 0.0001))
    board = apply_update({}, _update("less rain", ["e1"]), ledger, CATALOG)
    assert board["less rain"].status != "supported"


def test_a_correlate_between_two_other_series_is_not_a_link():
    ledger = _ledger(_rec("t1", "grace_tws", "trend", 0.001), _rec("t2", "ndvi~precip", "correlate", 0.0001, 0.8))
    board = apply_update({}, _update("less rain", ["e2"]), ledger, CATALOG)
    assert board["less rain"].status == "hint"
    assert board["less rain"].downgraded == f"no test links it to {TARGET_LABEL}"


# --------------------------------------------------------------------------- non-climate suspects


def test_non_climate_suspect_with_a_real_residual_is_supported():
    ledger = _ledger(_rec("t1", "grace_tws", "trend", 0.001), _rec("t2", "grace_tws", "residual", 0.0001))
    board = apply_update({}, _update("irrigation", ["e2"], kind="non_climate"), ledger, CATALOG)
    assert board["irrigation"].status == "supported"


def test_non_climate_suspect_with_no_residual_is_hint():
    ledger = _ledger(_rec("t1", "grace_tws", "trend", 0.001), _rec("t2", "ndvi", "trend", 0.5))
    board = apply_update({}, _update("irrigation", ["e2"], kind="non_climate"), ledger, CATALOG)
    assert board["irrigation"].status == "hint"
    assert board["irrigation"].downgraded == "fails correction over 2 tests"


def test_non_climate_suspect_with_a_weak_residual_is_hint():
    ledger = _ledger(_rec("t1", "grace_tws", "trend", 0.001), _rec("t2", "grace_tws", "residual", 0.5))
    board = apply_update({}, _update("irrigation", ["e2"], kind="non_climate"), ledger, CATALOG)
    assert board["irrigation"].status == "hint"


def test_non_climate_suspect_citing_only_the_target_trend_is_not_supported():
    ledger = _ledger(_rec("t1", "grace_tws", "trend", 0.001))
    board = apply_update({}, _update("irrigation", ["e1"], kind="non_climate"), ledger, CATALOG)
    assert board["irrigation"].status == "hint"
    assert board["irrigation"].downgraded == f"no test links it to {TARGET_LABEL}"


def test_a_residual_of_another_variable_is_not_a_link():
    ledger = _ledger(_rec("t1", "grace_tws", "trend", 0.001), _rec("t2", "ndvi", "residual", 0.0001))
    board = apply_update({}, _update("irrigation", ["e2"], kind="non_climate"), ledger, CATALOG)
    assert board["irrigation"].status == "trend_only"


def test_target_given_as_a_series_id_is_read_as_its_variable():
    ledger = _ledger(_rec("t1", "grace_tws", "residual", 0.0001))
    board = apply_update({}, _update("irrigation", ["e1"], target="grace_tws:2003-2024", kind="non_climate"),
                         ledger, CATALOG)
    assert board["irrigation"].status == "supported"


# --------------------------------------------------------------------------- legacy calls and boards


def test_legacy_update_without_target_or_kind_is_still_judged():
    ledger = _ledger(
        _rec("t1", "grace_tws", "trend", 0.001),
        _rec("t2", "precip", "trend", 0.001),
        _rec("t3", "grace_tws", "residual", 0.0001),
        _rec("t4", "grace_tws~precip", "correlate", 0.0001, 0.8),
    )
    rain = apply_update({}, _update("less rain", ["e2"], target=None, kind=None), ledger, CATALOG)
    assert rain["less rain"].status == "trend_only"  # target from the residual, climate from precip
    assert rain["less rain"].target_var is None and rain["less rain"].kind is None
    linked = apply_update({}, _update("less rain", ["e4"], target=None, kind=None), ledger, CATALOG)
    assert linked["less rain"].status == "supported"
    farms = apply_update({}, _update("irrigation", ["e3"], target=None, kind=None), ledger, CATALOG)
    assert farms["irrigation"].status == "supported"  # non-climate: no climate driver in its evidence


def test_legacy_target_falls_back_to_the_first_trend_tested_series():
    ledger = _ledger(_rec("t1", "grace_tws", "trend", 0.001), _rec("t2", "precip", "trend", 0.001))
    board = apply_update({}, _update("less rain", ["e2"], target=None, kind=None), ledger, CATALOG)
    assert board["less rain"].status == "trend_only"
    assert board["less rain"].downgraded == NOT_LINKED


def test_legacy_climate_suspect_is_not_supported_by_the_residual():
    ledger = _ledger(_rec("t1", "grace_tws", "residual", 0.0001), _rec("t2", "precip", "trend", 0.001))
    board = apply_update({}, _update("less rain", ["e1", "e2"], target=None, kind=None), ledger, CATALOG)
    assert board["less rain"].status == "trend_only"


def test_legacy_board_rows_load_and_are_judged():
    row = {"id": "rain", "label": "rain", "status": "supported", "evidence": ["e2"], "note": "",
           "downgraded": None, "claimed": "supported", "dropped": []}
    ledger = _ledger(_rec("t1", "grace_tws", "trend", 0.001), _rec("t2", "precip", "trend", 0.001))
    place = Place(lat=37.0, lon=-4.5, bbox=(-4.6, 36.9, -4.4, 37.1), tags=())
    state = Session(ledger=ledger, place=place, catalog=CATALOG).to_state()
    state["board"] = {"rain": row}
    s = Session.from_state(state, CATALOG, None, "")
    assert evaluate(s.board, s.ledger)["rain"].status == "trend_only"


def test_evaluate_without_a_catalog_uses_the_default_one():
    ledger = _ledger(_rec("t1", "grace_tws", "trend", 0.001), _rec("t2", "precip", "trend", 0.001))
    board = {"rain": Suspect(id="rain", label="rain", status="supported", evidence=["e2"], claimed="supported")}
    assert evaluate(board, ledger)["rain"].downgraded == NOT_LINKED


# --------------------------------------------------------------------------- re-judging


def test_evaluate_after_later_weak_tests_moves_supported_to_trend_only():
    ledger = _ledger(_rec("t1", "precip", "trend", 0.0001), _rec("t2", "grace_tws~precip", "correlate", 0.01, 0.8))
    board = apply_update({}, _update("less rain", ["e1", "e2"]), ledger, CATALOG)
    assert board["less rain"].status == "supported"
    for i in range(3, 13):
        ledger.add_test(_rec(f"t{i}", "ndvi", "trend", 0.9))
    later = evaluate(board, ledger, CATALOG)
    assert later["less rain"].status == "trend_only"
    assert later["less rain"].downgraded == NOT_LINKED


def test_evaluate_after_later_weak_tests_moves_supported_to_hint():
    ledger = _ledger(_rec("t1", "grace_tws", "residual", 0.01))
    board = apply_update({}, _update("irrigation", ["e1"], kind="non_climate"), ledger, CATALOG)
    assert board["irrigation"].status == "supported"
    for i in range(2, 12):
        ledger.add_test(_rec(f"t{i}", "ndvi", "trend", 0.9))
    later = evaluate(board, ledger, CATALOG)
    assert later["irrigation"].status == "hint"
    assert later["irrigation"].downgraded == "fails correction over 11 tests"


# --------------------------------------------------------------------------- the tool


def test_trend_only_is_a_shown_status_but_not_one_to_ask_for():
    assert "trend_only" in board_mod.SHOWN_STATUSES and "trend_only" not in board_mod.STATUSES
    with pytest.raises(ValueError):
        apply_update({}, _update("x", [], status="trend_only"), Ledger(), CATALOG)


def test_update_board_schema_takes_target_and_kind_and_keeps_them_optional():
    fields = UpdateBoardArgs.model_fields
    assert "target_var" in fields and "kind" in fields
    assert fields["target_var"].description and fields["kind"].description
    legacy = UpdateBoardArgs.model_validate({"suspect": "x", "status": "open", "evidence_ids": [], "note": ""})
    assert legacy.target_var is None and legacy.kind is None
    with pytest.raises(ValueError):
        UpdateBoardArgs.model_validate({"suspect": "x", "status": "open", "evidence_ids": [], "note": "",
                                        "kind": "human"})


def test_update_board_tool_records_target_and_kind():
    place = Place(lat=37.0, lon=-4.5, bbox=(-4.6, 36.9, -4.4, 37.1), tags=())
    s = Session(ledger=_ledger(_rec("t1", "grace_tws", "trend", 0.001), _rec("t2", "precip", "trend", 0.001)),
                place=place, catalog=CATALOG)
    out = TOOLS["update_board"].fn(s, suspect="less rain", status="supported", evidence_ids=["e2"], note="",
                                   target_var="grace_tws", kind="climate")
    assert out["status"] == "trend_only" and out["downgraded"] == NOT_LINKED
    assert out["target_var"] == "grace_tws" and out["kind"] == "climate"
    assert board_mod.as_json(s.board)[0]["status"] == "trend_only"
