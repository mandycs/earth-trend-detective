import json
import math

import numpy as np
import pandas as pd
import pytest

from app import gather
from app.catalog import load_catalog
from app.detective.board import apply_update, evaluate
from app.detective.ledger import Ledger, TestRecord
from app.detective.persistence import load_series, open_persistence, save_series
from app.detective.place import Place
from app.detective.session import Session
from app.detective.tools import analysis, data
from app.stats.trend import trend_test as mk_trend_test


def _monthly(start: int = 2003, end: int = 2024, slope_per_year: float = 0.05, seed: int = 0) -> pd.Series:
    idx = pd.date_range(f"{start}-01-01", f"{end}-12-01", freq="MS")
    t = np.arange(idx.size) / 12.0
    rng = np.random.default_rng(seed)
    seasonal = 5 * np.sin(2 * np.pi * idx.month / 12)
    return pd.Series(10 + seasonal + slope_per_year * t + rng.normal(0, 0.2, idx.size), index=idx)


def _session() -> Session:
    place = Place(lat=37.0, lon=-4.5, bbox=(-4.6, 36.9, -4.4, 37.1), tags=("agriculture",), site_id=None)
    return Session(ledger=Ledger(), place=place, catalog=load_catalog(), series={})


def _json_round_trip(state: dict) -> dict:
    return json.loads(json.dumps(state))  # no custom encoder: the state must be JSON-safe as is


def _same_corrected(a: dict, b: dict) -> None:
    assert a.keys() == b.keys()
    for k in a:
        (qa, va, da), (qb, vb, db) = a[k], b[k]
        assert (math.isnan(qa) and math.isnan(qb)) or qa == pytest.approx(qb)
        assert va == vb and da == db


@pytest.fixture
def store():
    _, st = open_persistence(":memory:")
    return st


# --------------------------------------------------------------------------- ledger


def test_ledger_round_trip_keeps_corrected_verdicts():
    led = Ledger()
    res = mk_trend_test(_monthly())
    led.add_test(TestRecord("t1", "t2m", "Air temperature", "trend", np.float64(0.001), np.float64(0.4), False, res))
    led.add_test(TestRecord("t2", "prec", "Rain", "trend", 0.3, -0.1, False, None))
    led.add_test(TestRecord("t3", "ndvi", "Greenness", "trend", float("nan"), None, True, None))
    led.remember('get_series:{"var_id": "t2m"}', {"status": "ok", "chart": [{"year": 2003, "value": np.float32(1.5)}]})
    led.remember("trend_test:x", {"test_id": "t1", "years": (2003, 2024), "p_value": float("nan")})

    back = Ledger.from_state(_json_round_trip(led.to_state()))

    _same_corrected(led.corrected(), back.corrected())
    assert back.n_tests == 3
    assert back.test("t1").result is None and back.test("t1").p_value == pytest.approx(0.001)
    assert math.isnan(back.test("t3").p_value) and back.test("t3").too_short is True
    assert back.cached('get_series:{"var_id": "t2m"}')["evidence_id"] == "e1"
    assert back.results["e2"]["years"] == [2003, 2024] and back.results["e2"]["p_value"] is None
    assert back.remember("k", {"status": "ok"}) == "e3"  # the evidence counter carries on


def test_board_works_on_a_restored_ledger_without_trend_results():
    led = Ledger()
    led.add_test(TestRecord("t1", "t2m", "Air temperature", "trend", 0.001, 0.4, False, mk_trend_test(_monthly())))
    led.add_test(TestRecord("t2", "prec", "Rain", "trend", 0.6, 0.01, False, None))
    led.remember("trend_test:a", {"test_id": "t1", "status": "ok"})
    led.remember("trend_test:b", {"test_id": "t2", "status": "ok"})
    back = Ledger.from_state(_json_round_trip(led.to_state()))
    assert all(back.test(t).result is None for t in ("t1", "t2"))

    board = apply_update({}, {"suspect": "heat", "status": "supported", "evidence_ids": ["e1"], "note": ""}, back)
    board = apply_update(board, {"suspect": "rain", "status": "ruled_out", "evidence_ids": ["e2"], "note": ""}, back)
    board = evaluate(board, back)
    assert board["heat"].status == "supported" and board["rain"].status == "ruled_out"


# --------------------------------------------------------------------------- session


def test_session_round_trip_without_series(store):
    s = _session()
    s.start, s.end = 2005, 2020
    s.series["t2m:2005-2020"] = _monthly(2005, 2020)
    s.ledger.add_test(TestRecord("t1", "t2m", "Air temperature", "trend", 0.001, 0.4, False, None))
    s.ledger.remember("trend_test:a", {"test_id": "t1", "status": "ok"})
    s.map.append({"op": "fly_to", "bbox": (1.0, 2.0, 3.0, 4.0), "pitch": np.float64(55.0), "bearing": 0.0})
    s.board = apply_update({}, {"suspect": "heat", "status": "supported", "evidence_ids": ["e1", "e9"], "note": "n"}, s.ledger)

    state = _json_round_trip(s.to_state())
    assert "series" not in state and state["series_ids"] == ["t2m:2005-2020"]

    back = Session.from_state(state, catalog=s.catalog, store=store, thread_id="th")
    assert back.place == s.place
    assert (back.start, back.end) == (2005, 2020)
    assert back.map == [{"op": "fly_to", "bbox": [1.0, 2.0, 3.0, 4.0], "pitch": 55.0, "bearing": 0.0}]
    assert back.board == s.board and back.board["heat"].dropped == ["e9"]
    _same_corrected(back.ledger.corrected(), s.ledger.corrected())
    assert back.series == {}  # nothing in the store: no crash, the tools re-fetch


def test_session_restores_series_from_the_store(store):
    s = _session()
    s.series["t2m:2003-2024"] = _monthly()
    for sid, series in s.series.items():
        save_series(store, "th", sid, series)
    back = Session.from_state(_json_round_trip(s.to_state()), catalog=s.catalog, store=store, thread_id="th")
    pd.testing.assert_series_equal(back.series["t2m:2003-2024"], s.series["t2m:2003-2024"], check_freq=False)


def test_get_series_refetches_a_series_missing_after_restore(monkeypatch, store):
    calls = []

    def fake_power(site, variables, catalog, start, end):
        calls.append(start)
        return {v.id: _monthly(start, end).rename(v.id) for v in variables}

    monkeypatch.setattr(gather, "FETCHERS", {**gather.FETCHERS, "power": fake_power})
    s = _session()
    first = data.get_series(s, "t2m")
    back = Session.from_state(_json_round_trip(s.to_state()), catalog=s.catalog, store=store, thread_id="th")
    again = data.get_series(back, "t2m")
    assert again["evidence_id"] == first["evidence_id"] and len(calls) == 2
    assert first["series_id"] in back.series
    assert data.trend_test(back, first["series_id"])["test_id"] == "t1"
    assert analysis._fetched(back, "t2m")[0] is not None


# --------------------------------------------------------------------------- store


def test_series_round_trip_through_store(store):
    s = _monthly(2003, 2006).rename("t2m")
    s.iloc[3] = np.nan
    s.attrs = {"units": "K", "source": "power"}
    save_series(store, "th", "t2m:2003-2006", s)
    back = load_series(store, "th", "t2m:2003-2006")
    pd.testing.assert_index_equal(back.index, s.index, exact=False, check_freq=False)
    np.testing.assert_allclose(back.to_numpy(), s.to_numpy(), equal_nan=True)
    assert back.attrs == s.attrs and back.name == "t2m"
    item = store.get(("detective", "th", "series"), "t2m:2003-2006")
    assert item.value["index"][0] == "2003-01-01" and item.value["values"][3] is None
    assert load_series(store, "th", "nope") is None
    assert load_series(store, "other", "t2m:2003-2006") is None


def test_persistence_survives_reopen(tmp_path):
    path = tmp_path / "sub" / "detective.sqlite"
    saver, st = open_persistence(path)
    save_series(st, "th", "a", _monthly(2003, 2004))
    config = {"configurable": {"thread_id": "th", "checkpoint_ns": ""}}
    checkpoint = {"v": 1, "id": "1f0", "ts": "2026-11-15T00:00:00+00:00", "channel_values": {"case": {"x": 1}},
                  "channel_versions": {}, "versions_seen": {}, "pending_sends": []}
    saver.put(config, checkpoint, {"source": "input", "step": 0}, {})
    saver.conn.close()
    st.conn.close()

    saver2, st2 = open_persistence(path)
    assert load_series(st2, "th", "a") is not None
    assert saver2.get_tuple({"configurable": {"thread_id": "th"}}).checkpoint["channel_values"] == {"case": {"x": 1}}


def test_open_persistence_reads_env(monkeypatch, tmp_path):
    path = tmp_path / "env" / "d.sqlite"
    monkeypatch.setenv("DETECTIVE_DB", str(path))
    open_persistence()
    assert path.exists()
