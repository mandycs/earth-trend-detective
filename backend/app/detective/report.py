"""The case as a report the narrator writes from and the validator checks against.

`ledger_report(session)` has the shape `app/explain/validator.validate_narrative` reads:
one row per tested variable (verdict and direction from the session-wide correction, read
now, never from a cached result), the period, and `figures`: every number any tool
returned, plus the data-cell sizes the tools gave as text ("~50 km") so the answer may
state them, plus the number of tests.

It also carries:
- `not_measured`: what could not be measured here and why: the `not_available` results, and the
  variables `list_variables` marked unavailable (a variable that was tested is never in it);
- `asked_not_measured`: labels of the variables the question names (catalog label or alias, e.g.
  "groundwater", "greener") that are in `not_measured` and have no measured row: the answer must
  say they could not be measured;
- `data_cells`: the data cells of the tested variables' sources that are bigger than the place
  (`{label, source, size_km}`), so the answer must say how big the cell is; their sizes are figures.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from typing import Any

from app.detective.cells import CELL_KM
from app.detective.ledger import Ledger
from app.detective.scrub import scrub
from app.detective.session import Session
from app.explain.vocab import VARIABLE_ALIASES

_SIZE = re.compile(r"~\s*(\d+(?:\.\d+)?)\s*(?:km|m)\b")
_NOT_HERE = re.compile(r"^not_available_here:\s*", re.IGNORECASE)
_FIRST_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_KM_PER_DEG = 111.32


def n_finite_tests(ledger: Ledger) -> int:
    """Tests with a finite p over the thread's whole family (a test that could not run is not counted)."""
    return ledger.n_finite()


def _plain_reason(reason: Any) -> str:
    text = _NOT_HERE.sub("", str(reason or "")).strip()
    text = _FIRST_SENTENCE.split(text, maxsplit=1)[0].rstrip(".").strip()
    return scrub(text)


def _not_measured_rows(session: Session, measured: set[str]) -> list[tuple[str | None, dict]]:
    """(var id, {label, reason}) of what the tools could not measure here: the `not_available`
    results first, then the variables `list_variables` marked unavailable. Tested variables are left out."""
    out: list[tuple[str | None, dict]] = []

    def add(var_id: str | None, label: str, reason_text: object) -> None:
        reason = _plain_reason(reason_text)
        if not reason or reason.lower().startswith("unknown "):  # a call the model got wrong, not the place
            return
        if var_id in measured:
            return
        row = {"label": label, "reason": reason}
        if all(r != row for _, r in out) and all(v != var_id or v is None for v, _ in out):
            out.append((var_id, row))

    listed: list[Mapping] = []
    for eid, result in session.ledger.results.items():
        if isinstance(result.get("variables"), list) and session.ledger.tool_of(eid) == "list_variables":
            listed += [r for r in result["variables"] if isinstance(r, Mapping)]
        if result.get("status") != "not_available":
            continue
        var_id = str(result.get("var_id") or "") or None
        var = _var(session, var_id or "")
        tool = session.ledger.tool_of(eid) or "a tool"
        label = var.label if var else str(result.get("label") or result.get("var_id") or tool.replace("_", " "))
        add(var_id, label, result.get("reason"))
    for row in listed:
        if row.get("available") is False:
            var = _var(session, str(row.get("id") or ""))
            add(str(row.get("id") or "") or None, var.label if var else str(row.get("label") or row.get("id")),
                row.get("reason"))
    return out


def _names(var_id: str, label: str) -> tuple[str, ...]:
    return tuple(n for n in (label.lower(), *VARIABLE_ALIASES.get(var_id, ())) if n)


def _named_in(text: str, names: Iterable[str]) -> bool:
    return any(re.search(r"\b" + re.escape(n), text) for n in names)


def _asked_not_measured(question: str | None, missing: list[tuple[str | None, dict]], rows: Mapping[str, dict]) -> list[str]:
    """Labels of the variables the question names that could not be measured (and have no measured row
    that answers to the same name, e.g. another source of the same variable)."""
    q = (question or "").lower()
    if not q:
        return []
    out: list[str] = []
    for var_id, row in missing:
        if var_id is None:
            continue
        names = _names(var_id, row["label"])
        if not _named_in(q, names):
            continue
        if any(_named_in(str(r.get("label") or "").lower(), names) for r in rows.values()):
            continue
        if row["label"] not in out:
            out.append(row["label"])
    return out


def _place_km(session: Session) -> float:
    w, s, e, n = session.place.bbox
    lat = math.radians((s + n) / 2)
    return max((e - w) * _KM_PER_DEG * max(math.cos(lat), 0.01), (n - s) * _KM_PER_DEG)


def _data_cells(session: Session, rows: Mapping[str, dict]) -> list[dict]:
    """Data cells of the tested variables' sources that are bigger than the place, one per source."""
    size = _place_km(session)
    out: list[dict] = []
    for var_id in rows:
        var = _var(session, var_id)
        km = CELL_KM.get(var.source) if var else None
        if km is None or km <= size or any(c["source"] == var.source for c in out):
            continue
        out.append({"label": var.label, "source": var.source, "size_km": float(km)})
    return out


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
        # annual tests count their years as months, so a short monthly test never outranks them
        months = int(result.get("n_months") or 12 * int(result.get("n_years") or 0))
        if record.var_id in best and best[record.var_id][0] >= months:
            continue
        _, verdict, direction = corrected[record.id]
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
    cells = _data_cells(session, rows)
    for cell in cells:
        if cell["size_km"] not in figures:
            figures.append(cell["size_km"])
    missing = _not_measured_rows(session, set(rows))
    report = {
        "variables": list(rows.values()),
        "start": session.start,
        "end": session.end,
        "figures": figures,
        "n_tests": n_tests,
        "not_measured": [row for _, row in missing],
        "asked_not_measured": _asked_not_measured(question, missing, rows),
        "data_cells": cells,
    }
    if question:
        report["question"] = question  # the validator then keeps the answer to 3 sentences
    return report
