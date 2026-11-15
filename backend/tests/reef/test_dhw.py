"""Heat stress at five reefs: the yearly maximum and the counted summary. Offline."""

from __future__ import annotations

from urllib.parse import unquote

import httpx
import pytest

from app.extractors import erddap
from app.reef import dhw
from app.reef.points import REEF_POINTS

DAVIES = REEF_POINTS[1]


@pytest.fixture(autouse=True)
def _no_pause(monkeypatch):
    monkeypatch.setattr(erddap, "_sleep", lambda _s: None)


def _csv(rows: list[tuple[str, str]]) -> str:
    head = "time,latitude,longitude,degree_heating_week\nUTC,degrees_north,degrees_east,degree_Celsius_weeks\n"
    return head + "".join(
        f"{day}T12:00:00Z,-18.775,147.625,{value}\n" for day, value in rows
    )


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_request_is_half_year_at_the_point(tmp_path):
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, text=_csv([("2016-03-21", "5.0")]))

    dhw.yearly_max(DAVIES, [2016], tmp_path, _client(handler))
    assert len(urls) == 1
    assert urls[0].startswith(
        "https://coastwatch.noaa.gov/erddap/griddap/noaacrwdhwDaily.csv?degree_heating_week%5B"
    )
    decoded = unquote(urls[0])
    time_axis = decoded.split("[")[1].split("]")[0]
    first, last = (part.strip("()") for part in time_axis.split(":1:"))
    assert (
        "2016-01-01" <= first[:10] <= "2016-01-02"
        and "2016-06-29" <= last[:10] <= "2016-06-30"
    )
    assert "(-18.8)" in decoded and "(147.6)" in decoded


def test_yearly_max_and_its_date(tmp_path):
    text = _csv([("2020-02-10", "3.1"), ("2020-03-21", "5.36"), ("2020-04-02", "4.9")])
    out = dhw.yearly_max(
        DAVIES, [2020], tmp_path, _client(lambda r: httpx.Response(200, text=text))
    )
    assert out == {2020: dhw.YearlyMax(5.36, "2020-03-21")}


def test_missing_year_is_null_not_zero(tmp_path):
    text = _csv([("2020-02-10", "NaN"), ("2020-03-21", "NaN")])
    out = dhw.yearly_max(
        DAVIES, [2020], tmp_path, _client(lambda r: httpx.Response(200, text=text))
    )
    assert out == {2020: dhw.YearlyMax(None, None)}
    summary = dhw.heat_stress_summary({"davies": out}, [DAVIES], 2020, 2020)
    assert summary["points"][0]["years_at_or_above"] == {"4": [], "8": []}
    assert sum(p["reef_years_missing"] for p in summary["periods"]) == 1
    assert sum(p["reef_years_measured"] for p in summary["periods"]) == 0


def test_failed_fetch_is_missing_not_below_four(tmp_path):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(unquote(str(request.url)))
        if "(2019-" in calls[-1]:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, text=_csv([("2020-03-21", "1.0")]))

    out = dhw.yearly_max(DAVIES, [2019, 2020], tmp_path, _client(handler))
    assert 2019 not in out
    assert out[2020] == dhw.YearlyMax(1.0, "2020-03-21")
    summary = dhw.heat_stress_summary({"davies": out}, [DAVIES], 2019, 2020)
    assert [y["year"] for y in summary["points"][0]["yearly_max"]] == [2019, 2020]
    assert summary["points"][0]["yearly_max"][0]["value"] is None
    assert sum(p["reef_years_missing"] for p in summary["periods"]) == 1


def test_threshold_is_inclusive():
    yearly = {
        "davies": {
            2020: dhw.YearlyMax(4.0, "2020-03-01"),
            2021: dhw.YearlyMax(7.99, "2021-03-01"),
        }
    }
    point = dhw.heat_stress_summary(yearly, [DAVIES], 2020, 2021)["points"][0]
    assert point["years_at_or_above"] == {"4": [2020, 2021], "8": []}


def _scout_yearly():
    listed = {
        "north": {2016: 11.36, 2017: 9.20, 2020: 5.0, 2022: 5.0, 2024: 5.0},
        "davies": {2017: 5.0, 2020: 5.36, 2022: 5.0, 2024: 5.0},
        "outer": {
            2009: 5.67,
            2016: 5.0,
            2017: 5.0,
            2020: 10.50,
            2022: 8.89,
            2024: 9.46,
        },
        "burdekin": {2017: 5.0, 2020: 7.17, 2022: 5.0, 2024: 5.0},
        "heron": {2020: 5.0, 2024: 11.59},
    }
    return {
        pid: {
            y: dhw.YearlyMax(vals.get(y, 1.0), f"{y}-03-01") for y in range(2003, 2025)
        }
        for pid, vals in listed.items()
    }


def test_threshold_uses_unrounded_value_and_rounds_for_display():
    yearly = {"davies": {2020: dhw.YearlyMax(3.996, "2020-03-01")}}
    summary = dhw.heat_stress_summary(yearly, [DAVIES], 2020, 2020)
    assert summary["points"][0]["yearly_max"][0]["value"] == 4.0
    assert summary["points"][0]["years_at_or_above"]["4"] == []
    assert summary["periods"][1]["reef_years_at_or_above"]["4"] == 0


def test_method_window_follows_the_hemisphere():
    summary = dhw.heat_stress_summary({}, [DAVIES], 2020, 2021)
    assert "January to June" in summary["method"]
    north = dhw.ReefPoint("n", "N", 10.0, 100.0)
    assert (
        "July to December" in dhw.heat_stress_summary({}, [north], 2020, 2021)["method"]
    )
    with pytest.raises(ValueError):
        dhw.heat_stress_summary({}, [DAVIES, north], 2020, 2021)


def test_summary_counts_scout_years():
    summary = dhw.heat_stress_summary(_scout_yearly(), list(REEF_POINTS), 2003, 2024)
    first, second = summary["periods"]
    assert first["years"] == [2003, 2013] and second["years"] == [2014, 2024]
    assert first["reef_years_at_or_above"] == {"4": 1, "8": 0}
    assert second["reef_years_at_or_above"] == {"4": 20, "8": 6}
    assert first["reef_years_measured"] == second["reef_years_measured"] == 55
    assert first["reef_years_missing"] == second["reef_years_missing"] == 0
    assert summary["unit"] == "°C-weeks"
    assert summary["thresholds"][0]["label"] == "NOAA Coral Reef Watch Alert Level 1"
    assert summary["source"]["name"].endswith("(not NASA)")


def test_worst_reef_series():
    summary = dhw.heat_stress_summary(_scout_yearly(), list(REEF_POINTS), 2003, 2024)
    worst = {row["year"]: row["value"] for row in dhw.worst_reef_series(summary)}
    assert worst[2024] == 11.59 and worst[2016] == 11.36 and worst[2005] == 1.0
    assert len(worst) == 22
