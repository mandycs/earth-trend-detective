"""The two prompts: the product name, and no figure the model could repeat as its own."""

import re

from app.detective.prompt import CONCLUDE_PROMPT, SYSTEM_PROMPT

# Structural counts only: the answer length limit and an empty test count.
_ALLOWED = {"3", "0"}  # "n_tests is 0" is a field check, not a figure


def test_prompts_carry_no_figures():
    for prompt in (SYSTEM_PROMPT, CONCLUDE_PROMPT):
        # list markers ("1. ") are structure, not figures
        body = re.sub(r"(?m)^\d+\. ", "", prompt)
        assert set(re.findall(r"\d+(?:[.,]\d+)?", body)) <= _ALLOWED, prompt


def test_persona_is_alibi():
    assert SYSTEM_PROMPT.startswith("You are Alibi")
    assert "Alibi" in CONCLUDE_PROMPT
    assert "Earth Trend Detective" not in SYSTEM_PROMPT + CONCLUDE_PROMPT
