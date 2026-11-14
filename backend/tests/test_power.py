import json
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import respx

from app.extractors.power import POWER_MONTHLY_URL, fetch_monthly, parse_monthly

FIXTURE = Path(__file__).parent / "fixtures" / "power_monthly_lake_mead.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def test_parse_monthly_drops_annual_rows_and_builds_month_index():
    series = parse_monthly(load_fixture(), {"t2m": "T2M", "precip": "PRECTOTCORR"})
    assert set(series) == {"t2m", "precip"}
    t2m = series["t2m"]
    assert len(t2m) == 24  # 2 years x 12 months, month "13" removed
    assert t2m.index[0] == pd.Timestamp("2022-01-01")
    assert t2m.index[-1] == pd.Timestamp("2023-12-01")
    assert t2m.iloc[0] == 7.57


def test_parse_monthly_turns_fill_values_into_nan():
    payload = load_fixture()
    payload["properties"]["parameter"]["T2M"]["202203"] = -999.0
    t2m = parse_monthly(payload, {"t2m": "T2M"})["t2m"]
    assert np.isnan(t2m.loc["2022-03-01"])


@respx.mock
def test_fetch_monthly_calls_api_then_uses_cache(tmp_path):
    route = respx.get(POWER_MONTHLY_URL).mock(return_value=httpx.Response(200, json=load_fixture()))

    first = fetch_monthly(36.2, -114.5, {"t2m": "T2M"}, 2022, 2023, cache_dir=tmp_path)
    second = fetch_monthly(36.2, -114.5, {"t2m": "T2M"}, 2022, 2023, cache_dir=tmp_path)

    assert route.call_count == 1
    params = route.calls[0].request.url.params
    assert params["parameters"] == "T2M"
    assert params["latitude"] == "36.2"
    assert params["longitude"] == "-114.5"
    pd.testing.assert_series_equal(first["t2m"], second["t2m"])
