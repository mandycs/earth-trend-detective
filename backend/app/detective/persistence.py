"""Where a detective thread lives between requests and restarts.

- The conversation and the JSON-safe case (`Session.to_state()`) go in the LangGraph
  checkpoint (`SqliteSaver`), so a thread can be resumed, replayed step by step and forked.
- The monthly series are too big for every checkpoint: they go in the LangGraph store
  (`SqliteStore`) under `("detective", thread_id, "series")`, one item per series id.
- Every test the thread ever logged, in any branch, goes in the store under
  `("detective", thread_id, "tests")`, append-only, keyed by a stable key (the tool call and
  the test's position in it). The correction runs over all of them, so a fork from an
  earlier step never drops a test from the family.
"""

from __future__ import annotations

import math
import os
import sqlite3
from pathlib import Path

import pandas as pd
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.base import BaseStore
from langgraph.store.sqlite import SqliteStore

from app.detective.ledger import json_safe

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "detective" / "detective.sqlite"
MEMORY = ":memory:"
SQLITE_TIMEOUT = 30.0
PAGE = 200


def series_namespace(thread_id: str) -> tuple[str, str, str]:
    return ("detective", thread_id, "series")


def tests_namespace(thread_id: str) -> tuple[str, str, str]:
    return ("detective", thread_id, "tests")


def save_tests(store: BaseStore, thread_id: str, tests: dict[str, dict]) -> None:
    """Append the thread's tests by stable key; a key already stored is never rewritten."""
    ns = tests_namespace(thread_id)
    for key, record in tests.items():
        if store.get(ns, key) is None:
            store.put(ns, key, json_safe(record))


def load_tests(store: BaseStore, thread_id: str) -> dict[str, dict]:
    """Every test the thread ever logged, in any branch (stable key -> record)."""
    ns, out, offset = tests_namespace(thread_id), {}, 0
    while True:
        page = store.search(ns, limit=PAGE, offset=offset)
        out |= {item.key: dict(item.value) for item in page}
        if len(page) < PAGE:
            return out
        offset += PAGE


def save_series(store: BaseStore, thread_id: str, series_id: str, s: pd.Series) -> None:
    """Store one monthly series: ISO dates, values (NaN as null), `attrs`, and its name."""
    values = [None if v is None or not math.isfinite(float(v)) else float(v) for v in s.to_numpy(dtype=float)]
    store.put(
        series_namespace(thread_id),
        series_id,
        {
            "index": [pd.Timestamp(t).date().isoformat() for t in s.index],
            "values": values,
            "attrs": json_safe(dict(s.attrs)),
            "name": json_safe(s.name),
        },
    )


def load_series(store: BaseStore, thread_id: str, series_id: str) -> pd.Series | None:
    """The stored series, or None when the store does not have it (the tool then re-fetches)."""
    item = store.get(series_namespace(thread_id), series_id)
    if item is None:
        return None
    v = item.value
    values = [float("nan") if x is None else float(x) for x in v.get("values") or []]
    s = pd.Series(values, index=pd.DatetimeIndex(v.get("index") or []), dtype=float, name=v.get("name"))
    s.attrs = dict(v.get("attrs") or {})
    return s


def _db_path(path: Path | str | None) -> str:
    if path is None:
        path = os.environ.get("DETECTIVE_DB") or DEFAULT_DB
    if str(path) == MEMORY:
        return MEMORY
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def open_persistence(path: Path | str | None = None) -> tuple[BaseCheckpointSaver, BaseStore]:
    """Checkpointer and store on one SQLite file (`DETECTIVE_DB`, else `backend/data/detective/`).

    Each gets its own connection (both are shared across threads, so `check_same_thread=False`).
    With `":memory:"` (tests) the two are separate in-memory databases.
    """
    db = _db_path(path)
    saver = SqliteSaver(_connect(db))
    saver.setup()
    store = SqliteStore(_connect(db, isolation_level=None))
    store.setup()
    return saver, store


def _connect(db: str, **kw) -> sqlite3.Connection:
    """A connection that waits for a busy file (30 s) and, on a file, uses WAL so readers never block."""
    conn = sqlite3.connect(db, check_same_thread=False, timeout=SQLITE_TIMEOUT, **kw)
    if db != MEMORY:
        conn.execute("PRAGMA journal_mode=WAL")
    return conn


def close_persistence(saver: BaseCheckpointSaver, store: BaseStore) -> None:
    """Close the connections `open_persistence` opened (other savers / stores are left alone)."""
    for holder in (saver, store):
        conn = getattr(holder, "conn", None)
        if isinstance(conn, sqlite3.Connection):
            conn.close()
