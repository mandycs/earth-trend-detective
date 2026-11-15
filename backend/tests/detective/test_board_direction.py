"""A suspect whose own data went the other way is ruled out ("less rain" while rain went up)."""

from app.catalog import load_catalog
from app.detective.board import OPPOSITE, apply_update, evaluate, expected_direction
from app.detective.ledger import Ledger, TestRecord
from app.detective.place import Place
from app.detective.session import Session
from app.detective.tools import TOOLS, UpdateBoardArgs

CATALOG = load_catalog()


def _rec(test_id, var_id, kind, p, slope=-0.5, too_short=False):
    return TestRecord(id=test_id, var_id=var_id, label=var_id, kind=kind, p_value=p, slope=slope,
                      too_short=too_short, result=None)


def _ledger(*records):
    ledger = Ledger()
    for r in records:
        ledger.add_test(r)
        ledger.remember(f"{r.kind}:{r.id}", {"test_id": r.id, "test_ids": [r.id], "status": "ok"})
    return ledger


def _update(suspect, evidence, status="hint", expects=None, suspect_var="precip", kind="climate"):
    out = {"suspect": suspect, "status": status, "evidence_ids": evidence, "note": "",
           "target_var": "grace_tws", "kind": kind, "suspect_var": suspect_var}
    if expects is not None:
        out["expects"] = expects
    return out


RAIN_UP = _rec("t2", "precip", "trend", 0.0001, slope=3.0)


def test_rain_going_up_rules_out_less_rain_whatever_was_claimed():
    ledger = _ledger(_rec("t1", "grace_tws", "trend", 0.001), RAIN_UP)
    for claimed in ("open", "hint", "supported", "ruled_out"):
        board = apply_update({}, _update("less rain", ["e2"], status=claimed, expects="down"), ledger, CATALOG)
        s = board["less rain"]
        assert s.status == "ruled_out", claimed
        assert s.expects == "down"
    forced = apply_update({}, _update("less rain", ["e2"], status="hint", expects="down"), ledger, CATALOG)
    assert forced["less rain"].downgraded == OPPOSITE.format(went="up", expected="down")


def test_opposite_direction_beats_a_link():
    ledger = _ledger(_rec("t1", "grace_tws", "trend", 0.001), RAIN_UP,
                     _rec("t3", "grace_tws~precip", "correlate", 0.0001, 0.8))
    board = apply_update({}, _update("less rain", ["e2", "e3"], status="supported", expects="down"), ledger, CATALOG)
    assert board["less rain"].status == "ruled_out"


def test_same_direction_is_not_ruled_out():
    ledger = _ledger(_rec("t1", "grace_tws", "trend", 0.001), _rec("t2", "precip", "trend", 0.0001, slope=-3.0))
    board = apply_update({}, _update("less rain", ["e2"], status="ruled_out", expects="down"), ledger, CATALOG)
    assert board["less rain"].status == "open"  # rain did go down: no grounds to rule it out


def test_a_likely_opposite_trend_backs_a_claimed_rule_out_but_does_not_force_one():
    weak = [_rec(f"t{i}", "ndvi", "trend", 0.9) for i in range(3, 13)]
    ledger = _ledger(_rec("t1", "grace_tws", "trend", 0.5), _rec("t2", "precip", "trend", 0.04, slope=3.0), *weak)
    claimed = apply_update({}, _update("less rain", ["e2"], status="ruled_out", expects="down"), ledger, CATALOG)
    assert claimed["less rain"].status == "ruled_out" and claimed["less rain"].downgraded is None
    hint = apply_update({}, _update("less rain", ["e2"], status="hint", expects="down"), ledger, CATALOG)
    assert hint["less rain"].status == "hint"


def test_a_too_short_test_never_rules_out():
    ledger = _ledger(_rec("t1", "precip", "trend", 0.0001, slope=3.0, too_short=True))
    board = apply_update({}, _update("less rain", ["e1"], status="ruled_out", expects="down"), ledger, CATALOG)
    assert board["less rain"].status == "open"


def test_only_the_suspects_own_variable_counts():
    ledger = _ledger(_rec("t1", "grace_tws", "trend", 0.001), _rec("t2", "t2m", "trend", 0.0001, slope=3.0))
    board = apply_update({}, _update("less rain", ["e2"], status="hint", expects="down"), ledger, CATALOG)
    assert board["less rain"].status == "hint"


def test_expected_direction_is_read_from_the_name_when_not_given():
    assert expected_direction("less rain") == "down"
    assert expected_direction("lower snowfall") == "down"
    assert expected_direction("warming") == "up"
    assert expected_direction("more heat") == "up"
    assert expected_direction("rain") is None
    assert expected_direction("irrigation") is None
    assert expected_direction("more or less rain") is None


def test_a_name_derived_direction_only_keeps_a_claimed_rule_out():
    ledger = _ledger(_rec("t1", "grace_tws", "trend", 0.001), RAIN_UP)
    kept = apply_update({}, _update("less rain", ["e2"], status="ruled_out"), ledger, CATALOG)
    assert kept["less rain"].status == "ruled_out" and kept["less rain"].expects is None
    not_forced = apply_update({}, _update("less rain", ["e2"], status="hint"), ledger, CATALOG)
    assert not_forced["less rain"].status == "hint"


def test_less_snow_with_warming_air_is_not_forced_out():
    """Fix round 1 #2: the name says 'down', but warming air fits 'less snow'."""
    ledger = _ledger(_rec("t1", "grace_tws", "trend", 0.001), _rec("t2", "t2m", "trend", 0.0001, slope=0.5))
    board = apply_update({}, _update("less snow", ["e2"], status="hint", suspect_var="t2m"), ledger, CATALOG)
    assert board["less snow"].status == "hint"


def test_an_inferred_suspect_var_never_forces_a_rule_out():
    """Fix round 1 #1: 'less rain' with no suspect_var and a real warming trend is not ruled out."""
    ledger = _ledger(_rec("t1", "grace_tws", "trend", 0.001), _rec("t2", "t2m", "trend", 0.0001, slope=0.5))
    board = apply_update({}, _update("less rain", ["e2"], status="hint", expects="down", suspect_var=None),
                         ledger, CATALOG)
    assert board["less rain"].status == "hint"
    rain = _ledger(_rec("t1", "grace_tws", "trend", 0.001), RAIN_UP)
    inferred = apply_update({}, _update("less rain", ["e2"], status="hint", expects="down", suspect_var=None),
                            rain, CATALOG)
    assert inferred["less rain"].status == "hint"


def test_conflicting_tests_of_the_same_variable_do_not_force_a_rule_out():
    """Fix round 1 #3: rain really down over the whole period, really up since 2014."""
    ledger = _ledger(_rec("t1", "grace_tws", "trend", 0.001), _rec("t2", "precip", "trend", 0.0001, slope=-3.0),
                     _rec("t3", "precip", "trend", 0.0001, slope=3.0))
    board = apply_update({}, _update("less rain", ["e2", "e3"], status="hint", expects="down"), ledger, CATALOG)
    assert board["less rain"].status == "hint"


def test_a_bad_expects_value_is_ignored():
    ledger = _ledger(RAIN_UP)
    board = apply_update({}, _update("rain", ["e1"], expects="sideways"), ledger, CATALOG)
    assert board["rain"].expects is None and board["rain"].status == "hint"


def test_evaluate_rejudges_the_rule_out_when_the_correction_changes():
    ledger = _ledger(_rec("t1", "precip", "trend", 0.04, slope=3.0))
    board = apply_update({}, _update("less rain", ["e1"], status="hint", expects="down"), ledger, CATALOG)
    assert board["less rain"].status == "ruled_out"  # one test: q = p, real
    for i in range(2, 12):
        ledger.add_test(_rec(f"t{i}", "ndvi", "trend", 0.9))
    later = evaluate(board, ledger, CATALOG)
    assert later["less rain"].status == "hint"  # only likely now: back to what was claimed


def test_old_boards_without_expects_still_load():
    place = Place(lat=37.0, lon=-4.5, bbox=(-4.6, 36.9, -4.4, 37.1))
    s = Session(ledger=Ledger(), place=place, catalog=CATALOG)
    state = s.to_state()
    state["board"] = {"x": {"id": "x", "label": "x", "status": "open"}}
    again = Session.from_state(state, CATALOG, None, "t")
    assert again.board["x"].expects is None


def test_update_board_tool_takes_expects():
    assert "expects" in UpdateBoardArgs.model_fields
    place = Place(lat=37.0, lon=-4.5, bbox=(-4.6, 36.9, -4.4, 37.1))
    s = Session(ledger=_ledger(_rec("t1", "grace_tws", "trend", 0.001), RAIN_UP), place=place, catalog=CATALOG)
    out = TOOLS["update_board"].fn(s, suspect="less rain", status="hint", evidence_ids=["e2"], note="",
                                   target_var="grace_tws", kind="climate", suspect_var="precip", expects="down")
    assert out["status"] == "ruled_out" and out["expects"] == "down"
