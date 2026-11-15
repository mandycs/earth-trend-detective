"""Detective wording: the link-words added to the cause list, and honest text no longer over-rejected."""

import pytest

from app.detective.wording import cause_problems

WATER_USE = [{"id": "water use", "label": "Water use"}]
RESERVOIR = [{"id": "reservoir releases", "label": "Reservoir releases"}]


@pytest.mark.parametrize(
    "sentence",
    [
        "Irrigation accounts for the drop in water stored.",
        "Farming account for most of the change.",
        "The drop in water stored is linked to pumping.",
        "Pumping is behind the drop in water stored.",
        "Wells are behind it.",
        "The drop is attributable to farms.",
        "Farms contributed to the drop in water stored.",
        "Less rain contributes to the change.",
    ],
)
def test_link_words_claim_a_cause(sentence):
    assert cause_problems(sentence), sentence


@pytest.mark.parametrize(
    "sentence",
    [
        "Its own trend is real, but no test links it to Total water stored.",
        "Rainfall: TREND REAL · NOT LINKED.",
        "Rainfall is not linked to the change by any test we ran.",
        "The reservoir behind the dam dried up.",
        "The lake is behind the dam.",
        "We can't tell yet because the record is short.",
        "We can't tell yet because of the short record.",
        "The trend is unclear due to missing data.",
        "We can't say because one data cell covers about 300 km.",
    ],
)
def test_honest_sentences_pass(sentence):
    assert cause_problems(sentence) == [], sentence


@pytest.mark.parametrize(
    ("sentence", "suspects"),
    [
        ("The water dried up in the lake each summer.", WATER_USE),
        ("Water drains from the basin each spring.", WATER_USE),
        ("Use the map: the reservoir dried up after the wet years.", RESERVOIR),
    ],
)
def test_words_from_suspect_labels_are_not_actors_when_they_are_places_or_plain_words(sentence, suspects):
    assert cause_problems(sentence, suspects) == [], sentence


@pytest.mark.parametrize(
    "sentence",
    [
        "Water stored fell because farmers pump it.",
        "Water stored fell because the farms grew.",
        "The drop is due to wells.",
        "Irrigation is draining the water stored.",
        "Dams are draining the river.",
    ],
)
def test_cause_claims_about_the_world_are_still_rejected(sentence):
    assert cause_problems(sentence), sentence


def test_a_suspect_name_is_still_an_actor():
    assert cause_problems("Orchard pumping drains the aquifer.", [{"id": "orchard pumping", "label": "Orchard pumping"}])
