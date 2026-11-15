"""Seabed relief from GEBCO, clipped and labelled. Offline."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

from app.assets.relief import decode_terrain_rgb
from app.extractors import erddap
from app.layers import build_layers
from app.reef import relief

FIXTURE = Path(__file__).parent.parent / "fixtures" / "reef" / "gebco_tiny.csv"
BBOX = (146.9, -19.1, 147.2, -18.7)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_gebco_rows_run_north_to_south(tmp_path):
    client = _client(lambda r: httpx.Response(200, text=FIXTURE.read_text()))
    grid = relief.fetch_gebco(BBOX, tmp_path, client)
    assert grid.shape == (3, 2)
    # ERDDAP answers south first; the first row of the result is the northernmost (-18.8)
    assert grid[0].tolist() == [-1571.0, 40.0]
    assert grid[-1].tolist() == [-50.0, -60.0]


def test_offline_reads_cache_and_never_asks(tmp_path):
    relief.fetch_gebco(BBOX, tmp_path, _client(lambda r: httpx.Response(200, text=FIXTURE.read_text())))
    again = relief.fetch_gebco(BBOX, tmp_path, None, offline=True)
    assert again.shape == (3, 2)


def test_relief_is_clipped_and_labelled(tmp_path):
    elev = np.linspace(-1571, 1541, 40 * 60).reshape(40, 60)
    meta = relief.write_relief(elev, BBOX, tmp_path)
    saved = json.loads((tmp_path / "heightmap.json").read_text())
    assert saved == meta
    assert saved["min_m"] == -100 and saved["max_m"] == 800
    assert saved["raw_range_m"] == [-1571, 1541]
    assert saved["clipped_to"] == [-100, 800]
    assert saved["source_id"] == "GEBCO_2020"
    assert saved["source"] == "GEBCO_2020 (GEBCO Compilation Group)"
    assert saved["note"].startswith("Heights clipped to")
    for name in ("heightmap.png", "heightmap_rgb.png", "hillshade.png"):
        assert (tmp_path / name).is_file()
    decoded = decode_terrain_rgb(np.asarray(Image.open(tmp_path / "heightmap_rgb.png").convert("RGB")))
    assert decoded.min() >= -100.05 and decoded.max() <= 800.05
    assert abs(decoded.min() + 100) < 0.1 and abs(decoded.max() - 800) < 0.1


def test_reef_relief_source_is_gebco(tmp_path):
    elev = np.linspace(-1571, 1541, 40 * 60).reshape(40, 60)
    relief.write_relief(elev, BBOX, tmp_path)
    by_id = {la["id"]: la for la in build_layers("great_barrier_reef", tmp_path)["layers"]}
    for lid in ("relief", "hillshade"):
        assert "GEBCO" in by_id[lid]["source"]["name"] and "not NASA" in by_id[lid]["source"]["name"]
    assert by_id["relief"]["note"].startswith("Heights clipped")
    assert by_id["relief"]["range_m"] == [-100.0, 800.0]


def test_reef_base_is_modis_aqua(tmp_path):
    (tmp_path / "base.jpg").write_bytes(b"x")
    base = build_layers("great_barrier_reef", tmp_path)["layers"][0]
    assert base["id"] == "base"
    assert "Aqua" in base["source"]["name"]
    assert base["dates"] == ["2024-09-01"]
