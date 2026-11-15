"""Ledger of one investigation thread.

Records every tool result and every statistical test, and recomputes
Benjamini-Hochberg over ALL tests of the thread so verdicts account for
everything the agent tried.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields, is_dataclass
from typing import Any

import numpy as np

from app.stats.fdr import benjamini_hochberg
from app.stats.trend import TrendResult
from app.stats.verdict import Direction, Verdict, classify

# p and q values are never figures the answer may quote.
_NON_FIGURE_KEYS = frozenset({"chart", "series", "url", "bbox", "evidence_id", "p_value", "p", "q_session", "q"})


@dataclass(frozen=True)
class TestRecord:
    __test__ = False  # not a pytest test class

    id: str
    var_id: str
    label: str
    kind: str  # "trend" | "correlate" | "residual" | "compare"
    p_value: float
    slope: float | None
    too_short: bool
    result: TrendResult | None


def json_safe(value: Any) -> Any:
    """`value` as plain JSON types: dataclasses and mappings to dicts, tuples to lists,
    numpy scalars to Python numbers, NaN and infinities to None."""
    if is_dataclass(value) and not isinstance(value, type):
        return json_safe(asdict(value))
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Mapping):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset, np.ndarray)):
        return [json_safe(v) for v in value]
    return str(value)


def _float(x: Any) -> float:
    return float("nan") if x is None else float(x)


def _numbers(value: Any) -> list[float]:
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [value]
    if isinstance(value, Mapping):
        return [n for k, v in value.items() if k not in _NON_FIGURE_KEYS for n in _numbers(v)]
    if isinstance(value, (list, tuple)):
        return [n for v in value for n in _numbers(v)]
    return []


class Ledger:
    def __init__(self) -> None:
        self.results: dict[str, dict] = {}
        self._by_key: dict[str, str] = {}
        self._tests: dict[str, TestRecord] = {}

    @staticmethod
    def call_key(tool: str, args: Mapping) -> str:
        return f"{tool}:{json.dumps(dict(args), sort_keys=True, default=str)}"

    def cached(self, key: str) -> dict | None:
        eid = self._by_key.get(key)
        if eid is None:
            return None
        return {**self.results[eid], "evidence_id": eid}

    def remember(self, key: str, result: dict) -> str:
        eid = f"e{len(self.results) + 1}"
        self.results[eid] = dict(result)
        self._by_key[key] = eid
        return eid

    def add_test(self, record: TestRecord) -> None:
        self._tests[record.id] = record

    def test(self, test_id: str) -> TestRecord | None:
        return self._tests.get(test_id)

    @property
    def n_tests(self) -> int:
        return len(self._tests)

    def corrected(self) -> dict[str, tuple[float, Verdict, Direction]]:
        qs = benjamini_hochberg({t.id: t.p_value for t in self._tests.values()})
        out = {}
        for t in self._tests.values():
            q = qs[t.id]
            verdict, direction = classify(q, t.p_value, t.slope if t.slope is not None else 0.0)
            out[t.id] = (q, verdict, direction)
        return out

    def to_state(self) -> dict:
        """JSON-safe copy (no `TrendResult`: only the fields the verdict and the board read)."""
        tests = [
            {f.name: getattr(t, f.name) for f in fields(TestRecord) if f.name != "result"}
            for t in self._tests.values()
        ]
        return json_safe({"results": self.results, "by_key": self._by_key, "tests": tests})

    @classmethod
    def from_state(cls, state: Mapping) -> Ledger:
        """Ledger rebuilt from `to_state()`; records come back with `result=None`, a NaN p stays NaN."""
        ledger = cls()
        ledger.results = {str(k): dict(v) for k, v in (state.get("results") or {}).items()}
        ledger._by_key = {str(k): str(v) for k, v in (state.get("by_key") or {}).items()}
        for t in state.get("tests") or []:
            slope = t.get("slope")
            ledger.add_test(
                TestRecord(
                    id=str(t["id"]),
                    var_id=str(t["var_id"]),
                    label=str(t["label"]),
                    kind=str(t["kind"]),
                    p_value=_float(t.get("p_value")),
                    slope=None if slope is None else float(slope),
                    too_short=bool(t["too_short"]),
                    result=None,
                )
            )
        return ledger

    def figures(self) -> list[float]:
        seen: list[float] = []
        for result in self.results.values():
            for n in _numbers(result):
                if n not in seen:
                    seen.append(n)
        return seen
