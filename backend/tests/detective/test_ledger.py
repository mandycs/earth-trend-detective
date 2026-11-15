import pytest

from app.detective.ledger import Ledger, TestRecord
from app.stats.verdict import Verdict


def test_correction_runs_over_all_tests_of_the_thread():
    led = Ledger()
    led.add_test(TestRecord("t1", "t2m", "Air temperature", "trend", 0.01, 0.8, False, None))
    for i in range(19):
        led.add_test(TestRecord(f"x{i}", f"v{i}", "v", "trend", 0.5, 0.1, False, None))
    q, verdict, _ = led.corrected()["t1"]
    assert q == pytest.approx(0.2)
    assert verdict != Verdict.REAL
    assert led.n_tests == 20


def test_ledger_dedupes_identical_calls():
    led = Ledger()
    key = led.call_key("trend_test", {"series_id": "s1"})
    assert led.cached(key) is None
    eid = led.remember(key, {"ok": 1})
    assert eid == "e1"
    assert led.cached(led.call_key("trend_test", {"series_id": "s1"})) == {"ok": 1, "evidence_id": eid}


def test_call_key_is_order_independent():
    led = Ledger()
    assert led.call_key("t", {"a": 1, "b": 2}) == led.call_key("t", {"b": 2, "a": 1})


def test_remember_does_not_mutate_and_keeps_full_result():
    led = Ledger()
    src = {"v": 1, "chart": [1, 2]}
    eid = led.remember("k", src)
    assert src == {"v": 1, "chart": [1, 2]}
    assert led.results[eid] == {"v": 1, "chart": [1, 2]}
    assert led.remember("k2", {}) == "e2"


def test_figures_excludes_chart_series_and_nested_dedupes():
    led = Ledger()
    led.remember("a", {"slope": 0.5, "chart": [9.1], "series": [8.2], "url": 7, "bbox": [1.5],
                       "nested": {"n": 12, "xs": [0.5, 3]}, "name": "x", "flag": True})
    led.add_test(TestRecord("t", "v", "l", "trend", 0.0123, 0.1, False, None))
    figs = led.figures()
    assert figs == [0.5, 12, 3]
    assert 0.0123 not in figs


def test_missing_slope_is_flat_and_nan_p_is_unknown():
    led = Ledger()
    led.add_test(TestRecord("t", "v", "l", "trend", float("nan"), None, True, None))
    q, verdict, _ = led.corrected()["t"]
    assert verdict == Verdict.UNKNOWN


def test_testrecord_not_collected_by_pytest():
    assert TestRecord.__test__ is False


def test_figures_never_include_p_or_q_values():
    led = Ledger()
    led.remember("a", {"slope_per_decade": 0.4, "p_value": 0.0082, "q_session": 0.0164,
                       "lags": [{"r": 0.61, "p": 0.031, "q": 0.05}]})
    assert led.figures() == [0.4, 0.61]
