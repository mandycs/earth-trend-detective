import dataclasses
import math

import numpy as np
import pandas as pd
import pytest

from app.catalog import load_catalog
from app.stats.sweep import VariableResult, run_sweep
from tests.test_stats_helpers import synthetic_series


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


def test_sweep_ranks_real_first_and_flags_noise(catalog):
    series = {
        "t2m": synthetic_series(0.6, sigma=0.3, seed=1),     # strong in sigma units
        "precip": synthetic_series(0.0, sigma=1.0, seed=2),  # pure noise
        "solar": synthetic_series(-1.0, sigma=1.0, seed=3),  # real, weaker in sigma
    }
    results = run_sweep(series, catalog)
    assert [r.id for r in results][:2] == ["t2m", "solar"]
    by_id = {r.id: r for r in results}
    assert by_id["t2m"].verdict == "real" and by_id["t2m"].direction == "up"
    assert by_id["solar"].verdict == "real" and by_id["solar"].direction == "down"
    assert by_id["precip"].verdict != "real"
    assert by_id["t2m"].label == "Air temperature"
    assert by_id["t2m"].unit == "°C"
    for r in results:
        assert r.q_value >= r.p_value
        assert r.years_needed is None and r.residual_pct_non_climate is None


def test_sweep_result_is_frozen_and_input_untouched(catalog):
    s = synthetic_series(1.0, seed=5)
    original = s.copy()
    results = run_sweep({"t2m": s}, catalog)
    pd.testing.assert_series_equal(s, original)
    with pytest.raises(dataclasses.FrozenInstanceError):
        results[0].verdict = "real"  # type: ignore[misc]
    assert isinstance(results[0], VariableResult)


def test_sweep_too_short_goes_last_and_is_excluded_from_fdr(catalog):
    series = {
        "t2m": synthetic_series(1.0, seed=1),
        "precip": synthetic_series(1.0, months=30, seed=2),
    }
    results = run_sweep(series, catalog)
    assert results[-1].id == "precip"
    short = results[-1]
    assert short.too_short and short.verdict == "unknown" and short.direction == "flat"
    assert short.q_value is None and short.p_value is None
    # with one testable variable BH q == p
    assert results[0].q_value == pytest.approx(results[0].p_value)


def test_sweep_unknown_variable_raises(catalog):
    with pytest.raises(KeyError):
        run_sweep({"nope": synthetic_series(1.0)}, catalog)


def test_sweep_all_nan_series(catalog):
    idx = pd.date_range("2003-01-01", periods=120, freq="MS")
    results = run_sweep({"t2m": pd.Series(np.nan, index=idx)}, catalog)
    assert results[0].too_short and results[0].n_months == 0
    assert results[0].sen_slope_per_decade is None


def test_to_dict_is_json_safe(catalog):
    d = run_sweep({"t2m": synthetic_series(1.0)}, catalog)[0].to_dict()
    assert d["id"] == "t2m"
    assert all(not (isinstance(v, float) and math.isnan(v)) for v in d.values())
