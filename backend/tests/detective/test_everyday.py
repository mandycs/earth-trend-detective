"""Everyday equivalents: exact arithmetic of tool outputs, and the checker that ties them to the tools."""

import pytest

from app.detective import everyday
from app.detective.wording import everyday_rejections


# --------------------------------------------------------------------------- converters


def test_water_stored_cm_becomes_litres_per_square_metre():
    out = everyday.for_trend("grace_tws", "cm", -6.47, [2003, 2024])
    assert out["litres_per_m2_per_decade"] == -65  # 1 cm of water on one square metre = 10 litres
    assert out["over_years"] == 21
    assert out["litres_per_m2_over_period"] == -136  # -6.47 * 21 / 10 * 10
    assert out["way"] == "less"


def test_small_water_slopes_keep_one_decimal():
    out = everyday.for_trend("soil_moisture", "kg/m²", 0.43, [2003, 2023])
    assert out["litres_per_m2_per_decade"] == 0.4  # 1 kg/m² = 1 litre on one square metre
    assert out["litres_per_m2_over_period"] == 0.9
    assert out["way"] == "more"


def test_temperature_slope_over_the_whole_period():
    out = everyday.for_trend("lst_day", "°C", 0.62, [2001, 2024])
    assert out == {"change_over_period_c": 1.4, "over_years": 23, "way": "warmer"}


def test_greenness_gets_words_only():
    out = everyday.for_trend("ndvi", "NDVI", -0.012, [2001, 2024])
    assert out == {"way": "browner"}
    assert everyday.for_trend("ndvi_gibs", "NDVI", 0.01, [2001, 2024]) == {"way": "greener"}


@pytest.mark.parametrize("slope", [None, 0.0])
def test_no_slope_no_everyday(slope):
    assert everyday.for_trend("grace_tws", "cm", slope, [2003, 2024]) is None


def test_other_variables_get_nothing():
    assert everyday.for_trend("precip", "mm/day", 0.1, [2001, 2024]) is None
    assert everyday.for_trend("grace_tws", "cm", -1.0, None) is None


def test_land_cover_share_in_ten():
    row = {"class": "Croplands", "before_pct": 12.3, "after_pct": 78.4, "change_points": 66.1}
    out = everyday.with_land_cover_everyday(row)
    assert out["everyday"] == {"in_ten_before": 1, "in_ten_after": 8, "out_of": "ten", "class": "Croplands"}
    assert "everyday" not in row  # a new copy


def test_land_cover_share_under_one_in_ten_is_left_out():
    out = everyday.with_land_cover_everyday({"class": "Urban", "before_pct": 3.0, "after_pct": 41.0, "change_points": 38})
    assert out["everyday"] == {"in_ten_after": 4, "out_of": "ten", "class": "Urban"}


def test_residual_share_in_ten_and_most_only_when_the_whole_range_is_over_half():
    assert everyday.for_residual(77.5, [60.0, 85.0]) == {"in_ten_not_explained": 8, "share_word": "most", "out_of": "ten"}
    assert everyday.for_residual(77.5, [40.0, 85.0]) == {"in_ten_not_explained": 8, "out_of": "ten"}
    assert everyday.for_residual(30.0, None) == {"in_ten_not_explained": 3, "out_of": "ten"}
    assert everyday.for_residual(None, None) is None


def test_with_everyday_adds_a_block_to_a_trend_result():
    result = {"var_id": "grace_tws", "unit": "cm per decade", "slope_per_decade": -6.47, "years": [2003, 2024]}
    out = everyday.with_trend_everyday(result)
    assert out["everyday"]["litres_per_m2_per_decade"] == -65
    assert "everyday" not in result
    assert everyday.with_trend_everyday({"status": "not_available"}) == {"status": "not_available"}


# --------------------------------------------------------------------------- checker


REPORT = {
    "everyday": [
        {"litres_per_m2_per_decade": -65, "litres_per_m2_over_period": -136, "over_years": 21},
        {"in_ten_not_explained": 8, "share_word": "most"},
        {"in_ten_after": 4},
    ]
}


@pytest.mark.parametrize(
    "text",
    [
        "That is about 65 litres of water per square metre each decade.",
        "At that pace, about 136 litres per square metre over the period.",
        "About 8 in 10 of the drop is not explained by the weather we measured.",
        "Four out of ten of the box is now cropland.",
        "The weather we measured doesn't explain most of it — that's a clue, not proof.",
    ],
)
def test_everyday_figures_from_the_tools_pass(text):
    assert everyday_rejections(text, REPORT) == []


@pytest.mark.parametrize(
    "text",
    [
        "That is about 70 litres per square metre each decade.",  # not a tool's litres value
        "About 6 in 10 of the drop is not explained by the weather we measured.",  # not a tool's in-ten
        "seven out of ten of the land",
    ],
)
def test_everyday_figures_not_from_the_tools_are_rejected(text):
    found = everyday_rejections(text, REPORT)
    assert found and all(kind == "everyday" for kind, _ in found)


def test_a_share_in_ten_belongs_to_the_land_class_the_sentence_names():
    report = {
        "everyday": [
            {"in_ten_before": 9, "in_ten_after": 8, "class": "Barren"},
            {"in_ten_after": 1, "class": "Urban and built-up land"},
        ]
    }
    # 9 in ten is barren land's share, never the city's
    assert everyday_rejections("Built-up land grew from about 9 in ten parts of the area.", report)
    assert everyday_rejections("Barren ground went from 9 in ten parts to 8 in ten.", report) == []
    assert everyday_rejections("The city now covers about 1 in 10 parts; barren land is 8 in 10.", report) == []


def test_only_the_ten_of_a_share_is_hidden_from_the_figure_check():
    from app.detective.wording import mask_everyday

    assert mask_everyday("about 8 in 10 parts") == "about 8 in tenths parts"
    assert mask_everyday("it fell in 10 years") == "it fell in 10 years"


def test_land_cover_block_names_its_class():
    out = everyday.with_land_cover_everyday({"class": "Barren", "before_pct": 88.0, "after_pct": 80.0})
    assert out["everyday"]["class"] == "Barren"


def test_most_of_it_needs_a_tool_share_word():
    text = "The weather we measured doesn't explain most of it — that's a clue, not proof."
    assert everyday_rejections(text, {"everyday": [{"in_ten_not_explained": 5}]})
    assert everyday_rejections(text, REPORT) == []


def test_groundwater_needs_the_all_the_water_hedge_when_the_water_row_is_grace():
    from app.detective.wording import answer_rejections

    report = {"variables": [{"id": "grace_tws", "label": "Total water stored"}]}
    kinds = lambda t: [k for k, _ in answer_rejections(t, report)]  # noqa: E731
    assert "groundwater" in kinds("Yes, the groundwater here is going down.")
    assert "groundwater" not in kinds("Yes, all the water stored here, underground and on the surface, is going down.")
    assert "groundwater" not in kinds("The data counts all the water, not just groundwater.")
    assert "groundwater" not in [k for k, _ in answer_rejections("The groundwater is going down.", {"variables": []})]


def test_small_land_cover_move_is_not_shown_as_a_jump_in_tenths():
    # 93.3 -> 95.6 % rounds to "9 in ten -> 10 in ten", which reads bigger than 2.3 points.
    out = everyday.with_land_cover_everyday({"class": "Urban", "before_pct": 93.3, "after_pct": 95.6, "change_points": 2.3})
    assert out["everyday"] == {"in_ten_after": 10, "out_of": "ten", "class": "Urban", "move": "small"}


def test_land_cover_move_of_ten_points_keeps_both_tenths():
    out = everyday.with_land_cover_everyday({"class": "Barren", "before_pct": 12.0, "after_pct": 31.0, "change_points": 19.0})
    assert out["everyday"] == {"in_ten_before": 1, "in_ten_after": 3, "out_of": "ten", "class": "Barren"}
