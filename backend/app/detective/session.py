"""State of one detective thread, shared by every tool call of that thread."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

import pandas as pd

from app.catalog import Variable
from app.detective.board import Suspect
from app.detective.ledger import Ledger, json_safe
from app.detective.persistence import load_series
from app.detective.place import Place

if TYPE_CHECKING:
    from langgraph.store.base import BaseStore


@dataclass
class Session:
    ledger: Ledger
    place: Place
    catalog: tuple[Variable, ...]
    series: dict[str, pd.Series] = field(default_factory=dict)  # series_id -> full monthly series
    start: int = 2003
    end: int = 2024
    map: list[dict] = field(default_factory=list)
    board: dict[str, Suspect] = field(default_factory=dict)  # suspect id -> Suspect (app.detective.board)

    def to_state(self) -> dict:
        """The case as JSON-safe data for the checkpoint: ledger, map and board together.

        The series themselves are not in it (they go to the store, see `persistence`), only their ids.
        Map ops are appended only when a result is computed fresh, so they must travel with the ledger.
        """
        return json_safe(
            {
                "place": asdict(self.place),
                "start": self.start,
                "end": self.end,
                "ledger": self.ledger.to_state(),
                "map": self.map,
                "board": {k: asdict(s) for k, s in self.board.items()},
                "series_ids": list(self.series),
            }
        )

    @classmethod
    def from_state(
        cls,
        state: Mapping,
        catalog: tuple[Variable, ...],
        store: BaseStore | None,
        thread_id: str,
    ) -> Session:
        """Session rebuilt from `to_state()`; series are read from the store, a missing one is skipped."""
        p = state["place"]
        place = Place(
            lat=float(p["lat"]),
            lon=float(p["lon"]),
            bbox=tuple(float(v) for v in p["bbox"]),
            tags=tuple(p.get("tags") or ()),
            site_id=p.get("site_id"),
        )
        series: dict[str, pd.Series] = {}
        if store is not None:
            for sid in state.get("series_ids") or []:
                s = load_series(store, thread_id, sid)
                if s is not None:
                    series[sid] = s
        return cls(
            ledger=Ledger.from_state(state["ledger"]),
            place=place,
            catalog=catalog,
            series=series,
            start=int(state.get("start", 2003)),
            end=int(state.get("end", 2024)),
            map=[dict(op) for op in state.get("map") or []],
            board={k: Suspect(**v) for k, v in (state.get("board") or {}).items()},
        )


SESSIONS: dict[str, Session] = {}  # keyed by thread_id
