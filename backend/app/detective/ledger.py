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
# `map` / `legend`: a trend map's drawing data (bounds, colour range, pixel counts), never quoted.
_NON_FIGURE_KEYS = frozenset(
    {"chart", "series", "url", "bbox", "evidence_id", "p_value", "p", "q_session", "q", "map", "legend"}
)


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


def _record_state(t: TestRecord) -> dict:
    """A test record as JSON-safe data (no `TrendResult`: only what the verdict and the board read)."""
    return json_safe({f.name: getattr(t, f.name) for f in fields(TestRecord) if f.name != "result"})


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
    """Results and tests of one branch of a thread.

    `family` holds the p values of the thread's other tests (those of other branches, read
    from the store by stable key), so the correction covers every test the thread ever ran:
    a fork never drops earlier tests from the family.
    """

    def __init__(self) -> None:
        self.results: dict[str, dict] = {}
        self._by_key: dict[str, str] = {}
        self._tests: dict[str, TestRecord] = {}
        self._test_keys: dict[str, str] = {}  # test id -> stable key (tool call key + position in the call)
        self.family: dict[str, float] = {}  # stable key -> p of the thread's tests outside this branch

    @staticmethod
    def call_key(tool: str, args: Mapping) -> str:
        return f"{tool}:{json.dumps(dict(args), sort_keys=True, default=str)}"

    def cached(self, key: str) -> dict | None:
        eid = self._by_key.get(key)
        if eid is None:
            return None
        return {**self.results[eid], "evidence_id": eid}

    def tool_of(self, evidence_id: str) -> str | None:
        """The tool whose call gave this evidence id."""
        return next((k.split(":", 1)[0] for k, eid in self._by_key.items() if eid == evidence_id), None)

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
        """Tests logged in this branch (the next test id is built from it)."""
        return len(self._tests)

    def test_ids(self) -> list[str]:
        """Ids of this branch's tests, in the order they were logged."""
        return list(self._tests)

    def claim_tests(self, call_key: str, before: set[str]) -> None:
        """Give the tests logged since `before` their stable key: the call that logged them
        and their position in it (the same call in two branches is the same test)."""
        new = [tid for tid in self._tests if tid not in before and tid not in self._test_keys]
        for i, tid in enumerate(new):
            self._test_keys[tid] = f"{call_key}#{i}"

    def test_key(self, test_id: str) -> str:
        return self._test_keys.get(test_id, f"test:{test_id}")

    def keyed_tests(self) -> dict[str, dict]:
        """This branch's tests by stable key, as plain data (for the thread-wide store)."""
        return {self.test_key(t.id): _record_state(t) for t in self._tests.values()}

    def with_family(self, thread_tests: Mapping[str, Mapping]) -> None:
        """Count the thread's tests that are not in this branch into the correction."""
        own = {self.test_key(tid) for tid in self._tests}
        self.family = {str(k): _float(v.get("p_value")) for k, v in thread_tests.items() if str(k) not in own}

    def _extra(self) -> dict[str, float]:
        own = {self.test_key(tid) for tid in self._tests}
        return {k: p for k, p in self.family.items() if k not in own}

    def n_finite(self) -> int:
        """Tests with a finite p in the whole family (a test that could not run is not counted)."""
        own = sum(1 for t in self._tests.values() if math.isfinite(t.p_value))
        return own + sum(1 for p in self._extra().values() if math.isfinite(p))

    def n_finite_branch(self) -> int:
        return sum(1 for t in self._tests.values() if math.isfinite(t.p_value))

    def corrected(self) -> dict[str, tuple[float, Verdict, Direction]]:
        """(q, verdict, direction) of this branch's tests, BH over the whole family."""
        ps = {t.id: t.p_value for t in self._tests.values()}
        ps |= {f"\x00{k}": p for k, p in self._extra().items()}  # keys no test id can take
        qs = benjamini_hochberg(ps)
        out = {}
        for t in self._tests.values():
            q = qs[t.id]
            verdict, direction = classify(q, t.p_value, t.slope if t.slope is not None else 0.0)
            out[t.id] = (q, verdict, direction)
        return out

    def to_state(self) -> dict:
        """JSON-safe copy (no `TrendResult`: only the fields the verdict and the board read)."""
        tests = [_record_state(t) for t in self._tests.values()]
        return json_safe({"results": self.results, "by_key": self._by_key, "tests": tests, "test_keys": self._test_keys})

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
        ledger._test_keys = {str(k): str(v) for k, v in (state.get("test_keys") or {}).items()}
        return ledger

    def figures(self) -> list[float]:
        seen: list[float] = []
        for result in self.results.values():
            for n in _numbers(result):
                if n not in seen:
                    seen.append(n)
        return seen
