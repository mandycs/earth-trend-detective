import numpy as np
import pandas as pd
import pymannkendall as mk
import pytest

from app.stats.deseason import monthly_anomalies
from app.stats.trend import MIN_MONTHS, MIN_YEARS_SPAN, sen_slope_ci, trend_test
from tests.test_stats_helpers import ar1_noise, monthly_index, synthetic_series


def test_known_trend_detected_with_slope_close_to_truth():
    series = synthetic_series(2.0, phi=0.4, sigma=1.0, seed=42)
    result = trend_test(monthly_anomalies(series))
    assert not result.too_short
    assert result.p_value < 0.01
    assert result.sen_slope_per_decade == pytest.approx(2.0, abs=0.35)
    assert result.ci_low < 2.0 < result.ci_high
    assert result.ci_low < result.sen_slope_per_decade < result.ci_high
    assert result.sigma_per_decade == pytest.approx(
        result.sen_slope_per_decade / result.anomaly_std
    )
    assert result.n_months == 264
    assert result.years_span == pytest.approx(22.0)


def test_negative_trend_has_negative_slope():
    result = trend_test(monthly_anomalies(synthetic_series(-3.0, seed=7)))
    assert result.sen_slope_per_decade < 0
    assert result.ci_high < 0


def test_pure_noise_is_not_significant_most_of_the_time():
    p_values = [
        trend_test(monthly_anomalies(synthetic_series(0.0, phi=0.5, seed=s))).p_value
        for s in range(40)
    ]
    # under the null ~5% would fall below 0.05; allow slack but catch a broken test
    assert np.mean(np.array(p_values) < 0.05) <= 0.15


def test_autocorrelation_correction_reduces_significance():
    n = 264
    noise = ar1_noise(n, phi=0.85, sigma=1.0, seed=3)
    values = 0.004 * np.arange(n) + noise
    series = pd.Series(values, index=monthly_index(months=n))
    corrected = trend_test(series)
    plain = mk.original_test(values)
    assert corrected.p_value > plain.p
    assert corrected.var_s > plain.var_s


def test_ci_matches_gilbert_formula_on_simple_case():
    times = np.arange(10, dtype=float)
    values = np.array([1, 3, 2, 5, 4, 6, 8, 7, 9, 10], dtype=float)
    slope, low, high = sen_slope_ci(times, values, var_s=125.0)
    slopes = np.sort(
        [(values[j] - values[i]) / (times[j] - times[i]) for i in range(10) for j in range(i + 1, 10)]
    )
    assert slope == pytest.approx(np.median(slopes))
    assert low <= slope <= high
    assert low >= slopes[0] and high <= slopes[-1]


def test_too_short_series_returns_no_verdict_inputs():
    series = synthetic_series(5.0, months=MIN_MONTHS - 1, seed=1)
    result = trend_test(monthly_anomalies(series))
    assert result.too_short
    assert np.isnan(result.p_value)
    assert result.n_months == MIN_MONTHS - 1


def test_enough_months_but_too_short_span():
    # many valid months crammed into < MIN_YEARS_SPAN is impossible monthly, so
    # instead: long span but too few valid months because of gaps
    series = synthetic_series(5.0, months=120, seed=1)
    gappy = series.where(series.index.month.isin([1, 7]))
    result = trend_test(monthly_anomalies(gappy))
    assert result.too_short
    assert result.years_span >= MIN_YEARS_SPAN


def test_nan_gaps_still_give_correct_slope():
    series = synthetic_series(2.0, phi=0.3, seed=11)
    rng = np.random.default_rng(0)
    holes = rng.choice(len(series), size=50, replace=False)
    gappy = series.copy()
    gappy.iloc[holes] = np.nan
    result = trend_test(monthly_anomalies(gappy))
    assert not result.too_short
    assert result.n_months == len(series) - 50
    assert result.sen_slope_per_decade == pytest.approx(2.0, abs=0.4)
    assert result.p_value < 0.01


def test_constant_series_does_not_crash():
    series = pd.Series(np.ones(120), index=monthly_index(months=120))
    result = trend_test(series)
    assert result.sen_slope_per_decade == 0
    assert result.p_value == pytest.approx(1.0)
    assert np.isnan(result.sigma_per_decade)
