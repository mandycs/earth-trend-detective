import pytest
from fastapi.testclient import TestClient

from app.assets import beforeafter, build, gibs_layers
from app.extractors import appeears
from app.main import app
from app.sites import PIPELINES, load_sites


def test_reef_site_loads():
    cat = load_sites()
    reef = cat.get("great_barrier_reef")
    assert reef is not None
    assert reef.bbox == (145.5, -21.0, 150.0, -17.0)
    assert reef.point == (147.6, -18.8)
    assert reef.pipeline == "sea"
    assert set(reef.tags) == {"ocean", "coast", "reef"}
    assert cat.get("lake_mead").pipeline == "land"
    assert PIPELINES == frozenset({"land", "sea"})


def test_unknown_pipeline_rejected(tmp_path):
    p = tmp_path / "sites.yaml"
    p.write_text(
        "study_period: [2003, 2024]\nsites:\n"
        "  - id: x\n    name: X\n    bbox: [0, 0, 1, 1]\n    point: [0.5, 0.5]\n"
        "    tags: [a]\n    pipeline: moon\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="pipeline"):
        load_sites(p)


def test_land_tools_skip_sea_sites():
    assert "great_barrier_reef" not in {s.id for s in appeears.load_sites()}
    for mod in (build, beforeafter, gibs_layers):
        ids = mod.default_site_ids()
        assert "great_barrier_reef" not in ids
        assert "lake_mead" in ids


def test_sweep_endpoint_refuses_sea_site():
    client = TestClient(app)
    r = client.get("/sites/great_barrier_reef/sweep")
    assert r.status_code == 409
    assert "precomputed" in r.json()["detail"]
    assert "great_barrier_reef" in {s["id"] for s in client.get("/sites").json()}
