"""State of one detective thread, shared by every tool call of that thread."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from app.catalog import Variable
from app.detective.board import Suspect
from app.detective.ledger import Ledger
from app.detective.place import Place


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


SESSIONS: dict[str, Session] = {}  # keyed by thread_id
