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
