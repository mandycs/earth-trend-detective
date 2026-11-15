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
    assert '"still", "recently"' in SYSTEM and "trend_test with start set about ten years before the last year" in SYSTEM
    assert "variable over two periods (the earlier years against the recent years)" in SYSTEM
    assert '"fast", "faster"' in SYSTEM
    assert '"groundwater"' in SYSTEM and "grace_tws" in SYSTEM and "soil_moisture" in SYSTEM


def test_system_prompt_asks_for_two_suspects_that_are_reasons_with_their_own_series():
    assert "suspects are possible reasons for the change" in SYSTEM
    assert "never the changing variable itself" in SYSTEM
    assert "open at least two suspects" in SYSTEM and "each with its own series" in SYSTEM


def test_system_prompt_retries_a_removed_note():
    assert "if update_board returns note_removed, call update_board again" in SYSTEM


def test_system_prompt_uses_the_automatic_map_and_the_cases_layers():
    assert "profile_place already flies the map to the place" in SYSTEM
    assert "show_layer without a date shows the last year of the period you tested" in SYSTEM
    assert "trend_lst_day" in SYSTEM and "before_after" in SYSTEM and "case_layers" in SYSTEM


def test_tool_descriptions_tell_the_model_about_the_automatic_map():
    from app.detective.tools import TOOLS

    assert "flies the map to the place" in TOOLS["profile_place"].description
    assert "last year of the period you tested" in TOOLS["show_layer"].description
