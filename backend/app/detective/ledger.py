"""Ledger of one investigation thread.

Records every tool result and every statistical test, and recomputes
Benjamini-Hochberg over ALL tests of the thread so verdicts account for
everything the agent tried.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.stats.fdr import benjamini_hochberg
from app.stats.trend import TrendResult
from app.stats.verdict import Direction, Verdict, classify

_NON_FIGURE_KEYS = frozenset({"chart", "series", "url", "bbox", "evidence_id"})


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

    def figures(self) -> list[float]:
        seen: list[float] = []
        for result in self.results.values():
            for n in _numbers(result):
                if n not in seen:
                    seen.append(n)
        return seen
