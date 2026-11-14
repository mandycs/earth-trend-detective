import numpy as np
import pandas as pd

from app.stats.deseason import anomaly_std, monthly_anomalies
from tests.test_stats_helpers import monthly_index, synthetic_series


def test_pure_seasonal_cycle_gives_zero_anomalies():
    index = monthly_index(months=120)
    series = pd.Series(np.sin(2 * np.pi * index.month.to_numpy() / 12.0) * 5, index=index)
    anomalies = monthly_anomalies(series)
    assert np.allclose(anomalies.to_numpy(), 0.0, atol=1e-12)


def test_anomalies_remove_month_climatology():
    series = synthetic_series(0.0, amplitude=10.0, seed=1)
    anomalies = monthly_anomalies(series)
    by_month = anomalies.groupby(anomalies.index.month).mean()
    assert np.allclose(by_month.to_numpy(), 0.0, atol=1e-9)
    # seasonality gone: anomaly spread is close to the noise, far below the raw spread
    assert anomaly_std(anomalies) < series.std() / 3


def test_nan_stays_nan_and_input_not_mutated():
    series = synthetic_series(1.0, seed=2)
    series.iloc[[5, 17, 100]] = np.nan
    original = series.copy()
    anomalies = monthly_anomalies(series)
    assert anomalies.iloc[[5, 17, 100]].isna().all()
    assert anomalies.notna().sum() == series.notna().sum()
    pd.testing.assert_series_equal(series, original)


def test_anomaly_std_ignores_nan_and_handles_empty():
    s = pd.Series([1.0, np.nan, 3.0], index=monthly_index(months=3))
    assert anomaly_std(s) == np.std([1.0, 3.0], ddof=1)
    assert np.isnan(anomaly_std(pd.Series([np.nan], index=monthly_index(months=1))))
