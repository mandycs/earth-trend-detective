"""trend_map: per-pixel "where" maps, the PNG route and the map cleanup (all offline)."""

import os
import re
import time

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.assets import gibs_layers
from app.catalog import load_catalog
from app.detective import maps
from app.detective.ledger import Ledger
from app.detective.place import Place
from app.detective.session import Session
from app.detective.tools import TOOLS, where
from app.detective.tools import data as tools
from app.extractors import erddap, gibs_values

URL_RE = re.compile(r"^/detective/maps/[0-9a-f]{32}\.png$")


@pytest.fixture(autouse=True)
def _dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(maps, "MAPS_DIR", tmp_path / "maps")
    monkeypatch.setattr(gibs_values, "grid_cache_dir_default", tmp_path / "gibs_grids")
    return tmp_path


def _session(tags=("ocean", "coast"), lat=-18.0, lon=147.0, half=0.1) -> Session:
    place = Place(lat=lat, lon=lon, bbox=(lon - half, lat - half, lon + half, lat + half), tags=tuple(tags))
    return Session(ledger=Ledger(), place=place, catalog=load_catalog(), series={})


def _sea_grid(start, end, ny=10, nx=10, warming=0.05):
    """Monthly SST: the east half warms by `warming` °C a year, the west half is noise only."""
    times = pd.date_range(f"{start}-01-01", f"{end}-12-01", freq="MS")
    rng = np.random.default_rng(3)
    t = (np.arange(len(times)) / 12.0)[:, None, None]
    season = 2.0 * np.sin(2 * np.pi * np.asarray(times.month)[:, None, None] / 12.0)
    trend = np.zeros((1, ny, nx))
    trend[..., nx // 2 :] = warming
    cube = 26.0 + season + trend * t + rng.normal(0, 0.05, (len(times), ny, nx))
    cube[:, 0, 0] = np.nan  # one land cell
    lat = np.linspace(-18.1, -17.9, ny)  # ascending, as MUR answers
    lon = np.linspace(146.9, 147.1, nx)
    out = xr.DataArray(cube, dims=("time", "latitude", "longitude"), coords={"time": times, "latitude": lat, "longitude": lon})
    out.attrs["missing_years"] = []
    return out


@pytest.fixture
def grid_calls(monkeypatch):
    calls = []

    def fake(dataset, variable, bbox, start, end, stride, client=None, cache_dir=None):
        calls.append({"dataset": dataset, "variable": variable, "bbox": bbox, "start": start, "end": end, "stride": stride})
        return _sea_grid(start, end)

    monkeypatch.setattr(erddap, "fetch_grid", fake)
    return calls


def test_trend_map_writes_png_and_overlay_op(grid_calls, _dirs):
    s = _session()
    got = where.trend_map(s, var_id="sst")
    assert got["status"] == "ok", got
    assert URL_RE.match(got["url"])
    path = maps.MAPS_DIR / got["url"].rsplit("/", 1)[1]
    with Image.open(path) as im:
        assert im.format == "PNG" and im.mode == "RGBA"
        assert max(im.size) >= where.MIN_RENDER_SIDE
    step = 0.2 / 9  # the fake grid: 10 cell centres from 146.9 to 147.1 (and -18.1 to -17.9)
    assert got["map"]["bounds"] == pytest.approx([146.9 - step / 2, -18.1 - step / 2, 147.1 + step / 2, -17.9 + step / 2])
    assert "bounds" not in got and "legend" not in got and "share_up" not in got
    assert 0.3 < got["share_significant"] < 0.7  # the east half has a clear trend
    assert got["median_slope_per_decade"] is not None and got["median_slope_per_decade"] > 0
    assert got["basis"] == "monthly"  # sea temperature stays on its own basis
    legend = got["map"]["legend"]
    assert legend["unit"] == "°C per decade"
    assert legend["labels"]["faded"] == "Faded = could be chance at this pixel"
    assert legend["labels"]["transparent"] == "Transparent = not enough data"
    assert len(legend["stops"]) == 9 and legend["range"][0] == -legend["range"][1]
    assert "share of the area with a clear trend" in got["note"]
    op = s.map[-1]
    assert op["op"] == "overlay"
    assert {"url", "bounds", "legend", "title", "source", "resolution", "period"} <= set(op)
    assert op["url"] == got["url"] and op["period"] == [2003, 2024] and op["resolution"] == "~1 km"
    assert op["bounds"] == got["map"]["bounds"] and op["legend"] == legend
    # exactly one counted test, on the median over the map area
    assert s.ledger.n_tests == 1
    record = s.ledger.test("t1")
    assert got["test_id"] == "t1" and got["verdict"] in {"real", "likely", "unknown"}
    assert record.kind == "trend" and "median over the map area" in record.label
    # the same call again: cached, no second test, no second file, no second op
    again = where.trend_map(s, var_id="sst")
    assert again["url"] == got["url"] and s.ledger.n_tests == 1
    assert len(list(maps.MAPS_DIR.glob("*.png"))) == 1 and len(s.map) == 1
    assert len(grid_calls) == 1


def test_faded_pixels_are_not_significant(grid_calls):
    s = _session()
    got = where.trend_map(s, var_id="sst")
    with Image.open(maps.MAPS_DIR / got["url"].rsplit("/", 1)[1]) as im:
        alpha = np.asarray(im)[..., 3]
    values = set(np.unique(alpha).tolist())
    assert values <= {0, 70, 230} and {70, 230} <= values  # faded, clear, and the land cell transparent
    assert 0 in values


def test_no_grid_source_not_available():
    s = _session(tags=("vegetated", "agriculture"), lat=37.0, lon=-4.5)
    for var_id in ("precip", "t2m"):
        got = where.trend_map(s, var_id=var_id)
        assert got == {"status": "not_available", "reason": "no gridded source for this variable", "var_id": var_id, "evidence_id": got["evidence_id"]}
    assert s.ledger.n_tests == 0 and s.map == []


def test_heat_stress_has_no_grid_yet():
    got = where.trend_map(_session(tags=("ocean", "coast", "reef")), var_id="dhw")
    assert got["status"] == "not_available" and got["reason"] == where.NO_GRID_REASON


def test_same_unavailable_predicate_as_get_series(grid_calls):
    s = _session(tags=("vegetated",), lat=37.0, lon=-4.5)
    got = where.trend_map(s, var_id="sst")
    assert got["status"] == "not_available" and got["reason"] == tools.get_series(s, var_id="sst")["reason"]
    assert grid_calls == []


def test_unknown_variable():
    got = where.trend_map(_session(), var_id="nope")
    assert got["status"] == "not_available" and "unknown variable" in got["reason"]


def test_erddap_failure_is_transient_and_logs_no_test(monkeypatch):
    def down(*a, **k):
        raise erddap.ErddapError("502")

    monkeypatch.setattr(erddap, "fetch_grid", down)
    s = _session()
    got = where.trend_map(s, var_id="sst")
    assert got["status"] == "not_available" and got.get("transient") is True
    assert "did not answer" in got["reason"]
    assert s.ledger.n_tests == 0 and s.map == []


def test_big_box_gets_a_larger_stride(grid_calls):
    where.trend_map(_session(half=2.0), var_id="sst")  # 4° of MUR at 100 cells/degree = 400 cells
    assert grid_calls[0]["stride"] == 2
    assert where.stride_for((0, 0, 0.2, 0.2), 100) == 1
    assert where.capped_size((500, 250)) == (200, 100)
    assert where.capped_size((120, 80)) == (120, 80)


def test_chlorophyll_is_mapped_on_log10(monkeypatch):
    def fake(dataset, variable, bbox, start, end, stride, client=None, cache_dir=None):
        grid = _sea_grid(start, end + 1)  # runs past the study period
        return np.exp(grid / 10.0).assign_attrs(missing_years=[2010])

    monkeypatch.setattr(erddap, "fetch_grid", fake)
    got = where.trend_map(_session(), var_id="chlorophyll")
    assert got["status"] == "ok", got
    assert got["unit"] == "log10(mg/m³) per decade" and got["map"]["years"] == [2003, 2024]
    assert got["map"]["missing_years"] == [2010]


# --------------------------------------------------------------------------- GIBS


def _gibs_tiles(monkeypatch, years_failed=()):
    """yearly_values stub: NDVI that greens in the north half; counts the years asked."""
    asked = []

    def fake_yearly(layer, bbox, years, client, months, size=None, table=None, workers=1, failed=None, saturated=None):
        w, h = size
        out = {}
        for y in years:
            asked.append(y)
            if y in years_failed:
                failed.add(y)
                continue
            grid = np.full((h, w), 0.4) + np.random.default_rng(y).normal(0, 0.003, (h, w))
            grid[: h // 2] += 0.01 * (y - 2003)
            out[y] = grid
            if saturated is not None:
                saturated[y] = 0.0
        return out

    monkeypatch.setattr(gibs_values, "yearly_values", fake_yearly)
    monkeypatch.setattr(gibs_values, "load_colormap", lambda client, layer: {(0, 0, 0): 0.0, (1, 1, 1): 0.01})
    return asked


def test_gibs_yearly_trend_map_and_its_cache(monkeypatch):
    asked = _gibs_tiles(monkeypatch, years_failed=(2015,))
    s = _session(tags=("vegetated",), lat=37.0, lon=-4.5)
    got = where.trend_map(s, var_id="ndvi_gibs")
    assert got["status"] == "ok", got
    assert got["basis"] == "annual" and got["map"]["area_test"]["n_years"] == 21
    assert got["map"]["missing_years"] == [2015]
    assert got["map"]["bounds"] == [-4.6, 36.9, -4.4, 37.1]  # GIBS draws the box itself
    assert got["precision"] == "palette step ≈ 0.01 NDVI"
    assert 0.3 < got["share_significant"] < 0.7
    assert s.map[-1]["op"] == "overlay" and "GIBS" in s.map[-1]["source"]
    assert len(asked) == 22
    # a second thread: every completed year comes from the disk cache, the failed one is asked again
    asked.clear()
    got2 = where.trend_map(_session(tags=("vegetated",), lat=37.0, lon=-4.5), var_id="ndvi_gibs")
    assert got2["status"] == "ok" and asked == [2015]
    assert got2["url"] != got["url"]  # a new, unguessable file per map


def test_gibs_grid_size_is_capped(monkeypatch):
    sizes = []
    _gibs_tiles(monkeypatch)
    real = gibs_values.fetch_annual_grids

    def spy(layer, bbox, start, end, size, **kw):
        sizes.append(size)
        return real(layer, bbox, start, end, size, **kw)

    monkeypatch.setattr(gibs_values, "fetch_annual_grids", spy)
    where.trend_map(_session(tags=("vegetated",), lat=37.0, lon=-4.5, half=1.0), var_id="ndvi_gibs")
    assert sizes and max(sizes[0]) <= where.MAX_SIDE
    assert max(gibs_layers.layer_size((-5.5, 36.0, -3.5, 38.0), gibs_values.layer_for(next(v for v in load_catalog() if v.id == "ndvi_gibs")))) > where.MAX_SIDE


def test_corrupt_grid_cache_is_refetched(monkeypatch, _dirs):
    asked = _gibs_tiles(monkeypatch)
    layer = gibs_values.layer_for(next(v for v in load_catalog() if v.id == "ndvi_gibs"))
    bbox, size = (-4.6, 36.9, -4.4, 37.1), (20, 20)
    gibs_values.fetch_annual_grids(layer, bbox, 2003, 2004, size)
    for path in (_dirs / "gibs_grids").rglob("*.npz"):
        path.write_bytes(b"junk")
    asked.clear()
    grids, _ = gibs_values.fetch_annual_grids(layer, bbox, 2003, 2004, size)
    assert asked == [2003, 2004] and set(grids) == {2003, 2004}


# --------------------------------------------------------------------------- route and files


def _client():
    app = FastAPI()
    app.include_router(maps.router)
    return TestClient(app)


def test_png_name_is_unguessable_uuid(grid_calls):
    a = where.trend_map(_session(), var_id="sst")
    b = where.trend_map(_session(lat=-17.0), var_id="sst")
    name_a, name_b = (r["url"].rsplit("/", 1)[1] for r in (a, b))
    assert name_a != name_b and maps.NAME_RE.fullmatch(name_a) and maps.NAME_RE.fullmatch(name_b)
    client = _client()
    r = client.get(a["url"])
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.parametrize(
    "path",
    [
        "/detective/maps/..%2F..%2Fpyproject.toml",
        "/detective/maps/%2e%2e%2fsecret.png",
        "/detective/maps/../../etc/passwd",
        "/detective/maps/abc.png",
        "/detective/maps/" + "0" * 32 + ".png",  # well formed but not there
        "/detective/maps/" + "A" * 32 + ".png",
        "/detective/maps/" + "0" * 32 + ".png.tmp",
    ],
)
def test_route_rejects_anything_but_an_existing_uuid_png(path, _dirs):
    (maps.MAPS_DIR).mkdir(parents=True, exist_ok=True)
    (_dirs / "secret.png").write_bytes(b"x")
    assert _client().get(path).status_code == 404


def test_png_is_written_atomically(monkeypatch):
    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        maps.write_png(np.zeros((4, 4, 4), dtype=np.uint8), (4, 4))
    assert list(maps.MAPS_DIR.iterdir()) == []  # no half-written file left behind


def test_cleanup_removes_only_old_map_files():
    folder = maps.MAPS_DIR
    folder.mkdir(parents=True)
    old, new, other = folder / ("a" * 32 + ".png"), folder / ("b" * 32 + ".png"), folder / "keep.txt"
    for p in (old, new, other):
        p.write_bytes(b"x")
    eight_days = time.time() - 8 * 86400
    os.utime(old, (eight_days, eight_days))
    os.utime(other, (eight_days, eight_days))
    assert maps.cleanup_old() == 1
    assert not old.exists() and new.exists() and other.exists()


def test_main_app_serves_the_route_and_registers_the_tool(grid_calls):
    from app.main import app

    got = where.trend_map(_session(), var_id="sst")
    client = TestClient(app)  # no lifespan: only the route is under test
    assert client.get(got["url"]).status_code == 200
    assert client.get("/detective/maps/" + "f" * 32 + ".png").status_code == 404
    assert "trend_map" in TOOLS


def test_not_this_place_reason_says_profile_first():
    assert "call profile_place first" in tools.NOT_THIS_PLACE_REASON


# --------------------------------------------------------------------------- fix round 1


def test_only_the_two_findings_are_quotable(grid_calls):
    s = _session()
    got = where.trend_map(s, var_id="sst")
    figures = s.ledger.figures()
    assert got["share_significant"] in figures and got["median_slope_per_decade"] in figures
    assert set(figures) == {got["share_significant"], got["median_slope_per_decade"]}
    for n in got["map"]["bounds"] + got["map"]["legend"]["range"] + [got["map"]["pixels"]]:
        assert n not in figures


def test_a_missing_png_is_drawn_again_from_the_caches(grid_calls):
    s = _session()
    got = where.trend_map(s, var_id="sst")
    path = maps.MAPS_DIR / got["url"].rsplit("/", 1)[1]
    first = path.read_bytes()
    path.unlink()  # cleaned up after 7 days
    again = where.trend_map(s, var_id="sst")
    assert again["url"] == got["url"] and path.read_bytes() == first
    assert s.ledger.n_tests == 1 and len(s.map) == 1  # no new test, no new op
    where.trend_map(s, var_id="sst")  # the file is there: nothing fetched
    assert len(grid_calls) == 2


def test_no_png_left_when_the_test_fails(grid_calls, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("ledger broke")

    monkeypatch.setattr(where, "_area_test", boom)
    got = where.trend_map(_session(), var_id="sst")
    assert got["status"] == "not_available"
    assert not maps.MAPS_DIR.exists() or list(maps.MAPS_DIR.glob("*.png")) == []


def test_png_is_north_up(monkeypatch):
    """Only the north half warms: PNG row 0 (top) is the clear, coloured half."""

    def fake(dataset, variable, bbox, start, end, stride, client=None, cache_dir=None):
        grid = _sea_grid(start, end, warming=0.0)
        years = (np.arange(grid.sizes["time"]) / 12.0)[:, None]
        north = grid["latitude"].values > -18.0  # ascending latitude: the north half is the end
        return (grid + xr.DataArray(0.05 * years * north[None, :], dims=("time", "latitude"))).assign_attrs(missing_years=[])

    monkeypatch.setattr(erddap, "fetch_grid", fake)
    got = where.trend_map(_session(), var_id="sst")
    with Image.open(maps.MAPS_DIR / got["url"].rsplit("/", 1)[1]) as im:
        alpha = np.asarray(im)[..., 3]
    assert (alpha[0, 1:] == 230).all()  # top row: clear trend (skip the transparent land cell)
    assert (alpha[-1] == 70).mean() > 0.8  # bottom row: mostly faded


def test_cell_edges():
    assert where.cell_edges(np.array([0.0, 1.0, 2.0]), np.array([10.0, 10.5]), 1.0) == [9.75, -0.5, 10.75, 2.5]
    assert where.cell_edges(np.array([5.0]), np.array([5.0]), 0.04) == pytest.approx([4.98, 4.98, 5.02, 5.02])


# --------------------------------------------------------------------------- final review fixes


def test_cached_trend_map_reflects_tests_logged_since(grid_calls, monkeypatch):
    from app.detective.ledger import TestRecord
    from app.stats.trend import TrendResult

    # a strong test alone (p=0.01 -> real) that cannot survive 20 tests (q=0.2)
    strong = TrendResult(264, 22.0, False, 0.5, 0.2, 0.8, 1.0, 0.5, 0.01, 1.0)
    monkeypatch.setattr(where, "mk_trend_test", lambda anomalies: strong)
    s = _session()
    got = where.trend_map(s, var_id="sst")
    assert got["verdict"] == "real"
    for i in range(19):
        s.ledger.add_test(TestRecord(f"x{i}", f"v{i}", "v", "trend", 0.5, 0.1, False, None))
    again = where.trend_map(s, var_id="sst")
    fresh = tools._corrected_fields(s, got["test_id"])
    assert again["evidence_id"] == got["evidence_id"] and s.ledger.n_tests == 20
    assert again["q_session"] == fresh["q_session"] and again["verdict"] == fresh["verdict"]
    assert again["direction"] == fresh["direction"]
    assert again["verdict"] != "real" and again["q_session"] == pytest.approx(0.2)
    assert len(grid_calls) == 1


def test_unprofiled_place_refusal_is_not_cached(grid_calls):
    got = where.trend_map(_session(tags=()), var_id="sst")
    assert got["status"] == "not_available" and "evidence_id" not in got and grid_calls == []
