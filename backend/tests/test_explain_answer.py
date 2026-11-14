"""The investigation's answer block: built in code from the report, no LLM."""

from __future__ import annotations

from app.explain.answer import build_answer
from app.explain.narrative import explain_report

WATER = {
    "id": "grace_tws",
    "label": "Total water stored",
    "unit": "cm",
    "sen_slope_per_decade": -6.47,
    "verdict": "real",
    "direction": "down",
    "residual_pct_non_climate": 83.7,
    "residual_pct_range": [53.6, 83.7],
}
HEAT = {
    "id": "t2m",
    "label": "Air temperature",
    "unit": "°C",
    "sen_slope_per_decade": 0.598,
    "verdict": "real",
    "direction": "up",
}
RAIN = {
    "id": "precip",
    "label": "Rainfall",
    "unit": "mm/day",
    "sen_slope_per_decade": -0.048,
    "verdict": "unknown",
    "direction": "down",
}
LIKELY = {**HEAT, "id": "t2m_up", "label": "Air temperature upstream", "verdict": "likely"}


def report(*rows, focus=None, years=(2003, 2024)):
    out = {"name": "Lake Mead", "years": list(years), "variables": list(rows)}
    if focus is not None:
        out["focus_ids"] = list(focus)
    return out


def test_real_trend_with_climate_split_leads_with_the_range():
    answer = build_answer(report(HEAT, WATER, RAIN, focus=["grace_tws", "precip"]))
    assert answer == {
        "headline": "Total water stored is going down, for real.",
        "verdict": "real",
        "direction": "down",
        "figure": "54–84%",
        "figure_label": "of the change in total water stored is not explained by climate, depending on the climate model",
        "note": "A clue, not proof.",
    }


def test_single_share_when_the_range_collapses():
    row = {**WATER, "residual_pct_range": [83.6, 83.7]}
    answer = build_answer(report(row, focus=["grace_tws"]))
    assert answer["figure"] == "84%"
    assert answer["figure_label"] == "of the change in total water stored is not explained by climate"


def test_trend_without_split_shows_the_slope_with_its_sign():
    answer = build_answer(report(HEAT, focus=["t2m"]))
    assert answer["headline"] == "Air temperature is going up, for real."
    assert answer["figure"] == "+0.60 °C per decade"
    assert answer["figure_label"] == "Air temperature, 2003–2024"
    assert answer["note"] is None


def test_likely_trend_says_so():
    answer = build_answer(report(LIKELY, focus=["t2m_up"]))
    assert answer["headline"] == "Air temperature upstream is probably going up, but we are not sure yet."
    assert answer["verdict"] == "likely"


def test_unknown_trend_has_no_figure():
    answer = build_answer(report(RAIN, focus=["precip"]))
    assert answer == {
        "headline": "We can't tell yet whether rainfall is changing.",
        "verdict": "unknown",
        "direction": None,
        "figure": None,
        "figure_label": None,
        "note": None,
    }


def test_no_focus_falls_back_to_the_top_trend():
    answer = build_answer(report(RAIN, HEAT))
    assert answer["headline"] == "Air temperature is going up, for real."


def test_no_variables_gives_no_answer():
    assert build_answer(report()) is None


def test_explain_report_attaches_the_answer_only_for_a_question():
    with_question = explain_report(report(HEAT, WATER), None, "Is the water going down?").to_dict()
    assert with_question["answer"]["headline"]
    without = explain_report(report(HEAT, WATER), None).to_dict()
    assert "answer" not in without


def test_a_question_paragraph_is_held_to_three_sentences():
    from app.explain.validator import validate_narrative

    four = (
        "Total water stored is going down. It is real. Rainfall: we can't tell yet. "
        "Air temperature is going up."
    )
    base = report(HEAT, WATER, RAIN)
    assert not [r for r in validate_narrative(four, base).rejected if r.kind == "length"]
    asked = {**base, "question": "Is the water going down?"}
    assert [r for r in validate_narrative(four, asked).rejected if r.kind == "length"]
