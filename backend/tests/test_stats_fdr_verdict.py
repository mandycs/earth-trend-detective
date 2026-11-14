import math

import pytest

from app.stats.fdr import benjamini_hochberg
from app.stats.verdict import LIKELY_P, REAL_Q, Direction, Verdict, classify


def test_bh_qvalues_monotone_with_p_and_never_smaller():
    p = {"a": 0.001, "b": 0.04, "c": 0.03, "d": 0.5}
    q = benjamini_hochberg(p)
    assert set(q) == set(p)
    order = sorted(p, key=p.get)
    qs = [q[k] for k in order]
    assert qs == sorted(qs)
    for k in p:
        assert q[k] >= p[k]
    assert q["a"] == pytest.approx(0.004)
    # raw BH for c is 0.03*4/2 = 0.06, capped by the next rank (0.04*4/3)
    assert q["c"] == pytest.approx(0.04 * 4 / 3)
    assert q["d"] == pytest.approx(0.5)


def test_bh_skips_nan_and_handles_empty():
    q = benjamini_hochberg({"a": 0.01, "b": float("nan")})
    assert q["a"] == pytest.approx(0.01)
    assert math.isnan(q["b"])
    assert benjamini_hochberg({}) == {}


def test_verdict_rules():
    assert classify(REAL_Q / 2, 0.001, 1.0) == (Verdict.REAL, Direction.UP)
    assert classify(0.2, LIKELY_P / 2, -1.0) == (Verdict.LIKELY, Direction.DOWN)
    assert classify(0.2, 0.3, 1.0) == (Verdict.UNKNOWN, Direction.FLAT)
    assert classify(float("nan"), float("nan"), 1.0) == (Verdict.UNKNOWN, Direction.FLAT)
    assert classify(0.01, 0.001, 0.0) == (Verdict.REAL, Direction.FLAT)


def test_verdict_values_match_site_json():
    assert {v.value for v in Verdict} == {"real", "likely", "unknown"}
    assert {d.value for d in Direction} == {"up", "down", "flat"}
