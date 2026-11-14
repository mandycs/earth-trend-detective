"""When the site report hides the non-climate % (and says why)."""

from app.site_report import residual_withheld_reason


def test_observed_variable_at_ordinary_site_is_reported():
    assert residual_withheld_reason("grace", ("water_body", "desert")) is None
    assert residual_withheld_reason("appeears", ("wetland",)) is None


def test_model_output_is_withheld():
    reason = residual_withheld_reason("gldas", ("water_body",))
    assert reason is not None and "model" in reason.lower()


def test_grace_at_snow_or_glacier_site_is_withheld():
    for tags in (("snow", "mountain"), ("glacier",)):
        reason = residual_withheld_reason("grace", tags)
        assert reason is not None and "snow" in reason.lower()


def test_modis_at_glacier_site_is_still_reported():
    assert residual_withheld_reason("appeears", ("snow", "glacier", "mountain")) is None
