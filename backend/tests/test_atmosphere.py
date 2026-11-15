"""Air over cities: OMI nitrogen dioxide and AIRS carbon monoxide from NASA GIBS (no network).

OMI NO2 is a daily layer on GIBS (no monthly one, and GES DISC has no monthly OMI NO2
product either), so the yearly value is the mean of 4 sampled days a month. AIRS carbon
monoxide is a monthly layer, read like the MODIS ones.
"""

from __future__ import annotations

import io
import json

import httpx
import numpy as np
import pandas as pd
import pytest
from PIL import Image

from app import gather
from app.assets import gibs_layers
from app.catalog import load_catalog, variables_for_site
from app.detective.ledger import Ledger
from app.detective.place import Place
from app.detective.session import Session
from app.detective.tools import data as tools
from app.detective.tools import mapping
from app.extractors import gibs_values

# The real GIBS NO2 colormap writes values in scientific notation with a "+" exponent.
NO2_COLORMAP = """
<ColorMaps>
<ColorMap title="No Data">
  <ColorMapEntry rgb="255,0,255" transparent="true" nodata="true" ref="0"/>
</ColorMap>
<ColorMap title="Nitrogen Dioxide" units="molecules/cm²">
  <ColorMapEntry rgb="255,252,199" transparent="false" sourceValue="[-INF,0.00e+00)" value="[-INF,0.00e+00)" ref="1"/>
  <ColorMapEntry rgb="10,20,30" transparent="false" sourceValue="[4.00e+15,4.20e+15)" value="[4.00e+15,4.20e+15)" ref="2"/>
  <ColorMapEntry rgb="40,50,60" transparent="false" sourceValue="[8.00e+15,8.20e+15)" value="[8.00e+15,8.20e+15)" ref="3"/>
</ColorMap>
</ColorMaps>
"""
CO_COLORMAP = """
<ColorMaps>
<ColorMap title="Carbon Monoxide" units="ppbv">
  <ColorMapEntry rgb="10,20,30" transparent="false" sourceValue="[9.0e-08,9.2e-08)" value="[90.0,92.0)" ref="1"/>
  <ColorMapEntry rgb="40,50,60" transparent="false" sourceValue="[1.1e-07,1.12e-07)" value="[110.0,112.0)" ref="2"/>
</ColorMap>
</ColorMaps>
"""
OMI_CAVEAT = "OMI has a known sensor defect since 2007 (row anomaly); gaps are filled by neighbouring rows."
BOX = (77.0, 28.5, 77.4, 28.8)


def _png(colour: tuple[int, int, int] | None, width: int, height: int) -> bytes:
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    if colour is not None:
        rgba[..., :3] = colour
        rgba[..., 3] = 255
    buf = io.BytesIO()
    Image.fromarray(rgba).save(buf, format="PNG")
    return buf.getvalue()


def _client(colormap: str, colour_for, calls: list | None = None, fail: frozenset[str] = frozenset()) -> httpx.Client:
    """Fixture GIBS: `colour_for(date)` is the colour of the whole box that day (None = no data)."""

    def handle(request: httpx.Request) -> httpx.Response:
        if "colormaps" in str(request.url):
            return httpx.Response(200, text=colormap)
        p = request.url.params
        if calls is not None:
            calls.append(dict(p))
        if p["TIME"] in fail:
            return httpx.Response(503, text="busy")
        tile = _png(colour_for(p["TIME"]), int(p["WIDTH"]), int(p["HEIGHT"]))
        return httpx.Response(200, content=tile, headers={"content-type": "image/png"})

    return httpx.Client(transport=httpx.MockTransport(handle))


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    monkeypatch.setattr(gibs_layers, "_sleep", lambda s: None)


def _var(var_id: str):
    return next(v for v in load_catalog() if v.id == var_id)


def _session(tags=("city", "atmosphere"), lat=28.65, lon=77.2) -> Session:
    place = Place(lat=lat, lon=lon, bbox=(lon - 0.1, lat - 0.1, lon + 0.1, lat + 0.1), tags=tuple(tags))
    return Session(ledger=Ledger(), place=place, catalog=load_catalog(), series={})


# --------------------------------------------------------------------------- catalog


def test_no2_variable_applies_to_cities():
    no2, co = _var("no2_omi"), _var("co_airs")
    for var in (no2, co):
        assert var.source == "gibs" and var.temporal == "annual" and var.role == "impact"
        assert set(var.applies_to) == {"city", "atmosphere"}
        assert var.definition and var.units and var.resolution
        assert gibs_values.layer_for(var).gibs_layer == var.dataset
    assert no2.dataset == "OMI_Nitrogen_Dioxide_Tropo_Column"
    assert co.dataset == "AIRS_L3_Carbon_Monoxide_500hPa_Volume_Mixing_Ratio_Monthly_Day"
    city = {v.id for v in variables_for_site(load_catalog(), ("city", "atmosphere"))}
    forest = {v.id for v in variables_for_site(load_catalog(), ("vegetated", "forest"))}
    assert {"no2_omi", "co_airs"} <= city
    assert not {"no2_omi", "co_airs"} & forest
    # the label says exactly what the yearly value is
    assert "annual mean of daily values on 4 days a month" in no2.label
    assert "annual mean of monthly values" in co.label


def test_air_variables_are_listed_in_a_city():
    rows = {r["id"]: r for r in tools.list_variables(_session())["variables"]}
    assert rows["no2_omi"]["available"] is True and rows["co_airs"]["available"] is True
    assert rows["no2_omi"]["resolution"] == "~25 km" and rows["co_airs"]["resolution"] == "~100 km"
    elsewhere = {r["id"] for r in tools.list_variables(_session(tags=("vegetated",)))["variables"]}
    assert "no2_omi" not in elsewhere and "co_airs" not in elsewhere


def test_air_map_layers_are_offered_in_cities():
    layers = mapping.load_map_layers()
    assert layers["no2"]["gibs_layer"] == "OMI_Nitrogen_Dioxide_Tropo_Column"
    assert layers["co"]["gibs_layer"] == "AIRS_L3_Carbon_Monoxide_500hPa_Volume_Mixing_Ratio_Monthly_Day"
    for layer_id in ("no2", "co"):
        row = layers[layer_id]
        assert row["zones"] == ["city"] and set(row["zones"]) <= mapping.ZONES
        assert row["tile_matrix_set"] == "GoogleMapsCompatible_Level6"
        assert row["resolution"] and row["source"] and row["legend"]["colormap"].endswith(".xml")


# --------------------------------------------------------------------------- colours


def test_colormap_reads_scientific_notation_with_a_plus_exponent():
    table = gibs_layers.parse_colormap(NO2_COLORMAP)
    assert table[(10, 20, 30)] == pytest.approx(4.1e15)
    assert table[(40, 50, 60)] == pytest.approx(8.1e15)
    assert (255, 0, 255) not in table  # no data


# --------------------------------------------------------------------------- OMI NO2 (daily layer)


def test_no2_reads_four_days_a_month_and_converts_units():
    layer = gibs_values.layer_for(_var("no2_omi"))
    calls: list = []
    # 2010 low, 2011 high: one colour for the whole year
    colour = lambda date: (10, 20, 30) if date.startswith("2010") else (40, 50, 60)  # noqa: E731
    with _client(NO2_COLORMAP, colour, calls) as client:
        raw = gibs_values.fetch_annual(layer, BOX, 2010, 2011, client=client)
    asked = sorted({c["TIME"] for c in calls})
    assert len(asked) == 2 * 12 * 4
    assert {d[8:] for d in asked} == {"01", "09", "17", "25"}
    assert raw.tolist() == pytest.approx([4.1e15, 8.1e15])
    assert raw.attrs["days"] == [1, 9, 17, 25]
    var = _var("no2_omi")
    series = (raw * var.scale + var.offset).astype(float)  # what the `gibs` fetcher hands on
    assert series.tolist() == pytest.approx([4.1, 8.1])  # 10^15 molecules/cm²


def test_omi_result_carries_row_anomaly_caveat(monkeypatch):
    layer = gibs_values.layer_for(_var("no2_omi"))
    with _client(NO2_COLORMAP, lambda date: (10, 20, 30)) as client:
        raw = gibs_values.fetch_annual(layer, BOX, 2010, 2011, client=client)
    assert raw.attrs["caveat"] == OMI_CAVEAT

    monkeypatch.setattr(gibs_values, "fetch_annual", lambda lay, bbox, start, end, client=None: _yearly(lay, start, end))
    s = _session()
    got = tools.get_series(s, var_id="no2_omi", start=2005, end=2024)
    assert got["status"] == "ok", got
    assert got["caveat"] == OMI_CAVEAT and got["basis"] == "annual"
    assert got["precision"] == "palette step ≈ 0.1 10^15 molecules/cm²"  # the step in display units
    res = tools.trend_test(s, series_id=got["series_id"])
    assert res["caveat"] == OMI_CAVEAT and res["basis"] == "annual"
    label = s.ledger.test(res["test_id"]).label
    assert "annual mean of daily values on 4 days a month" in label and "monthly" not in label


def _yearly(layer, start, end) -> pd.Series:
    years = list(range(start, end + 1))
    s = pd.Series(5e15 + 1e14 * np.arange(len(years)), index=pd.to_datetime([f"{y}-01-01" for y in years]))
    s.attrs = {"temporal": "annual", "palette_step": 1.0e14, "dropped_years": [], "missing_years": []}
    if layer.caveat:
        s.attrs["caveat"] = layer.caveat
    return s


def test_no2_year_with_too_few_seen_days_is_dropped():
    layer = gibs_values.layer_for(_var("no2_omi"))
    # 2012: only 10 of the 48 sampled days show the box (cloud, the row anomaly)
    seen_2012 = {f"2012-{m:02d}-01" for m in range(1, 11)}

    def colour(date):
        if date.startswith("2012"):
            return (10, 20, 30) if date in seen_2012 else None
        return (40, 50, 60)

    with _client(NO2_COLORMAP, colour) as client:
        raw = gibs_values.fetch_annual(layer, BOX, 2011, 2013, client=client)
    assert [d.year for d in raw.index] == [2011, 2013]
    assert raw.attrs["dropped_years"] == [2012]


def test_no2_starts_with_the_first_full_omi_year():
    layer = gibs_values.layer_for(_var("no2_omi"))
    calls: list = []
    with _client(NO2_COLORMAP, lambda date: (10, 20, 30), calls) as client:
        raw = gibs_values.fetch_annual(layer, BOX, 2003, 2006, client=client)
    assert {c["TIME"][:4] for c in calls} == {"2005", "2006"}  # OMI flew from late 2004
    assert [d.year for d in raw.index] == [2005, 2006]


def test_no2_failed_day_is_a_missing_year_never_cached():
    layer = gibs_values.layer_for(_var("no2_omi"))
    with _client(NO2_COLORMAP, lambda date: (10, 20, 30), fail=frozenset({"2010-03-09"})) as client:
        raw = gibs_values.fetch_annual(layer, BOX, 2010, 2011, client=client)
    assert raw.attrs["missing_years"] == [2010] and [d.year for d in raw.index] == [2011]
    calls: list = []
    with _client(NO2_COLORMAP, lambda date: (10, 20, 30), calls) as client:
        again = gibs_values.fetch_annual(layer, BOX, 2010, 2011, client=client)
    assert {c["TIME"][:4] for c in calls} == {"2010"}  # 2011 from the disk cache
    assert [d.year for d in again.index] == [2010, 2011]


# --------------------------------------------------------------------------- AIRS CO (monthly layer)


def test_co_year_needs_every_month():
    layer = gibs_values.layer_for(_var("co_airs"))
    # GIBS has no AIRS pictures for May and June 2015 here: the year would lean on the other months
    colour = lambda date: None if date in ("2015-05-01", "2015-06-01") else (40, 50, 60)  # noqa: E731
    calls: list = []
    with _client(CO_COLORMAP, colour, calls) as client:
        raw = gibs_values.fetch_annual(layer, BOX, 2014, 2016, client=client)
    assert {c["TIME"][8:] for c in calls} == {"01"}  # monthly layer: the first of each month
    assert [d.year for d in raw.index] == [2014, 2016]
    assert raw.attrs["dropped_years"] == [2015]
    assert raw.tolist() == pytest.approx([111.0, 111.0])
    assert "caveat" not in raw.attrs and "days" not in raw.attrs


def test_monthly_layer_cache_keys_are_unchanged():
    """Adding sampled days must not move the cache of the MODIS layers already on disk."""
    import hashlib

    layer = gibs_values.layer_for(_var("ndvi_gibs"))
    box = (-4.6, 36.9, -4.4, 37.1)
    key = json.dumps([layer.gibs_layer, [round(float(c), 6) for c in box], list(range(1, 13)), 2010])
    expected = gibs_values.cache_dir_default / layer.id / f"{hashlib.sha256(key.encode()).hexdigest()[:20]}.json"
    assert gibs_values._cache_path(gibs_values.cache_dir_default, layer, box, 2010) == expected


def test_gibs_source_names_the_air_products():
    name = gather.SOURCES["gibs"].title
    assert "OMI" in name and "AIRS" in name
