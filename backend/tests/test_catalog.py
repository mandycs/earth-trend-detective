import pytest

from app.catalog import Variable, load_catalog, variables_for_site


def test_catalog_has_ten_unique_variables():
    catalog = load_catalog()
    assert len(catalog) == 10
    assert len({v.id for v in catalog}) == 10
    assert all(isinstance(v, Variable) for v in catalog)


def test_impact_drivers_reference_existing_driver_variables():
    catalog = load_catalog()
    driver_ids = {v.id for v in catalog if v.role == "driver"}
    for v in catalog:
        if v.role == "impact":
            assert v.drivers, f"{v.id} has no drivers"
            assert set(v.drivers) <= driver_ids, f"{v.id} references unknown drivers"
        else:
            assert v.drivers == ()


def test_variables_for_site_filters_by_tags():
    catalog = load_catalog()
    ids = {v.id for v in variables_for_site(catalog, ["snow", "mountain"])}
    assert "snow_cover" in ids
    assert "t2m" in ids  # applies_to: any
    assert "ndvi" not in ids


def test_invalid_role_is_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "variables:\n"
        "  - {id: x, label: X, role: weird, source: power, dataset: d, band: B,"
        " units: u, scale: 1, offset: 0, temporal: monthly, tags: [], applies_to: [any], drivers: []}\n"
    )
    with pytest.raises(ValueError, match="role"):
        load_catalog(bad)
