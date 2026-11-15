"""The prompts carry the instructions the evaluation of recorded runs asked for."""

from app.detective.prompt import CONCLUDE_PROMPT, SYSTEM_PROMPT


def _flat(text: str) -> str:
    return " ".join(text.split()).lower()


SYSTEM = _flat(SYSTEM_PROMPT)
CONCLUDE = _flat(CONCLUDE_PROMPT)


def test_system_prompt_asks_for_expects_and_rules_out_the_opposite_direction():
    assert "expects (up or down" in SYSTEM
    assert 'if rain went up, "less rain" is ruled out' in SYSTEM


def test_conclude_prompt_says_what_could_not_be_measured():
    assert "asked_not_measured" in CONCLUDE
    assert "say plainly that it could not be measured here and why" in CONCLUDE


def test_conclude_prompt_answers_why_with_the_board_not_a_cause():
    assert "if the question asks why, never give a reason in your own words" in CONCLUDE
    assert "using its board status" in CONCLUDE


def test_conclude_prompt_makes_the_cell_mandatory():
    assert "if data_cells is not empty" in CONCLUDE and "always say how big the cell is" in CONCLUDE


def test_retry_of_a_why_question_points_to_the_board():
    from app.detective.prompt import retry_request

    assert "why question" in retry_request(["x"], why=True)
    assert "why question" not in retry_request(["x"])


def test_system_prompt_answers_the_facet_of_the_question():
    assert '"still", "recently"' in SYSTEM and "trend_test with start=2014" in SYSTEM
    assert "compare the same variable over two periods (a: 2003-2013, b: 2014-2024)" in SYSTEM
    assert '"fast", "faster"' in SYSTEM
    assert '"groundwater"' in SYSTEM and "grace_tws" in SYSTEM and "soil_moisture" in SYSTEM


def test_system_prompt_asks_for_two_suspects_that_are_reasons_with_their_own_series():
    assert "suspects are possible reasons for the change" in SYSTEM
    assert "never the changing variable itself" in SYSTEM
    assert "open at least 2 suspects" in SYSTEM and "each with its own series" in SYSTEM


def test_system_prompt_retries_a_removed_note():
    assert "if update_board returns note_removed, call update_board again" in SYSTEM
