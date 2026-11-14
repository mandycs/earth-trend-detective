import pytest

from app.explain.numbers import allowed_numbers, extract_numbers, find_match
from app.explain.template import template_narrative
from app.explain.validator import validate_narrative
from tests.explain_fakes import SITES_DIR, lake_mead_report

GOOD = (
    "Total water stored at Lake Mead is going down, by about 6.5 cm per decade. "
    "This change is real, not just chance. "
    "About 84% of that drop is not explained by climate. That is a lead, not proof."
)


def kinds(result) -> list[str]:
    return [r.kind for r in result.rejected]


@pytest.fixture
def report() -> dict:
    return lake_mead_report()


def test_extracts_signed_decimals_percentages_and_words():
    found = extract_numbers("It fell −6.5 cm, about 84% or eighty-four percent, from 2003-2024, Step 1.")
    values = [(n.value, n.percent) for n in found]
    assert values == [(-6.5, False), (84.0, True), (84.0, True), (2003.0, False), (2024.0, False)]


def test_extracts_fraction_without_double_counting():
    found = extract_numbers("About three quarters of it.")
    assert [(n.value, n.fraction) for n in found] == [(75.0, True)]


def test_accepts_good_text(report):
    result = validate_narrative(GOOD, report)
    assert result.ok, result.rejected
    assert result.checked_numbers == ("6.5", "84%")


@pytest.mark.parametrize("figure", ["−6.47", "6.47", "−6", "6.5", "−6.5"])
def test_accepts_rounded_slope(report, figure):
    text = GOOD.replace("6.5 cm", f"{figure} cm")
    assert validate_narrative(text, report).ok


@pytest.mark.parametrize("pct", ["83.7%", "84%", "80%", "84 percent", "eighty-four percent"])
def test_accepts_rounded_percentage(report, pct):
    assert validate_narrative(GOOD.replace("84%", pct), report).ok


def test_rejects_invented_number(report):
    result = validate_narrative(GOOD.replace("6.5 cm", "9 cm"), report)
    assert kinds(result) == ["number"]
    assert "'9'" in result.rejected[0].detail


def test_rejects_unit_conversion(report):
    # 84% written as a fraction, and cm converted to mm
    assert "number" in kinds(validate_narrative(GOOD.replace("84%", "0.84"), report))
    assert "number" in kinds(validate_narrative(GOOD.replace("6.5 cm", "65 mm"), report))


def test_percent_must_match_a_percentage(report):
    # 6.5 exists as a slope, not as a share
    assert kinds(validate_narrative(GOOD.replace("84%", "6.5%"), report)) == ["number"]


def test_accepts_climate_share_complement(report):
    text = GOOD + " The other 16% is climate."
    assert validate_narrative(text, report).ok


def test_rejects_wrong_direction(report):
    text = GOOD.replace("is going down", "is rising")
    result = validate_narrative(text, report)
    assert kinds(result) == ["direction"]


def test_direction_follows_pronoun_into_next_sentence(report):
    text = GOOD.replace("This change is real, not just chance.", "It is climbing fast.")
    assert "direction" in kinds(validate_narrative(text, report))


def test_mixed_clause_directions_are_fine(report):
    text = GOOD + " Total water stored is falling, while air temperature is rising."
    assert validate_narrative(text, report).ok


@pytest.mark.parametrize(
    "sentence",
    ["Rainfall is definitely falling.", "Topsoil moisture is clearly drying.", "Rainfall is down for sure."],
)
def test_rejects_certainty_for_unknown_verdict(report, sentence):
    assert "certainty" in kinds(validate_narrative(GOOD + " " + sentence, report))


def test_hedged_unknown_is_fine(report):
    text = GOOD.replace("That is a lead", "Rainfall: we can't tell yet. That is a lead")
    assert validate_narrative(text, report).ok


@pytest.mark.parametrize("bad", ["This proves people drained it.", "It is proof of pumping."])
def test_rejects_proof_language(report, bad):
    assert "proof" in kinds(validate_narrative(GOOD + " " + bad, report))


def test_rejects_unhedged_cause(report):
    assert "causal" in kinds(validate_narrative(GOOD + " The drop is caused by pumping.", report))
    assert validate_narrative(GOOD + " The drop could be caused by pumping.", report).ok


@pytest.mark.parametrize("word", ["Mann-Kendall", "FDR", "p-value", "statistically significant", "residual"])
def test_rejects_jargon(report, word):
    assert "jargon" in kinds(validate_narrative(GOOD + f" We used {word}.", report))


def test_requires_lead_not_proof_when_share_exists(report):
    text = GOOD.replace(" That is a lead, not proof.", "")
    assert kinds(validate_narrative(text, report)) == ["lead"]


def test_rejects_empty_and_too_long(report):
    assert kinds(validate_narrative("  ", report)) == ["length"]
    assert "length" in kinds(validate_narrative(" ".join([GOOD] * 3), report))


def test_find_match_ignores_zero_rounding(report):
    allowed = allowed_numbers(report)
    zero = extract_numbers("0 cm")[0]
    assert find_match(zero, allowed) is None


@pytest.mark.parametrize("site_id", ["lake_mead", "aletsch", "donana", "_example"])
def test_template_passes_own_validator(site_id):
    import json

    path = SITES_DIR / site_id / "site.json"
    if not path.is_file():
        pytest.skip("no site.json")
    report = json.loads(path.read_text(encoding="utf-8"))
    text = template_narrative(report)
    result = validate_narrative(text, report)
    assert result.ok, (text, result.rejected)
    assert 2 <= text.count(". ") + 1 <= 6


def test_template_lake_mead_wording(report):
    text = template_narrative(report)
    assert text.startswith("Total water stored is going down (−6.5 cm per decade).")
    assert "About 84% of the change in total water stored is not explained by climate" in text
    assert "a lead, not proof" in text
    assert text.index("This change is real") < text.index("air temperature")
