"""The final answer: says the data cell when the place is smaller (item 8), says what could not be
measured when the question's variable is missing (item 4), and the code's own answer carries the
cell and the board (item 5)."""

import numpy as np
import pandas as pd
import pytest

from app import gather
from app.catalog import load_catalog
from app.detective.ledger import Ledger
from app.detective.nodes import check, narrate, template_answer
from app.detective.place import Place
from app.detective.report import ledger_report
from app.detective.session import Session
from app.detective.tools import data

SMALL = Place(lat=37.0, lon=-4.5, bbox=(-4.6, 36.9, -4.4, 37.1), tags=("agriculture",))  # ~18 x 22 km
BIG = Place(lat=37.0, lon=-4.5, bbox=(-5.5, 36.0, -3.5, 38.0), tags=("agriculture",))  # ~180 x 220 km


def _synthetic(start=2003, end=2024, slope_per_year=0.05):
    idx = pd.date_range(f"{start}-01-01", f"{end}-12-01", freq="MS")
    t = np.arange(idx.size) / 12.0
    rng = np.random.default_rng(0)
    return pd.Series(10 + 5 * np.sin(2 * np.pi * idx.month / 12) + slope_per_year * t + rng.normal(0, 0.2, idx.size),
                     index=idx)


@pytest.fixture
def power(monkeypatch):
    def fetch(site, variables, catalog, start, end):
        return {v.id: _synthetic(start, end).rename(v.id) for v in variables}

    monkeypatch.setattr(gather, "FETCHERS", {**gather.FETCHERS, "power": fetch})


def _tested(place=SMALL, var_id="t2m") -> Session:
    s = Session(ledger=Ledger(), place=place, catalog=load_catalog())
    data.trend_test(s, series_id=data.get_series(s, var_id=var_id)["series_id"])
    return s


# --------------------------------------------------------------------------- item 8: the data cell


def test_report_lists_the_data_cells_bigger_than_the_place(power):
    report = ledger_report(_tested(), "Is it getting warmer?")
    assert report["data_cells"] == [{"label": "Air temperature", "source": "power", "size_km": 50.0}]
    assert 50.0 in report["figures"]


def test_no_data_cell_when_the_place_is_bigger_than_the_cell(power):
    report = ledger_report(_tested(place=BIG), "Is it getting warmer?")
    assert report["data_cells"] == []


def test_answer_must_say_the_cell_when_the_place_is_smaller(power):
    report = ledger_report(_tested(), "Is it getting warmer?")
    ok, _, rejected = check("Air temperature went up from 2003 to 2024.", report)
    assert not ok and any("data cell" in r for r in rejected), rejected
    ok, _, rejected = check("Air temperature went up from 2003 to 2024; one value covers a cell of about 50 km.", report)
    assert ok, rejected


def test_answer_need_not_say_a_cell_for_a_big_place(power):
    report = ledger_report(_tested(place=BIG), "Is it getting warmer?")
    ok, _, rejected = check("Air temperature went up from 2003 to 2024.", report)
    assert ok, rejected


# --------------------------------------------------------------------------- item 4: what could not be measured


def _with_unavailable_ndvi(s: Session) -> Session:
    s.ledger.remember("list_variables:{}", {"variables": [
        {"id": "t2m", "label": "Air temperature", "available": True},
        {"id": "ndvi", "label": "Plant greenness", "available": False,
         "reason": "not_available_here: only precomputed for the solved cases"},
    ]})
    return s


def test_not_measured_includes_listed_variables_that_are_not_available_here(power):
    report = ledger_report(_with_unavailable_ndvi(_tested()), "Is it getting warmer?")
    assert {"label": "Plant greenness", "reason": "only precomputed for the solved cases"} in report["not_measured"]
    assert all(row["label"] != "Air temperature" for row in report["not_measured"])


def test_the_question_variable_that_could_not_be_measured_is_named(power):
    report = ledger_report(_with_unavailable_ndvi(_tested()), "Is it getting greener here?")
    assert report["asked_not_measured"] == ["Plant greenness"]
    plain = ledger_report(_with_unavailable_ndvi(_tested()), "Is it getting warmer?")
    assert plain["asked_not_measured"] == []


def test_answer_must_say_the_question_variable_could_not_be_measured(power):
    report = ledger_report(_with_unavailable_ndvi(_tested()), "Is it getting greener here?")
    cell = "one value covers a cell of about 50 km"
    ok, _, rejected = check(f"Air temperature went up from 2003 to 2024; {cell}.", report)
    assert not ok and any("could not be measured" in r for r in rejected), rejected
    ok, _, rejected = check(
        f"Plant greenness could not be measured here. Air temperature went up from 2003 to 2024; {cell}.", report
    )
    assert ok, rejected


def test_template_says_what_could_not_be_measured_and_passes_the_check(power):
    report = ledger_report(_with_unavailable_ndvi(_tested()), "Is it getting greener here?")
    text, _ = template_answer(report)
    assert "could not measure plant greenness" in text.lower(), text
    ok, _, rejected = check(text, report)
    assert ok, (text, rejected)


# --------------------------------------------------------------------------- item 5: the template and the rejections

BOARD = [
    {"id": "less rain", "label": "less rain", "status": "ruled_out", "downgraded": None, "note": ""},
    {"id": "irrigation", "label": "irrigation", "status": "hint", "downgraded": "x", "note": ""},
    {"id": "heat", "label": "warmer air", "status": "trend_only", "downgraded": "x", "note": ""},
]


def test_template_carries_the_cell_and_the_board(power):
    report = ledger_report(_tested(), "Why is it getting warmer?")
    text, figures = template_answer(report, BOARD)
    assert "50 km" in text, text
    assert "less rain is ruled out" in text and "irrigation is only a hint" in text, text
    assert "warmer air" in text
    ok, _, rejected = check(text, report, BOARD)
    assert ok, (text, rejected)
    assert "50" in figures


def test_template_skips_board_names_with_figures_or_cause_words(power):
    report = ledger_report(_tested(), "Why is it getting warmer?")
    board = [
        {"id": "a", "label": "47 new wells", "status": "hint", "note": ""},
        {"id": "b", "label": "drought caused by dams", "status": "hint", "note": ""},
    ]
    text, _ = template_answer(report, board)
    assert "47" not in text and "caused" not in text, text
    ok, _, rejected = check(text, report, board)
    assert ok, (text, rejected)


class _Narrator:
    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = 0

    def invoke(self, messages):
        from langchain_core.messages import AIMessage

        self.calls += 1
        return AIMessage(self.texts.pop(0))


def test_narrate_reports_why_each_try_was_rejected_without_the_models_words(power):
    report = ledger_report(_tested(), "Why is it getting warmer?")
    bad = "Air temperature went up 47 times because of farms."
    text, checked, figures, source, rejected = narrate(_Narrator([bad, bad, bad]), "Why?", report, BOARD)
    assert source == "template" and checked
    assert rejected and {"try", "kind", "reason"} <= set(rejected[0])
    kinds = {r["kind"] for r in rejected}
    assert {"number", "cause", "cell"} <= kinds, rejected
    assert all("47" not in r["reason"] and "farms" not in r["reason"] for r in rejected), rejected


def test_narrate_gives_a_why_question_a_third_try(power):
    report = ledger_report(_tested(), "Why is it getting warmer?")
    bad = "Air temperature went up because of farms; one value covers a cell of about 50 km."
    good = "Air temperature went up from 2003 to 2024; one value covers a cell of about 50 km."
    narrator = _Narrator([bad, bad, good])
    text, _, _, source, rejected = narrate(narrator, "Why is it getting warmer?", report, BOARD)
    assert source == "llm" and text == good and narrator.calls == 3
    assert rejected  # the earlier tries are still reported
