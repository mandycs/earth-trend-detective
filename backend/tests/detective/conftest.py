import pytest

from app.extractors import erddap


@pytest.fixture(autouse=True)
def _no_gebco_network(monkeypatch):
    """The sea check never reaches the network in tests: without a stub it fails (no sea tags)."""

    def down(*a, **k):
        raise erddap.ErddapError("offline in tests")

    monkeypatch.setattr(erddap, "fetch_min_elevation", down)
