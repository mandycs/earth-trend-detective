"""Where a detective thread lives between requests and restarts.

- The conversation and the JSON-safe case (`Session.to_state()`) go in the LangGraph
  checkpoint (`SqliteSaver`), so a thread can be resumed, replayed step by step and forked.
- The monthly series are too big for every checkpoint: they go in the LangGraph store
  (`SqliteStore`) under `("detective", thread_id, "series")`, one item per series id.
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


def series_namespace(thread_id: str) -> tuple[str, str, str]:
    return ("detective", thread_id, "series")


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
    saver = SqliteSaver(sqlite3.connect(db, check_same_thread=False))
    saver.setup()
    store = SqliteStore(sqlite3.connect(db, check_same_thread=False, isolation_level=None))
    store.setup()
    return saver, store
