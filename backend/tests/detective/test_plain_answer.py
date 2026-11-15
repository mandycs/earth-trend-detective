"""The answer in everyday words: the template sentences, the next questions, and the report fields they read."""

from app.detective import plain
from app.detective.nodes import check, template_answer
from app.detective.wording import cause_problems
from app.explain.numbers import extract_numbers

WATER = {
    "id": "grace_tws",
    "label": "Total water stored",
    "unit": "cm",
    "verdict": "real",
    "direction": "down",
    "sen_slope_per_decade": -6.47,
    "ci_low": -8.0,
    "ci_high": -5.0,
    "years_needed": None,
    "residual_pct_non_climate": 77.5,
    "residual_pct_range": [60.0, 85.0],
    "everyday": {"litres_per_m2_per_decade": -65, "litres_per_m2_over_period": -136, "over_years": 21, "way": "less"},
    "residual_everyday": {"in_ten_not_explained": 8, "share_word": "most", "out_of": "ten"},
}


def _report(**extra):
    report = {
        "variables": [WATER],
        "start": 2003,
        "end": 2024,
        "figures": [-6.47, -8.0, -5.0, 77.5, 60.0, 85.0, -65, -136, 21, 8, 300.0, 4],
        "percent_figures": [77.5],
        "n_tests": 4,
        "not_measured": [],
        "asked_not_measured": [],
        "data_cells": [{"label": "Total water stored", "source": "grace", "size_km": 300.0}],
        "everyday": [WATER["everyday"], WATER["residual_everyday"]],
        "comparisons": [],
        "land_cover": [],
        "question": "Is the water going down?",
    }
    return report | extra


def test_template_leads_with_the_change_in_litres_and_the_plain_share():
    text, figures = template_answer(_report())
    assert text.startswith("Total water stored here is going down: about 6.5 cm per decade"), text
    assert "about 65 litres of water on each square metre" in text
    assert "The weather we measured doesn't explain most of it, about 8 in 10 parts" in text
    assert "a clue, not proof" in text and "about 300 km across" in text
    assert "tests run" not in text and "data cell" not in text
    ok, _, rejected = check(text, _report())
    assert ok, (text, rejected)


def test_template_says_in_ten_without_most_when_a_model_disagrees():
    row = WATER | {"residual_everyday": {"in_ten_not_explained": 8, "out_of": "ten"}}
    report = _report(variables=[row], everyday=[row["everyday"], row["residual_everyday"]])
    text, _ = template_answer(report)
    assert "most" not in text
    assert "About 8 in 10 parts of that change are not explained by the weather we measured" in text
    ok, _, rejected = check(text, report)
    assert ok, (text, rejected)


def test_a_likely_trend_is_said_as_probably():
    row = WATER | {"verdict": "likely", "residual_pct_non_climate": None, "residual_everyday": None}
    text = plain.change_sentence(row)
    assert "probably going down" in text and "not sure yet" in text
    assert "litres" not in text  # the equivalent goes with a real trend only


def test_temperature_equivalent_over_the_years_tested():
    row = {
        "label": "Daytime ground temperature (annual mean of monthly values)",
        "unit": "°C",
        "verdict": "real",
        "direction": "up",
        "sen_slope_per_decade": 0.62,
        "everyday": {"change_over_period_c": 1.4, "over_years": 23, "way": "warmer"},
    }
    assert plain.change_sentence(row) == (
        "Daytime ground temperature here is going up: about 0.62 °C per decade, about 1.4 °C warmer over 23 years."
    )


def _cause(q):
    return cause_problems(q)


def test_next_questions_point_to_what_was_not_tested():
    board = [{"id": "irrigation", "label": "Irrigation", "status": "trend_only"}]
    listed = [
        {"id": "grace_tws", "label": "Total water stored", "available": True},
        {"id": "precip_upstream", "label": "Rainfall and snowfall upstream", "available": True},
        {"id": "snow_cover", "label": "Snow cover", "available": False},
    ]
    out = plain.next_questions(_report(), board, {"grace_tws"}, listed, _cause)
    assert out == [
        "Is it still going down in recent years?",
        "Can we test the link with irrigation?",
        "What about rainfall and snowfall upstream here?",
    ]
    for q in out:
        assert not extract_numbers(q) and not cause_problems(q) and q.endswith("?")


def test_next_questions_skip_recent_when_another_period_was_tested():
    row = WATER | {"other_periods": [{"years": [2014, 2024], "verdict": "real", "direction": "down"}]}
    out = plain.next_questions(_report(variables=[row]), [], {"grace_tws"}, [], _cause)
    assert "Is it still going down in recent years?" not in out
    assert out == ["Is a place nearby changing the same way?"]


def test_next_questions_drop_names_with_figures_or_cause_words():
    board = [{"id": "a", "label": "47 new wells", "status": "hint"}]
    out = plain.next_questions(_report(), board, {"grace_tws"}, [], _cause)
    assert all("47" not in q for q in out)


def test_next_questions_offer_the_weather_split_for_an_impact_without_one():
    row = WATER | {"residual_pct_non_climate": None, "residual_everyday": None}
    out = plain.next_questions(_report(variables=[row]), [], {"grace_tws"}, [], _cause)
    assert "What happens if we take the weather out of it?" in out


def test_nothing_real_gives_only_safe_generic_questions():
    out = plain.next_questions(_report(variables=[]), [], set(), [], _cause)
    assert out == []
