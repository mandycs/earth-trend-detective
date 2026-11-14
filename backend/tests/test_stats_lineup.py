import json
import math

import numpy as np
import pandas as pd
import pytest

from app.stats.lineup import (
    CAVEAT,
    CLEARED,
    INCONCLUSIVE,
    NO_SUSPECT,
    OPEN,
    PRIME,
    SUSPECT_FOUND,
    annualize,
    run_lineup,
    year_changes,
)
from app.suspects import Suspect, registry_by_id

YEARS = np.arange(1990, 2024)  # 34 years -> 33 year-to-year changes, 25 up to 2015
N_PLACEBOS = 100


def _spec(sid: str, sign: int) -> Suspect:
    return Suspect(
        id=sid, label=f"suspect {sid}", source="synthetic", url="", expected_sign=sign,
        applies_to=("test",), unit="u", is_nasa=False,
    )


def _annual(values: np.ndarray, years: np.ndarray = YEARS) -> pd.Series:
    return pd.Series(values, index=years.astype(int))


def _to_monthly(annual: pd.Series, sigma: float, seed: int) -> pd.Series:
    """Monthly series whose calendar-year mean is the annual value plus small noise."""
    rng = np.random.default_rng(seed)
    index = pd.date_range(f"{annual.index.min()}-01-01", f"{annual.index.max()}-12-01", freq="MS")
    values = np.repeat(annual.to_numpy(), 12) + rng.normal(0, sigma, len(index))
    return pd.Series(values, index=index)


def _random_walk(seed: int, drift: float = 1.0, sigma: float = 1.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.cumsum(drift + rng.normal(0, sigma, len(YEARS)))


def _by_id(result):
    return {s.id: s for s in result.suspects}


# (a) residual driven by A with a one-year delay
@pytest.fixture(scope="module")
def case_a():
    a = _random_walk(seed=1)
    rng = np.random.default_rng(2)
    residual = np.empty(len(YEARS))
    residual[0] = 0.0
    residual[1:] = -0.8 * a[:-1]
    residual = residual + rng.normal(0, 0.4, len(YEARS))
    b = _random_walk(seed=3)
    monthly = _to_monthly(_annual(residual), sigma=0.3, seed=4)
    suspects = {"A": _annual(a), "B": _annual(b)}
    specs = registry_by_id([_spec("A", -1), _spec("B", -1)])
    return monthly, suspects, specs


def test_a_lagged_driver_is_prime_suspect_and_other_cleared(case_a):
    monthly, suspects, specs = case_a
    result = run_lineup(monthly, suspects, specs, n_placebos=N_PLACEBOS, seed=0)
    found = _by_id(result)
    assert found["A"].verdict == PRIME
    assert found["A"].lag_years == 1
    assert found["A"].r < -0.5
    assert found["A"].q < 0.05
    assert found["A"].oos_skill > 0
    assert found["A"].expected_sign_ok is True
    assert found["B"].verdict == CLEARED
    assert result.status == SUSPECT_FOUND
    assert result.n_suspects == 2
    assert result.n_tests == 6  # 2 suspects x 3 lags, all counted
    assert result.placebo_false_alarm_rate is not None and result.placebo_false_alarm_rate <= 0.10
    assert result.caveat == CAVEAT
    assert "1-year delay" in found["A"].evidence and "suspect A" in found["A"].evidence


def test_a_to_dict_is_json_safe(case_a):
    monthly, suspects, specs = case_a
    payload = run_lineup(monthly, suspects, specs, n_placebos=10, seed=0).to_dict()
    text = json.dumps(payload, allow_nan=False)
    assert "prime suspect" in text
    assert isinstance(payload["suspects"], list)


# (b) both series decline, otherwise unrelated: raw levels correlate, changes do not
def test_b_shared_trend_alone_is_not_a_suspect():
    rng = np.random.default_rng(10)
    t = np.arange(len(YEARS), dtype=float)
    residual = _annual(-0.5 * t + rng.normal(0, 1.0, len(YEARS)))
    suspect = _annual(-0.3 * t + rng.normal(0, 1.0, len(YEARS)))
    assert residual.corr(suspect) > 0.8  # the spurious level correlation is there...
    result = run_lineup(residual, {"T": suspect}, registry_by_id([_spec("T", 1)]), n_placebos=N_PLACEBOS)
    assert _by_id(result)["T"].verdict != PRIME  # ...but year-to-year changes kill it
    assert result.status != SUSPECT_FOUND


# (c) strong link but opposite to the declared mechanism
def test_c_wrong_sign_is_not_prime(case_a):
    monthly, suspects, _ = case_a
    specs = registry_by_id([_spec("A", 1), _spec("B", -1)])
    result = run_lineup(monthly, suspects, specs, n_placebos=N_PLACEBOS)
    a = _by_id(result)["A"]
    assert a.expected_sign_ok is False
    assert a.verdict == CLEARED
    assert "opposite" in a.evidence


# (d) relationship holds before the split only, reverses afterwards
def test_d_in_sample_only_is_not_prime():
    rng = np.random.default_rng(20)
    change_a = rng.normal(1.0, 1.0, len(YEARS))
    change_res = np.where(YEARS <= 2015, -change_a, change_a) + rng.normal(0, 0.2, len(YEARS))
    a = _annual(np.cumsum(change_a))
    residual = _annual(np.cumsum(change_res))
    result = run_lineup(residual, {"A": a}, registry_by_id([_spec("A", -1)]), n_placebos=N_PLACEBOS)
    found = _by_id(result)["A"]
    assert found.q < 0.05 and found.lag_years == 0  # strong in-sample match
    assert found.oos_skill < 0
    assert found.verdict == OPEN
    assert result.status == NO_SUSPECT


# (e) pure noise residual: no suspect, placebo false alarms near nominal
def test_e_noise_residual_gives_no_suspect_and_calibrated_placebos():
    rng = np.random.default_rng(30)
    residual = _to_monthly(_annual(rng.normal(0, 1.0, len(YEARS))), sigma=1.0, seed=31)
    suspects = {f"S{i}": _annual(_random_walk(seed=40 + i)) for i in range(4)}
    specs = registry_by_id([_spec(sid, -1) for sid in suspects])
    result = run_lineup(residual, suspects, specs, n_placebos=200, seed=0)
    assert result.status == NO_SUSPECT
    assert all(s.verdict != PRIME for s in result.suspects)
    assert result.placebo_false_alarm_rate < 0.10


def test_e_real_noise_lineups_rarely_accuse():
    """Across many independent null lineups the accusation rate stays near nominal."""
    accused = 0
    trials = 60
    for seed in range(trials):
        rng = np.random.default_rng(1000 + seed)
        residual = _annual(np.cumsum(rng.normal(0, 1.0, len(YEARS))))
        suspects = {f"S{i}": _annual(np.cumsum(rng.normal(0.5, 1.0, len(YEARS)))) for i in range(3)}
        specs = registry_by_id([_spec(sid, -1) for sid in suspects])
        result = run_lineup(residual, suspects, specs, n_placebos=0)
        accused += any(s.verdict == PRIME for s in result.suspects)
    assert accused / trials <= 0.10


def test_e_placebo_alarm_above_limit_marks_inconclusive(case_a, monkeypatch):
    import app.stats.lineup as lineup

    monkeypatch.setattr(lineup, "MAX_PLACEBO_ALARM", -1.0)
    monthly, suspects, specs = case_a
    result = run_lineup(monthly, suspects, specs, n_placebos=5)
    assert result.status == INCONCLUSIVE


# (f) gaps and short overlap
def test_f_gaps_are_handled_and_short_overlap_is_skipped_with_reason(case_a):
    monthly, suspects, specs = case_a
    gappy = suspects["A"].copy()
    gappy.loc[[1995, 2003, 2010]] = np.nan
    short = suspects["B"].loc[2012:2019]  # 8 years -> 7 changes
    result = run_lineup(monthly, {"A": gappy, "B": short}, specs, n_placebos=N_PLACEBOS)
    found = _by_id(result)
    assert found["A"].verdict == PRIME and found["A"].lag_years == 1
    assert found["B"].verdict == OPEN
    assert found["B"].lag_years is None and found["B"].r is None
    assert "need 10" in found["B"].skipped_reason
    assert found["B"].evidence == found["B"].skipped_reason
    assert result.n_tests == 3  # only A's lags were testable


def test_f_nothing_testable_is_inconclusive():
    residual = _annual(np.arange(5, dtype=float), YEARS[:5])
    result = run_lineup(residual, {"A": _annual(np.arange(5.0), YEARS[:5])}, registry_by_id([_spec("A", 1)]))
    assert result.status == INCONCLUSIVE
    assert result.placebo_false_alarm_rate is None
    assert result.n_tests == 0


def test_annualize_requires_eight_valid_months():
    index = pd.date_range("2000-01-01", "2002-12-01", freq="MS")
    monthly = pd.Series(np.ones(len(index)), index=index)
    monthly.iloc[12:17] = np.nan  # 2001 keeps 7 valid months
    annual = annualize(monthly)
    assert list(annual.index) == [2000, 2002]
    assert annual.loc[2000] == 1.0


def test_annualize_passes_annual_through_and_changes_skip_gaps():
    annual = pd.Series([1.0, 3.0, np.nan, 10.0, 12.0], index=[2000, 2001, 2002, 2003, 2004])
    assert annualize(annual).equals(annual.dropna())
    changes = year_changes(annualize(annual))
    assert list(changes.index) == [2001, 2004]  # no change across the 2002 gap
    assert list(changes) == [2.0, 2.0]


def test_missing_spec_raises():
    with pytest.raises(KeyError):
        run_lineup(_annual(np.zeros(len(YEARS))), {"X": _annual(np.zeros(len(YEARS)))}, {})


# (g) inputs not mutated
def test_g_inputs_not_mutated(case_a):
    monthly, suspects, specs = case_a
    gappy = suspects["A"].copy()
    gappy.loc[2000] = np.nan
    inputs = {"A": gappy, "B": suspects["B"]}
    before_res = monthly.copy()
    before = {k: v.copy() for k, v in inputs.items()}
    run_lineup(monthly, inputs, specs, n_placebos=10)
    pd.testing.assert_series_equal(monthly, before_res)
    assert list(inputs) == ["A", "B"]
    for k in before:
        pd.testing.assert_series_equal(inputs[k], before[k])


def test_suspect_rejects_bad_sign():
    with pytest.raises(ValueError):
        _spec("Z", 0)


def test_nan_becomes_none_in_to_dict():
    residual = _annual(np.arange(5, dtype=float), YEARS[:5])
    payload = run_lineup(residual, {"A": _annual(np.arange(5.0), YEARS[:5])}, registry_by_id([_spec("A", 1)])).to_dict()
    row = payload["suspects"][0]
    assert row["r"] is None and row["q"] is None and row["oos_skill"] is None
    assert not any(isinstance(v, float) and math.isnan(v) for v in row.values())
