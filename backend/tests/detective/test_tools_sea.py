"""The detective reaches the sea variables through get_series -> gather.FETCHERS["erddap"]."""

import numpy as np
import pandas as pd

from app.catalog import load_catalog
from app.detective.ledger import Ledger
from app.detective.place import Place
from app.detective.session import Session
from app.detective.tools import data as tools
from app.extractors import erddap


def _sea_session() -> Session:
    # Atlantic, off Cape St. Vincent: open sea, no land cover
    place = Place(lat=36.0, lon=-10.0, bbox=(-10.1, 35.9, -9.9, 36.1), tags=("ocean",))
    return Session(ledger=Ledger(), place=place, catalog=load_catalog(), series={})


def test_get_series_sst_at_sea_goes_through_the_erddap_fetcher(monkeypatch):
    calls = []

    def fake_point_monthly(dataset, variable, lat, lon, start, end, client=None):
        calls.append((dataset, variable, lat, lon, start, end))
        idx = pd.date_range(f"{start}-01-01", f"{end}-12-01", freq="MS")
        series = pd.Series(18 + 3 * np.sin(2 * np.pi * idx.month / 12), index=idx)
        series.attrs["cell"] = (36.005, -9.995)
        return series, (36.005, -9.995)

    monkeypatch.setattr(erddap, "fetch_point_monthly", fake_point_monthly)
    s = _sea_session()
    rows = {r["id"]: r for r in tools.list_variables(s)["variables"]}
    assert rows["sst"]["available"] and rows["sst"]["resolution"] == "~1 km"
    got = tools.get_series(s, var_id="sst")
    assert got["status"] == "ok", got
    assert calls == [("jplMURSST41mday", "sst", 36.0, -10.0, s.start, s.end)]
    assert got["unit"] == "°C"
    assert got["cell"] == [36.005, -9.995]
    assert got["n_months"] == 12 * (s.end - s.start + 1)
    assert tools.trend_test(s, series_id=got["series_id"])["test_id"] == "t1"


def test_heat_stress_is_not_offered_on_the_monthly_path(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("must not fetch")

    monkeypatch.setattr(erddap, "fetch_point_yearly_max", boom)
    s = _sea_session()
    got = tools.get_series(s, var_id="dhw")
    assert got["status"] == "not_available"
    assert got["reason"] == tools.ANNUAL_PENDING_REASON
    row = next(r for r in tools.list_variables(s)["variables"] if r["id"] == "dhw")
    assert row["available"] is False and row["reason"] == tools.ANNUAL_PENDING_REASON
