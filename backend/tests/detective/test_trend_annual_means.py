"""Rain, runoff and snow: the trend is tested on annual means, not on monthly anomalies.

A dry season full of zeros drags the Sen slope of monthly anomalies to about zero even when
the rainy months get much wetter (Chad: 0.0071 vs ~0.45 mm/day per decade). One mean per
complete year keeps the whole change.
"""

import numpy as np
import pandas as pd
import pytest

from app.catalog import load_catalog
from app.detective.ledger import Ledger
from app.detective.place import Place
from app.detective.session import Session
from app.detective.tools import data as tools


def _session() -> Session:
    place = Place(lat=12.0, lon=15.0, bbox=(14.9, 11.9, 15.1, 12.1), tags=("dry",), site_id=None)
    return Session(ledger=Ledger(), place=place, catalog=load_catalog(), series={})


def _sahel_rain(start=2003, end=2024, end_month=12, name="precip") -> pd.Series:
    """Zero for eight months a year; the four rainy months get wetter by 0.5 mm/day a year."""
    idx = pd.date_range(f"{start}-01-01", f"{end}-{end_month:02d}-01", freq="MS")
    rng = np.random.default_rng(1)
    year = (idx.year - start).to_numpy(dtype=float)
    rainy = np.isin(idx.month, [6, 7, 8, 9])
    values = np.where(rainy, 3.0 + 0.5 * year + rng.normal(0, 0.1, idx.size), 0.0)
    return pd.Series(values, index=idx, name=name)


def _put(s: Session, series: pd.Series) -> str:
    sid = f"{series.name}:test"
    s.series[sid] = series
    return sid


@pytest.mark.parametrize("var_id", ["precip", "precip_upstream", "runoff", "snow_cover"])
def test_skewed_water_variables_are_tested_on_annual_means(var_id):
    s = _session()
    res = tools.trend_test(s, series_id=_put(s, _sahel_rain(name=var_id)))
    assert res["basis"] == "annual means"
    assert res["n_years"] == 22
    # 4 wet months x 0.5 mm/day a year / 12 months x 10 years = 1.67 per decade
    assert res["slope_per_decade"] == pytest.approx(4 * 0.5 * 10 / 12, rel=0.05)
    assert res["direction"] == "up"
    assert "n_months" not in res
    assert s.ledger.n_tests == 1


def test_the_annual_mean_keeps_the_unit_of_the_variable():
    s = _session()
    res = tools.trend_test(s, series_id=_put(s, _sahel_rain()))
    assert res["unit"] == "mm/day per decade"


def test_an_incomplete_year_is_left_out():
    s = _session()
    # ends in March: the last year has only dry months and would read as a drought
    res = tools.trend_test(s, series_id=_put(s, _sahel_rain(end=2024, end_month=3)))
    assert res["basis"] == "annual means"
    assert res["years"] == [2003, 2023]
    assert res["n_years"] == 21


def test_too_few_complete_years_falls_back_to_monthly_anomalies():
    s = _session()
    res = tools.trend_test(s, series_id=_put(s, _sahel_rain(start=2018, end=2024)))
    assert res["basis"] == "monthly"


def test_temperature_stays_on_monthly_anomalies():
    s = _session()
    idx = pd.date_range("2003-01-01", "2024-12-01", freq="MS")
    t2m = pd.Series(np.linspace(10, 12, idx.size), index=idx, name="t2m")
    res = tools.trend_test(s, series_id=_put(s, t2m))
    assert res["basis"] == "monthly"


def test_years_needed_for_uses_the_same_annual_means():
    from app.detective.tools import analysis

    s = _session()
    sid = _put(s, _sahel_rain())
    out = analysis.years_needed_for(s, sid)
    assert out["basis"] == "annual means"
    assert out["years_needed"] == tools.trend_test(s, series_id=sid)["years_needed"]


def test_the_report_keeps_the_whole_period_over_a_short_monthly_test():
    from app.detective.report import ledger_report

    s = _session()
    sid = _put(s, _sahel_rain())
    whole = tools.trend_test(s, series_id=sid)
    tools.trend_test(s, series_id=sid, start=2019)  # too few complete years: monthly fallback
    row = next(r for r in ledger_report(s)["variables"] if r["id"] == "precip")
    assert row["test_id"] == whole["test_id"]
