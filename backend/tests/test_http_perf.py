"""Transport details the web relies on: compressed JSON and cacheable static lists."""

from fastapi.testclient import TestClient

from app.main import app


def test_large_json_is_gzipped() -> None:
    r = TestClient(app).get("/variables", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"
    assert isinstance(r.json(), list)


def test_static_lists_are_cacheable() -> None:
    for path in ("/sites", "/variables"):
        r = TestClient(app).get(path)
        assert r.status_code == 200
        assert "max-age=" in r.headers.get("cache-control", "")


def test_tiny_answers_are_not_compressed() -> None:
    r = TestClient(app).get("/health", headers={"Accept-Encoding": "gzip"})
    assert "content-encoding" not in r.headers
