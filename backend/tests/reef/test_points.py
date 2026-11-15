"""Reef points and cache location. ERDDAP request behaviour (brackets, cache, retries, error
bodies) is tested once, in tests/test_erddap.py, with the reef grids at its end."""

from app.extractors import erddap
from app.reef import points


def test_five_points_in_order():
    assert [p.id for p in points.REEF_POINTS] == ["north", "davies", "outer", "burdekin", "heron"]
    davies = points.REEF_POINTS[1]
    assert (davies.lat, davies.lon) == (-18.8, 147.6)


def test_chlorophyll_point_exists_and_cache_is_the_extractors():
    assert points.CHLOROPHYLL_POINT in {p.id for p in points.REEF_POINTS}
    assert points.DEFAULT_CACHE_DIR == erddap.DEFAULT_CACHE_DIR
    assert points.SITE_ID == "great_barrier_reef"
