"""The case as a report the narrator writes from and the validator checks against.

`ledger_report(session)` has the shape `app/explain/validator.validate_narrative` reads:
one row per tested variable (verdict and direction from the session-wide correction, read
now, never from a cached result), the period, and `figures`: every number any tool
returned, plus the data-cell sizes the tools gave as text ("~50 km") so the answer may
state them, plus the number of tests.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from typing import Any

from app.detective.ledger import Ledger
from app.detective.session import Session

_SIZE = re.compile(r"~\s*(\d+(?:\.\d+)?)\s*(?:km|m)\b")


def n_finite_tests(ledger: Ledger) -> int:
    """Tests with a finite p (a test that could not run is not counted in the answer)."""
    return sum(1 for tid in ledger.corrected() if math.isfinite(ledger.test(tid).p_value))


def _sizes(value: Any) -> Iterable[float]:
    if isinstance(value, str):
        for m in _SIZE.finditer(value):
            yield float(m.group(1))
    elif isinstance(value, Mapping):
        for v in value.values():
            yield from _sizes(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _sizes(v)


def _var(session: Session, var_id: str):
    return next((v for v in session.catalog if v.id == var_id), None)


def _trend_rows(session: Session, corrected: Mapping) -> dict[str, dict]:
    """One row per variable: its trend test over the most months (the first on a tie)."""
    best: dict[str, tuple[int, dict]] = {}
    for result in session.ledger.results.values():
        record = session.ledger.test(str(result.get("test_id")))
        if record is None or record.kind != "trend" or record.id not in corrected:
            continue
        months = int(result.get("n_months") or 0)
        if record.var_id in best and best[record.var_id][0] >= months:
            continue
        q, verdict, direction = corrected[record.id]
        var = _var(session, record.var_id)
        best[record.var_id] = (
            months,
            {
                "id": record.var_id,
                "label": record.label,
                "unit": var.units if var else "",
                "test_id": record.id,
                "verdict": str(verdict),
                "direction": str(direction),
                "q_session": None if not math.isfinite(q) else q,
                "sen_slope_per_decade": result.get("slope_per_decade"),
                "ci_low": result.get("ci_low"),
                "ci_high": result.get("ci_high"),
                "years_needed": result.get("years_needed"),
                "residual_pct_non_climate": None,
                "residual_pct_range": None,
            },
        )
    return {k: row for k, (_, row) in best.items()}


def _add_residuals(rows: dict[str, dict], session: Session, corrected: Mapping) -> None:
    for result in session.ledger.results.values():
        record = session.ledger.test(str(result.get("test_id")))
        if record is None or record.kind != "residual" or result.get("pct_not_explained") is None:
            continue
        row = rows.get(record.var_id)
        if row is None:  # a split without its own trend test: no verdict to claim
            var = _var(session, record.var_id)
            row = rows[record.var_id] = {
                "id": record.var_id,
                "label": var.label if var else record.var_id,
                "unit": var.units if var else "",
                "verdict": "unknown",
                "direction": "flat",
                "sen_slope_per_decade": None,
                "ci_low": None,
                "ci_high": None,
                "years_needed": None,
            }
        row["residual_pct_non_climate"] = result["pct_not_explained"]
        row["residual_pct_range"] = result.get("pct_range")
        _, verdict, _ = corrected[record.id]
        row["residual_verdict"] = str(verdict)


def ledger_report(session: Session, question: str | None = None) -> dict:
    corrected = session.ledger.corrected()
    rows = _trend_rows(session, corrected)
    _add_residuals(rows, session, corrected)
    figures = list(session.ledger.figures())
    for size in _sizes(list(session.ledger.results.values())):
        if size not in figures:
            figures.append(size)
    n_tests = n_finite_tests(session.ledger)
    if n_tests not in figures:
        figures.append(n_tests)
    report = {
        "variables": list(rows.values()),
        "start": session.start,
        "end": session.end,
        "figures": figures,
        "n_tests": n_tests,
    }
    if question:
        report["question"] = question  # the validator then keeps the answer to 3 sentences
    return report
