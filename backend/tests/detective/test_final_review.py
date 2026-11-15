"""Fixes from the final whole-branch review (all offline)."""

import math

import numpy as np
import pandas as pd
import pytest

from app import gather
from app.catalog import load_catalog
from app.detective import board as board_mod
from app.detective.ledger import Ledger, TestRecord
from app.detective.nodes import check, template_answer
from app.detective.place import Place
from app.detective.prompt import conclude_request
from app.detective.report import ledger_report
from app.detective.session import Session
from app.detective.tools import TOOLS, analysis, context, data, mapping
from app.explain.validator import validate_narrative
from app.investigate import thennow

PLACE = Place(lat=37.0, lon=-4.5, bbox=(-4.6, 36.9, -4.4, 37.1), tags=("agriculture",))


def _session(site_id=None) -> Session:
    place = Place(lat=37.0, lon=-4.5, bbox=(-4.6, 36.9, -4.4, 37.1), tags=("agriculture",), site_id=site_id)
    return Session(ledger=Ledger(), place=place, catalog=load_catalog(), series={})


def _synthetic(start=2003, end=2024, slope_per_year=0.05):
    idx = pd.date_range(f"{start}-01-01", f"{end}-12-01", freq="MS")
    t = np.arange(idx.size) / 12.0
    rng = np.random.default_rng(0)
    return pd.Series(10 + 5 * np.sin(2 * np.pi * idx.month / 12) + slope_per_year * t + rng.normal(0, 0.2, idx.size), index=idx)


def _record(test_id, p, slope=0.1, too_short=False):
    return TestRecord(id=test_id, var_id="t2m", label="Air temperature", kind="trend",
                      p_value=p, slope=slope, too_short=too_short, result=None)


REPORT = {
    "variables": [
        {"id": "grace_tws", "label": "Water stored", "unit": "cm", "verdict": "real", "direction": "down",
         "sen_slope_per_decade": -4.2, "ci_low": -5.0, "ci_high": -3.0, "years_needed": None,
         "residual_pct_non_climate": 62.0, "residual_pct_range": None},
    ],
    "start": 2003,
    "end": 2024,
    "figures": [62.0, 47.0, -4.2],
    "n_tests": 2,
    "question": "Why is the water going down?",
}
WORDING = "not explained by the climate we measured — a clue, not proof"


# --------------------------------------------------------------------------- I-4 cause claims


@pytest.mark.parametrize(
    "sentence",
    [
        f"Water stored went down, driven by irrigation; 62% is {WORDING}.",
        f"Irrigation is draining the water stored; 62% is {WORDING}.",
        f"Farms are responsible for the drop in water stored; 62% is {WORDING}.",
        f"The drop in water stored results from pumping; 62% is {WORDING}.",
        f"Water stored fell because farmers pump it; 62% is {WORDING}.",
        f"62% comes from farming, {WORDING}.",
        f"The drop is due to wells; 62% is {WORDING}.",
        f"Pumping explains the drop; 62% is {WORDING}.",
        f"We blame the farms; 62% is {WORDING}.",
        f"Farming caused it, not the rain; 62% is {WORDING}.",
    ],
)
def test_detective_check_rejects_every_cause_claim(sentence):
    ok, _, rejected = check(sentence, REPORT)
    assert not ok, sentence
    assert any("cause" in r for r in rejected), rejected


def test_detective_check_accepts_the_honest_wording():
    ok, _, rejected = check(f"Water stored went down from 2003 to 2024; 62% of the drop is {WORDING}.", REPORT)
    assert ok, rejected


def test_explain_validator_keeps_its_own_causal_rule():
    # /explain is unchanged: a hedged or negated causal phrase still passes there
    report = {k: v for k, v in REPORT.items() if k != "question"}
    text = "Water stored went down. It might be caused by pumping. About 62% is not explained by climate, a lead, not proof."
    assert validate_narrative(text, report).ok


# --------------------------------------------------------------------------- m2 residual wording


def test_detective_check_rejects_a_lead_not_proof():
    ok, _, rejected = check("Water stored went down; 62% is not explained by climate, a lead, not proof.", REPORT)
    assert not ok
    assert any("not explained by the climate we measured" in r for r in rejected), rejected


def test_detective_check_requires_the_residual_wording_when_a_share_is_in_the_report():
    ok, _, rejected = check("Water stored went down from 2003 to 2024, a clue, not proof.", REPORT)
    assert not ok
    assert any("not explained by the weather we measured" in r for r in rejected), rejected  # the plain wording


# --------------------------------------------------------------------------- I-2 nothing measured


def _nothing_measured(monkeypatch) -> Session:
    def empty(site, variables, catalog, start, end):
        return {v.id: pd.Series(dtype=float) for v in variables}

    monkeypatch.setattr(gather, "FETCHERS", {**gather.FETCHERS, "power": empty})
    s = _session()
    assert data.get_series(s, var_id="t2m")["status"] == "not_available"
    return s


def test_report_lists_what_could_not_be_measured(monkeypatch):
    s = _nothing_measured(monkeypatch)
    report = ledger_report(s, "Is it warmer?")
    assert report["n_tests"] == 0
    assert report["not_measured"] == [
        {"label": "Air temperature", "reason": "no data for Air temperature here in 2003-2024"}
    ]
    assert '"not_measured"' in conclude_request("Is it warmer?", report, [])


def test_template_with_no_test_says_nothing_could_be_measured(monkeypatch):
    s = _nothing_measured(monkeypatch)
    text, _ = template_answer(ledger_report(s, "Is it warmer?"))
    assert "Nothing could be measured here" in text, text
    assert "no data for Air temperature here" in text
    assert "is changing" not in text.replace("whether anything is changing", "")


def test_template_with_no_test_and_no_reason():
    text, figures = template_answer(ledger_report(_session(), "Is it warmer?"))
    assert text.startswith("Nothing could be measured here")
    assert figures == []


def test_check_rejects_nothing_is_changing_with_no_test(monkeypatch):
    s = _nothing_measured(monkeypatch)
    report = ledger_report(s, "Is it warmer?")
    ok, _, rejected = check("Nothing here is changing in a clear way.", report)
    assert not ok and rejected


def test_template_answer_passes_the_detective_check(monkeypatch):
    monkeypatch.setattr(gather, "FETCHERS", {**gather.FETCHERS, "power": lambda site, variables, catalog, start, end: {
        v.id: _synthetic(start, end).rename(v.id) for v in variables}})
    s = _session()
    data.trend_test(s, series_id=data.get_series(s, var_id="t2m")["series_id"])
    report = ledger_report(s, "Is it warmer?")
    text, _ = template_answer(report)
    ok, _, rejected = check(text, report)
    assert ok, (text, rejected)


# --------------------------------------------------------------------------- I-3 board notes


PROBE = "Rain fell 47% since the dam was built, caused by farms."


def test_board_note_with_an_unchecked_figure_or_a_cause_is_not_shown():
    s = _session()
    out = TOOLS["update_board"].fn(s, suspect="farms", status="open", evidence_ids=[], note=PROBE)
    assert s.board["farms"].note == "" and out["note"] == ""
    assert out["note_removed"]
    assert "47" not in str(out)


def test_board_note_that_passes_is_kept():
    s = _session()
    out = TOOLS["update_board"].fn(s, suspect="farms", status="open", evidence_ids=[], note="Not tested yet.")
    assert s.board["farms"].note == "Not tested yet." and "note_removed" not in out


# --------------------------------------------------------------------------- m1 finite counts / m4 grammar


def test_counts_shown_skip_tests_that_could_not_run(monkeypatch):
    monkeypatch.setattr(gather, "FETCHERS", {**gather.FETCHERS, "power": lambda site, variables, catalog, start, end: {
        v.id: _synthetic(start, end).rename(v.id) for v in variables}})
    s = _session()
    s.ledger.add_test(_record("t1", math.nan, slope=None, too_short=True))
    got = data.get_series(s, var_id="t2m")
    trend = data.trend_test(s, series_id=got["series_id"])
    assert trend["n_tests_so_far"] == 1
    out = TOOLS["update_board"].fn(s, suspect="x", status="open", evidence_ids=[], note="")
    assert out["n_tests"] == 1
    data.get_series(s, var_id="precip")
    corr = analysis.correlate(s, series_a="t2m:2003-2024", series_b="precip:2003-2024", max_lag=0)
    assert corr["n_tests_so_far"] == 2


def test_downgrade_reason_is_singular_for_one_test():
    ledger = Ledger()
    ledger.add_test(_record("t1", 0.2))
    board = board_mod.apply_update({}, {"suspect": "s", "status": "supported", "evidence_ids": ["t1"], "note": ""}, ledger)
    assert board["s"].downgraded == "fails correction over 1 test"
    ledger.add_test(_record("t2", 0.3))
    assert board_mod.evaluate(board, ledger)["s"].downgraded == "fails correction over 2 tests"


# --------------------------------------------------------------------------- I-8 satellite layer id


def test_satellite_picture_maps_the_catalog_layer_id(monkeypatch):
    def fake(lat, lon, years, tags):
        return {
            "layer": thennow.DEFAULT_LAYER, "bbox": [1, 2, 3, 4], "status": "visual_only",
            "before": {"year": 2003, "url": "http://b"}, "after": {"year": 2024, "url": "http://a"},
        }

    monkeypatch.setattr(thennow, "then_and_now", fake)
    s = _session()
    out = context.satellite_picture(s)
    assert s.map[0]["layer_id"] == "true_colour"
    assert out["layer_id"] == "true_colour"


# --------------------------------------------------------------------------- T7 show_layer


def test_show_layer_compares_years_as_numbers():
    s = _session()
    assert mapping.show_layer(s, "true_colour", year=999)["status"] == "rejected"
    assert mapping.show_layer(s, "true_colour", year=2010)["status"] == "shown"


def test_show_layer_ongoing_layers_end_this_year():
    s = _session()
    assert mapping.show_layer(s, "true_colour", year=2999)["status"] == "rejected"
    assert mapping.show_layer(s, "true_colour", date="2999-01-01")["status"] == "rejected"


def test_show_layer_rejects_a_date_and_a_year_together():
    s = _session()
    out = mapping.show_layer(s, "true_colour", date="2010-07-01", year=2010)
    assert out["status"] == "rejected" and s.map == []


def test_case_layers_need_a_clean_site_id():
    assert mapping._case_layers(_session(site_id="lake_mead\n")) == {}


# --------------------------------------------------------------------------- m5 model limits


def test_models_have_a_timeout_and_retries(monkeypatch, tmp_path):
    from app.detective.model import make_chat_model

    monkeypatch.setenv("LLM_API_KEY", "x")
    m = make_chat_model()
    assert m.default_request_timeout == 60 and m.max_retries == 2
    monkeypatch.delenv("LLM_API_KEY")
    f = tmp_path / "key"
    f.write_text("x")
    monkeypatch.setenv("OPENROUTER_KEY_FILE", str(f))
    m = make_chat_model()
    assert m.request_timeout == 60 and m.max_retries == 2


# --------------------------------------------------------------------------- T9


def test_tool_error_prefix_is_shared():
    from app.detective import events, nodes

    assert events.TOOL_ERROR_PREFIX is nodes.TOOL_ERROR_PREFIX


def test_tests_never_touch_the_real_detective_db():
    import os

    from app.detective.persistence import DEFAULT_DB

    assert os.environ.get("DETECTIVE_DB") and os.environ["DETECTIVE_DB"] != str(DEFAULT_DB)
