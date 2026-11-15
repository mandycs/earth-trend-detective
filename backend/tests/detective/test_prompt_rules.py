"""The prompts carry the instructions the evaluation of recorded runs asked for."""

from app.detective.prompt import CONCLUDE_PROMPT, SYSTEM_PROMPT


def _flat(text: str) -> str:
    return " ".join(text.split()).lower()


SYSTEM = _flat(SYSTEM_PROMPT)
CONCLUDE = _flat(CONCLUDE_PROMPT)


def test_system_prompt_asks_for_expects_and_rules_out_the_opposite_direction():
    assert "expects (up or down" in SYSTEM
    assert 'if rain went up, "less rain" is ruled out' in SYSTEM
