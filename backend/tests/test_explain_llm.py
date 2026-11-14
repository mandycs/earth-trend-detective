from unittest.mock import MagicMock

import anthropic
import httpx2
import pytest

from app.explain import llm as llm_module
from app.explain.llm import AnthropicLLM, make_llm
from app.explain.narrative import explain_report
from app.explain.route import clean_ids, keyword_route, route_question
from tests.explain_fakes import fake_client, fake_response, json_text, lake_mead_report
from tests.test_explain_validator import GOOD

CHOICES = {"grace_tws": "Total water stored", "precip": "Rainfall", "t2m": "Air temperature", "soil_moisture": "Topsoil moisture"}


def test_good_llm_text_is_returned():
    client = fake_client(GOOD)
    result = explain_report(lake_mead_report(), AnthropicLLM(client))
    assert result.source == "llm"
    assert result.text == GOOD
    assert result.validation.ok
    kwargs = client.beta.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-sonnet-5-5"
    assert kwargs["output_config"] == {"effort": "low"}
    assert kwargs["fallbacks"] == "default"
    assert "temperature" not in kwargs


def test_retry_with_errors_then_success():
    bad = GOOD.replace("6.5 cm", "37 cm")
    client = fake_client(bad, GOOD)
    result = explain_report(lake_mead_report(), AnthropicLLM(client))
    assert result.source == "llm"
    assert len(result.attempts) == 1
    retry_prompt = client.beta.messages.create.call_args_list[1].kwargs["messages"][0]["content"]
    assert "was rejected" in retry_prompt and "'37' is not a number in the report" in retry_prompt


def test_two_bad_drafts_fall_back_to_template():
    bad = GOOD.replace("is going down", "is rising")
    client = fake_client(bad, bad)
    result = explain_report(lake_mead_report(), AnthropicLLM(client))
    assert client.beta.messages.create.call_count == 2
    assert result.source == "template"
    assert result.validation.ok
    assert [a.rejected[0].kind for a in result.attempts] == ["direction", "direction"]
    assert result.to_dict()["rejected_attempts"][0]["ok"] is False


def test_refusal_or_truncation_falls_back():
    client = MagicMock()
    client.beta.messages.create.return_value = fake_response(GOOD, stop_reason="max_tokens")
    assert explain_report(lake_mead_report(), AnthropicLLM(client)).source == "template"


def test_api_error_falls_back_without_crash():
    client = MagicMock()
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    client.beta.messages.create.side_effect = anthropic.APIConnectionError(request=request)
    result = explain_report(lake_mead_report(), AnthropicLLM(client))
    assert result.source == "template"


def test_no_llm_is_template():
    result = explain_report(lake_mead_report(), None)
    assert result.source == "template"
    assert result.validation.ok


def test_empty_key_gives_no_llm(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setattr(llm_module, "load_dotenv", lambda *_a, **_k: False)
    assert make_llm() is None


def test_route_uses_enum_schema_and_haiku():
    client = fake_client(json_text({"ids": ["grace_tws", "precip"]}))
    result = route_question("Is the lake drying up?", CHOICES, AnthropicLLM(client))
    assert result.ids == ("grace_tws", "precip") and result.source == "llm"
    kwargs = client.beta.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-haiku-5-5"
    assert "fallbacks" not in kwargs
    fmt = kwargs["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["schema"]["properties"]["ids"]["items"]["enum"] == [*CHOICES, "unknown"]


def test_route_drops_ids_outside_enum():
    client = fake_client(json_text({"ids": ["water_area", "grace_tws", "grace_tws", "unknown"]}))
    assert route_question("lake?", CHOICES, AnthropicLLM(client)).ids == ("grace_tws",)
    assert clean_ids(["made_up"], tuple(CHOICES)) == ("unknown",)
    assert clean_ids("not a list", tuple(CHOICES)) == ("unknown",)


def test_route_bad_json_falls_back_to_keywords():
    result = route_question("Is the lake drying up?", CHOICES, AnthropicLLM(fake_client("not json")))
    assert result.source == "template"
    assert result.ids == ("grace_tws", "precip", "soil_moisture")


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Is it getting hotter?", ("t2m",)),
        ("Is there less rain?", ("precip",)),
        ("What about the economy?", ("unknown",)),
    ],
)
def test_keyword_route(question, expected):
    assert keyword_route(question, CHOICES) == expected
