"""GIBS yearly values at any point (no network: fixture tiles built from a small colormap)."""

from __future__ import annotations

import hashlib
import json
import io
from pathlib import Path

import httpx
import numpy as np
import pytest
from PIL import Image

import pandas as pd

from app import gather
from app.assets import gibs_layers
from app.catalog import load_catalog
from app.extractors import gibs_values
from app.investigate.runner import point_site

COLORMAP_XML = """
<ColorMap>
  <ColorMapEntry rgb="0,0,0" transparent="true" sourceValue="[-3000,-2000)" value="[-0.3,-0.2)" nodata="true" ref="0"/>
  <ColorMapEntry rgb="10,20,30" transparent="false" sourceValue="[100,200)" value="[0.10,0.12)" ref="1"/>
  <ColorMapEntry rgb="40,50,60" transparent="false" sourceValue="[200,300)" value="[0.20,0.22)" ref="2"/>
  <ColorMapEntry rgb="70,80,90" transparent="false" sourceValue="[300,400)" value="[0.30,0.32)" ref="3"/>
  <ColorMapEntry rgb="100,110,120" transparent="false" sourceValue="[400,500)" value="[0.40,0.42)" ref="4"/>
</ColorMap>
"""
COLOURS = ((10, 20, 30), (40, 50, 60), (70, 80, 90), (100, 110, 120))


def _tile(width: int, height: int, date: str, blank: bool = False) -> bytes:
    """A deterministic RGBA tile for `date`: colours picked from the colormap, a few holes."""
    year, month = int(date[:4]), int(date[5:7])
    rng = np.random.default_rng(year * 100 + month)
    picks = rng.integers(0, len(COLOURS), size=(height, width))
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[..., :3] = np.array(COLOURS, dtype=np.uint8)[picks]
    rgba[..., 3] = 255
    rgba[rng.random((height, width)) < 0.1, 3] = 0  # cloudy pixels
    if blank:
        rgba[...] = 0
    buf = io.BytesIO()
    Image.fromarray(rgba).save(buf, format="PNG")
    return buf.getvalue()


def _handler(
    blank_years: frozenset[int] = frozenset(),
    calls: list | None = None,
    blank_months: frozenset[tuple[int, int]] = frozenset(),
    fail: frozenset[tuple[int, int]] = frozenset(),
):
    """Fixture GIBS: `blank_*` answer a wholly transparent picture, `fail` months answer 503."""

    def handle(request: httpx.Request) -> httpx.Response:
        if "colormaps" in str(request.url):
            return httpx.Response(200, text=COLORMAP_XML)
        p = request.url.params
        if calls is not None:
            calls.append(dict(p))
        date = p["TIME"]
        ym = (int(date[:4]), int(date[5:7]))
        if ym in fail:
            return httpx.Response(503, text="busy")
        blank = ym[0] in blank_years or ym in blank_months
        tile = _tile(int(p["WIDTH"]), int(p["HEIGHT"]), date, blank=blank)
        return httpx.Response(200, content=tile, headers={"content-type": "image/png"})

    return handle


def _digests(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_build_layer_unchanged_after_refactor(monkeypatch, tmp_path):
    """The per-site output is byte-identical to the one written before `yearly_values` existed."""
    transport = httpx.MockTransport(_handler(blank_years=frozenset({2005})))
    real = httpx.Client
    monkeypatch.setattr(gibs_layers.httpx, "Client", lambda **kw: real(transport=transport, **kw))
    monkeypatch.setattr(gibs_layers, "YEARS", range(2003, 2008))
    layer = next(lay for lay in gibs_layers.LAYERS if lay.id == "ndvi_gibs")
    meta = gibs_layers.build_layer("donana", layer, sites_dir=tmp_path)
    assert meta is not None and meta["years"] == [2003, 2004, 2006, 2007]
    assert _digests(tmp_path) == GOLDEN


GOLDEN: dict[str, str] = {  # recorded with build_layer before the yearly_values refactor
    "donana/layers/ndvi_gibs/2003.png": "0b8d725d7c8d5789",
    "donana/layers/ndvi_gibs/2003_values.png": "82bccab1f530c5f2",
    "donana/layers/ndvi_gibs/2004.png": "300be81c24e13ab3",
    "donana/layers/ndvi_gibs/2004_values.png": "f0ccd0f8a10f1d7e",
    "donana/layers/ndvi_gibs/2006.png": "ee4ae19c82763138",
    "donana/layers/ndvi_gibs/2006_values.png": "e9ea271d638ba591",
    "donana/layers/ndvi_gibs/2007.png": "fb73c0cd6d3cd796",
    "donana/layers/ndvi_gibs/2007_values.png": "248dd01d0e182efd",
    "donana/layers/ndvi_gibs/meta.json": "9ad1abef5687c29e",
}


# --------------------------------------------------------------------------- any point


def _client(blank_years=frozenset(), calls=None, blank_months=frozenset(), fail=frozenset()) -> httpx.Client:
    handler = _handler(frozenset(blank_years), calls, frozenset(blank_months), frozenset(fail))
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    monkeypatch.setattr(gibs_layers, "_sleep", lambda s: None)


def _layer(layer_id: str) -> gibs_layers.GibsLayer:
    return gibs_values.layer_for(next(v for v in load_catalog() if v.id == layer_id))


BOX = (-4.6, 36.9, -4.4, 37.1)


def test_yearly_values_returns_the_season_mean_per_year():
    layer = _layer("ndvi_gibs")
    with _client() as client:
        got = gibs_layers.yearly_values(layer, BOX, range(2003, 2006), client, months=(3, 4), size=(8, 6))
    assert sorted(got) == [2003, 2004, 2005]
    assert got[2003].shape == (6, 8)
    finite = got[2003][np.isfinite(got[2003])]
    assert finite.size and finite.min() >= 0.11 - 1e-9 and finite.max() <= 0.41 + 1e-9  # midpoints of the fixture entries


def test_transparent_years_are_dropped():
    layer = _layer("ndvi_gibs")
    calls: list = []
    with _client(blank_years={2005, 2010}, calls=calls) as client:
        series = gibs_values.fetch_annual(layer, BOX, 2003, 2014, client=client)
    years = [d.year for d in series.index]
    assert years == [y for y in range(2003, 2015) if y not in (2005, 2010)]
    assert series.attrs["temporal"] == "annual"
    assert series.attrs["dropped_years"] == [2005, 2010]
    assert series.attrs["months"] == list(range(1, 13))
    assert abs(series.attrs["palette_step"] - 0.1) < 1e-9  # fixture colormap: one entry per 0.1
    assert len(calls) == 12 * 12  # every month of every year
    assert all(0.1 < v < 0.42 for v in series)


def test_every_year_transparent_is_a_source_failure():
    layer = _layer("ndvi_gibs")
    with _client(blank_years=set(range(2003, 2015))) as client, pytest.raises(gibs_values.GibsError):
        gibs_values.fetch_annual(layer, BOX, 2003, 2014, client=client)


def test_snow_blank_winter_months_do_not_lower_the_year():
    """A wholly transparent snow month was not seen (cloud, polar night): it is left out, not 0 %."""
    layer = _layer("snow_gibs")
    assert layer.transparent_value == 0.0
    with _client() as client:
        full = gibs_values.fetch_annual(layer, BOX, 2003, 2003, client=client, cache_dir=None)
    blank = {(2003, 1), (2003, 2), (2003, 12)}
    with _client(blank_months=blank) as client:
        partial = gibs_values.fetch_annual(layer, BOX, 2003, 2003, client=client, cache_dir=gibs_values.cache_dir_default / "b")
    months = [m for m in range(1, 13) if (2003, m) not in blank]
    with _client() as client:
        seen_only = gibs_layers.yearly_values(layer, BOX, [2003], client, months)
    with np.errstate(all="ignore"):
        expected = float(np.nanmean(seen_only[2003]))
    assert abs(partial.iloc[0] - expected) < 1e-9  # the mean of the nine seen months
    assert full.attrs["caveat"] == gibs_values.SNOW_CAVEAT
    assert "left out" in gibs_values.SNOW_CAVEAT


def test_snow_year_with_fewer_than_six_seen_months_is_dropped():
    layer = _layer("snow_gibs")
    blank = {(2004, m) for m in range(1, 8)}  # five seen months left in 2004
    with _client(blank_months=blank) as client:
        series = gibs_values.fetch_annual(layer, BOX, 2003, 2005, client=client)
    assert [d.year for d in series.index] == [2003, 2005]
    assert series.attrs["dropped_years"] == [2004]


# --------------------------------------------------------------------------- failures and cache


def test_a_503_month_is_missing_not_transparent():
    layer = _layer("ndvi_gibs")
    calls: list = []
    with _client(fail={(2005, 3)}, calls=calls) as client:
        series = gibs_values.fetch_annual(layer, BOX, 2003, 2014, client=client)
    assert series.attrs["missing_years"] == [2005]
    assert series.attrs["dropped_years"] == []
    assert 2005 not in [d.year for d in series.index]
    assert sum(1 for c in calls if c["TIME"] == "2005-03-01") == 1 + gibs_layers.RETRIES  # retried, then given up


def test_completed_years_are_cached_but_a_failed_year_is_not():
    layer = _layer("ndvi_gibs")
    with _client(fail={(2005, 3)}) as client:
        first = gibs_values.fetch_annual(layer, BOX, 2003, 2014, client=client)
    calls: list = []
    with _client(calls=calls) as client:
        again = gibs_values.fetch_annual(layer, BOX, 2003, 2014, client=client)
    assert {c["TIME"][:4] for c in calls} == {"2005"}  # only the failed year is asked again
    assert again.attrs["missing_years"] == []
    assert [d.year for d in again.index] == list(range(2003, 2015))
    assert again.drop(pd.Timestamp("2005-01-01")).equals(first)
    calls.clear()
    with _client(calls=calls) as client:
        gibs_values.fetch_annual(layer, BOX, 2003, 2014, client=client)
    assert calls == []  # every year from the disk cache


def test_corrupt_cache_file_is_fetched_again():
    layer = _layer("ndvi_gibs")
    with _client() as client:
        first = gibs_values.fetch_annual(layer, BOX, 2003, 2014, client=client)
    path = gibs_values._cache_path(gibs_values.cache_dir_default, layer, BOX, 2007)
    path.write_text("{not json", encoding="utf-8")
    calls: list = []
    with _client(calls=calls) as client:
        again = gibs_values.fetch_annual(layer, BOX, 2003, 2014, client=client)
    assert {c["TIME"][:4] for c in calls} == {"2007"}
    assert again.equals(first)
    assert not list(path.parent.glob("*.tmp"))


def test_no_completed_year_in_range_is_an_empty_series(monkeypatch):
    monkeypatch.setattr(gibs_values, "_this_year", lambda: 2026)
    calls: list = []
    with _client(calls=calls) as client:
        series = gibs_values.fetch_annual(_layer("ndvi_gibs"), BOX, 2026, 2026, client=client)
    assert series.empty and calls == []


def test_gibs_fetcher_returns_annual_series_with_precision(monkeypatch):
    seen = {}

    def fake(layer, bbox, start, end, client=None):
        seen["args"] = (layer.gibs_layer, tuple(bbox), start, end)
        s = pd.Series([0.5] * 12, index=pd.to_datetime([f"{y}-01-01" for y in range(2003, 2015)]))
        s.attrs = {"temporal": "annual", "palette_step": 0.005, "months": list(range(1, 13)), "dropped_years": []}
        return s

    monkeypatch.setattr(gibs_values, "fetch_annual", fake)
    site = point_site(37.0, -4.5, ("vegetated",))
    var = next(v for v in load_catalog() if v.id == "ndvi_gibs")
    out = gather.FETCHERS["gibs"](site, (var,), load_catalog(), 2003, 2014)
    series = out["ndvi_gibs"]
    assert seen["args"] == ("MODIS_Terra_L3_NDVI_Monthly", tuple(site.bbox), 2003, 2014)
    assert series.attrs["temporal"] == "annual"
    assert series.attrs["precision"] == "palette step ≈ 0.005 NDVI"


def test_gibs_variables_in_the_catalog():
    by_id = {v.id: v for v in load_catalog()}
    for var_id, twin in (("ndvi_gibs", "ndvi"), ("lst_gibs", "lst_day"), ("snow_gibs", "snow_cover")):
        var = by_id[var_id]
        assert var.source == "gibs" and var.temporal == "annual"
        assert var.definition and var.units and var.resolution and var.applies_to
        assert var.applies_to == by_id[twin].applies_to
        assert gibs_values.layer_for(var).gibs_layer == var.dataset
    assert by_id["lst_gibs"].units == "°C"


def test_point_season_skips_the_unfinished_year(monkeypatch):
    monkeypatch.setattr(gibs_values, "_this_year", lambda: 2014)
    layer = _layer("ndvi_gibs")
    calls: list = []
    with _client(calls=calls) as client:
        series = gibs_values.fetch_annual(layer, BOX, 2003, 2014, client=client)
    assert series.index[-1].year == 2013
    assert {c["TIME"][:4] for c in calls} == {str(y) for y in range(2003, 2014)}


def test_build_layer_leaves_out_a_year_it_could_not_fetch(monkeypatch, tmp_path):
    """A month that still fails after the retries: its year is not written, and meta.json says so."""
    transport = httpx.MockTransport(_handler(fail=frozenset({(2004, 3)})))
    real = httpx.Client
    monkeypatch.setattr(gibs_layers.httpx, "Client", lambda **kw: real(transport=transport, **kw))
    monkeypatch.setattr(gibs_layers, "YEARS", range(2003, 2007))
    layer = next(lay for lay in gibs_layers.LAYERS if lay.id == "ndvi_gibs")
    meta = gibs_layers.build_layer("donana", layer, sites_dir=tmp_path)
    out = tmp_path / "donana" / "layers" / "ndvi_gibs"
    assert meta["years"] == [2003, 2005, 2006]
    assert not (out / "2004.png").exists() and not (out / "2004_values.png").exists()
    written = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert written["missing_years"] == [2004] and written["years"] == [2003, 2005, 2006]
