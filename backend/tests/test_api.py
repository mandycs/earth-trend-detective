import httpx
import numpy as np
import pytest
import respx
from fastapi.testclient import TestClient

from app.extractors.power import POWER_MONTHLY_URL
from app.main import app, get_power_cache_dir


def power_payload(start: int, end: int) -> dict:
    """Fake POWER monthly payload: warming T2M, noisy rain, flat-ish sun."""
    rng = np.random.default_rng(0)
    params: dict[str, dict[str, float]] = {"T2M": {}, "PRECTOTCORR": {}, "ALLSKY_SFC_SW_DWN": {}}
    i = 0
    for year in range(start, end + 1):
        for month in range(1, 14):
            key = f"{year}{month:02d}"
            if month == 13:
                for band in params:
                    params[band][key] = 0.0
                continue
            season = np.sin(2 * np.pi * month / 12)
            params["T2M"][key] = round(20 + 10 * season + 0.005 * i + rng.normal(0, 0.3), 2)
            params["PRECTOTCORR"][key] = round(max(0.0, 1 + season + rng.normal(0, 0.5)), 2)
            params["ALLSKY_SFC_SW_DWN"][key] = round(20 + 8 * season + rng.normal(0, 0.5), 2)
            i += 1
    return {"header": {"fill_value": -999.0}, "properties": {"parameter": params}}


@pytest.fixture
def client(tmp_path):
    app.dependency_overrides[get_power_cache_dir] = lambda: tmp_path
    yield TestClient(app)
    app.dependency_overrides.clear()


@respx.mock
def test_sweep_returns_ranked_power_variables(client):
    route = respx.get(POWER_MONTHLY_URL).mock(
        return_value=httpx.Response(200, json=power_payload(2003, 2024))
    )
    response = client.get("/sweep", params={"lat": 36.2, "lon": -114.5})
    assert response.status_code == 200
    body = response.json()
    assert route.call_count == 1
    assert route.calls[0].request.url.params["start"] == "2003"
    assert body["lat"] == 36.2 and body["start"] == 2003 and body["end"] == 2024
    ids = [v["id"] for v in body["variables"]]
    assert set(ids) == {"t2m", "precip", "solar"}
    t2m = next(v for v in body["variables"] if v["id"] == "t2m")
    assert ids[0] == "t2m"
    assert t2m["verdict"] == "real" and t2m["direction"] == "up"
    for key in ("sen_slope_per_decade", "ci_low", "ci_high", "sigma_per_decade", "p_value", "q_value"):
        assert isinstance(t2m[key], float)


@pytest.mark.parametrize(
    "params",
    [
        {"lat": 95, "lon": 0},
        {"lat": 0, "lon": -181},
        {"lat": 0, "lon": 0, "start": 2020, "end": 2010},
        {"lat": 0, "lon": 0, "start": 1970},
    ],
)
def test_sweep_rejects_bad_input_with_plain_message(client, params):
    response = client.get("/sweep", params=params)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, str) and len(detail) > 10


@respx.mock
def test_sweep_upstream_failure_is_a_clear_502(client):
    respx.get(POWER_MONTHLY_URL).mock(return_value=httpx.Response(500, text="boom"))
    response = client.get("/sweep", params={"lat": 36.2, "lon": -114.5})
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "NASA POWER" in detail and "try again" in detail.lower()
    assert "Traceback" not in detail


@respx.mock
def test_sweep_upstream_timeout_is_a_clear_504(client):
    respx.get(POWER_MONTHLY_URL).mock(side_effect=httpx.ReadTimeout("slow"))
    response = client.get("/sweep", params={"lat": 36.2, "lon": -114.5})
    assert response.status_code == 504
    assert "NASA POWER" in response.json()["detail"]


@respx.mock
def test_sweep_default_has_no_series(client):
    respx.get(POWER_MONTHLY_URL).mock(return_value=httpx.Response(200, json=power_payload(2003, 2024)))
    body = client.get("/sweep", params={"lat": 36.2, "lon": -114.5}).json()
    assert "series" not in body


@respx.mock
def test_sweep_include_series_returns_monthly_points(client):
    payload = power_payload(2003, 2024)
    payload["properties"]["parameter"]["T2M"]["200305"] = -999.0  # fill value -> null
    respx.get(POWER_MONTHLY_URL).mock(return_value=httpx.Response(200, json=payload))
    response = client.get("/sweep", params={"lat": 36.2, "lon": -114.5, "include_series": "true"})
    assert response.status_code == 200
    series = response.json()["series"]
    assert set(series) == {"t2m", "precip", "solar"}
    t2m = series["t2m"]
    assert len(t2m) == 22 * 12
    assert t2m[0]["date"] == "2003-01"
    assert set(t2m[0]) == {"date", "value", "anomaly"}
    assert isinstance(t2m[0]["value"], float) and isinstance(t2m[0]["anomaly"], float)
    may = next(p for p in t2m if p["date"] == "2003-05")
    assert may["value"] is None and may["anomaly"] is None
