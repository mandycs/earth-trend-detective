"""The case board: suspects and the evidence for each, kept honest by the code.

The model asks for a status; the code decides what it may show:

- `supported` needs at least one evidence test that LINKS the suspect to the variable under
  investigation (the target) and whose Benjamini-Hochberg q (over every test of the thread)
  is below 0.05. A link is a `correlate` test between the target and another series (any
  lag), or, for a non-climate suspect only, the `residual` test of the target with a real
  corrected verdict (the share not explained by the climate we measured is a real trend).
  Otherwise:
  - `trend_only` when the suspect's own trend survives the correction but no link does,
    flagged `downgraded = "its own trend is real, but no test links it to <target>"`;
  - `hint` otherwise, flagged `"fails correction over N tests"` (or `"no test links it to
    <target>"` when the only test that survives is not about the suspect at all).
- `ruled_out` needs an evidence test with no clear trend (verdict `unknown`) that had
  enough years (`too_short is False`); otherwise it is shown as `open`.

The target and the suspect's kind (climate / non_climate) come from the model's call; when
a call or a stored board has none, they are inferred: the target from the thread's residual
test, else its first trend-tested series (else series_a of its first correlate); the kind from whether the suspect's evidence
variables are climate drivers in the catalog.

Later tests change the correction, so `evaluate` re-judges the whole board from the
status each suspect was claimed with. Every function returns a new board.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field, replace
from functools import cache

from app.catalog import Variable, load_catalog
from app.detective.ledger import Ledger, TestRecord
from app.stats.verdict import REAL_Q, Verdict

STATUSES = ("open", "supported", "hint", "ruled_out")  # what the model may ask for
SHOWN_STATUSES = (*STATUSES, "trend_only")  # what the board may show
KINDS = ("climate", "non_climate")
RULED_OUT_DOWNGRADE = "needs a test with enough years and no clear trend"
NO_LINK = "no test links it to {target}"
TREND_NOT_LINKED = "its own trend is real, but no test links it to {target}"
UNKNOWN_TARGET = "the change under investigation"
_OWN_TREND_KINDS = ("trend", "compare", "residual")


@dataclass(frozen=True)
class Suspect:
    id: str
    label: str
    status: str  # what the board shows, after the code's checks
    evidence: list[str] = field(default_factory=list)
    note: str = ""
    downgraded: str | None = None
    claimed: str = "open"  # what the model asked for; re-judged on every read
    dropped: list[str] = field(default_factory=list)  # evidence ids that did not exist
    target_var: str | None = None  # variable whose change the suspect would explain (None: inferred)
    kind: str | None = None  # "climate" | "non_climate" (None: inferred)


@cache
def _default_catalog() -> tuple[Variable, ...]:
    return load_catalog()


def _test_ids(evidence_id: str, ledger: Ledger, known_tests: Mapping) -> list[str] | None:
    """Test ids behind one evidence id (a tool result), or the id itself if it is a test id."""
    result = ledger.results.get(evidence_id)
    if result is not None:
        ids = list(result.get("test_ids") or [])
        single = result.get("test_id")
        if isinstance(single, str) and single not in ids:
            ids.append(single)
        return ids
    if evidence_id in known_tests:
        return [evidence_id]
    return None


def _too_short(ledger: Ledger, test_id: str) -> bool:
    record = ledger.test(test_id)
    return True if record is None else record.too_short


def _var_id(value: object) -> str | None:
    """A variable id from what the model gave (a series id like 'grace_tws:2003-2024' counts)."""
    text = str(value or "").strip().split(":", 1)[0].strip()
    return text or None


def _sides(record: TestRecord) -> list[str]:
    """Variables a test is about (a correlate test is about both of its series)."""
    return record.var_id.split("~") if record.kind == "correlate" else [record.var_id]


def infer_target(ledger: Ledger) -> str | None:
    """The thread's target when the model gave none: the residual's variable, else the first
    trend-tested one, else series_a ("the series to explain") of the first correlate test."""
    records = [ledger.test(t) for t in ledger.test_ids()]
    for kind in ("residual", "trend", "correlate"):
        hit = next((r for r in records if r is not None and r.kind == kind), None)
        if hit is not None:
            return _sides(hit)[0]
    return None


def _infer_kind(records: Iterable[TestRecord], target: str | None, catalog: Iterable[Variable]) -> str:
    by_id = {v.id: v for v in catalog}
    climate = {v.id for v in by_id.values() if v.role == "driver"}
    if target in by_id:
        climate |= set(by_id[target].drivers)
    own = {side for r in records for side in _sides(r) if side != target}
    return "climate" if own & climate else "non_climate"


def _target_label(target: str | None, ledger: Ledger, catalog: Iterable[Variable]) -> str:
    if target is None:
        return UNKNOWN_TARGET
    var = next((v for v in catalog if v.id == target), None)
    if var is not None:
        return var.label
    record = next((r for r in map(ledger.test, ledger.test_ids()) if r and r.kind == "trend" and r.var_id == target), None)
    return record.label if record is not None else target


def _is_link(record: TestRecord, target: str | None, kind: str) -> bool:
    if target is None:
        return False
    if record.kind == "correlate":
        sides = _sides(record)
        return target in sides and any(s != target for s in sides)
    return record.kind == "residual" and record.var_id == target and kind == "non_climate"


def _link_holds(record: TestRecord, corrected_row: tuple) -> bool:
    q, verdict, _ = corrected_row
    if record.kind == "residual":
        return verdict == Verdict.REAL
    return q < REAL_Q  # NaN q compares False


def _judge_supported(suspect: Suspect, tests: list[str], ledger: Ledger, corrected: Mapping, catalog) -> tuple[str, str | None]:
    records = {t: ledger.test(t) for t in tests}
    records = {t: r for t, r in records.items() if r is not None}
    target = _var_id(suspect.target_var) or infer_target(ledger)
    kind = suspect.kind if suspect.kind in KINDS else _infer_kind(records.values(), target, catalog)
    if any(_is_link(r, target, kind) and _link_holds(r, corrected[t]) for t, r in records.items()):
        return "supported", None
    passes = {t for t in tests if corrected[t][0] < REAL_Q}
    label = _target_label(target, ledger, catalog)
    own = [
        t for t, r in records.items()
        if t in passes and r.kind in _OWN_TREND_KINDS and r.var_id != target and not _is_link(r, target, kind)
    ]
    if own:
        return "trend_only", TREND_NOT_LINKED.format(target=label)
    if passes:
        return "hint", NO_LINK.format(target=label)
    n = ledger.n_finite()  # every test of the thread that ran, not only this branch
    return "hint", f"fails correction over {n} {'test' if n == 1 else 'tests'}"


def _judge(suspect: Suspect, ledger: Ledger, corrected: Mapping, catalog: tuple[Variable, ...]) -> Suspect:
    tests = [t for e in suspect.evidence for t in (_test_ids(e, ledger, corrected) or []) if t in corrected]
    status, downgraded = suspect.claimed, None
    if suspect.claimed == "supported":
        status, downgraded = _judge_supported(suspect, tests, ledger, corrected, catalog)
    elif suspect.claimed == "ruled_out":
        if not any(corrected[t][1] == Verdict.UNKNOWN and not _too_short(ledger, t) for t in tests):
            status, downgraded = "open", RULED_OUT_DOWNGRADE
    return replace(suspect, status=status, downgraded=downgraded)


def _catalog(catalog: Iterable[Variable] | None) -> tuple[Variable, ...]:
    given = tuple(catalog or ())
    return given or _default_catalog()


def _clean_ids(ids: Iterable[str] | None) -> list[str]:
    out: list[str] = []
    for i in ids or []:
        s = str(i).strip()
        if s and s not in out:
            out.append(s)
    return out


def apply_update(
    board: Mapping[str, Suspect], update: Mapping, ledger: Ledger, catalog: Iterable[Variable] | None = None
) -> dict[str, Suspect]:
    """New board with `update` ({suspect, status, evidence_ids, note, label?, target_var?, kind?}) applied and judged."""
    suspect_id = str(update.get("suspect") or "").strip()
    if not suspect_id:
        raise ValueError("a suspect name is needed")
    claimed = str(update.get("status") or "").strip()
    if claimed not in STATUSES:
        raise ValueError(f"unknown status {claimed!r}; use one of {', '.join(STATUSES)}")
    kind = str(update.get("kind") or "").strip() or None
    corrected = ledger.corrected()
    requested = _clean_ids(update.get("evidence_ids"))
    evidence = [e for e in requested if _test_ids(e, ledger, corrected) is not None]
    dropped = [e for e in requested if e not in evidence]
    previous = board.get(suspect_id)
    suspect = Suspect(
        id=suspect_id,
        label=str(update.get("label") or (previous.label if previous else suspect_id)),
        status=claimed,
        evidence=evidence,
        note=str(update.get("note") or ""),
        claimed=claimed,
        dropped=dropped,
        target_var=_var_id(update.get("target_var")),
        kind=kind if kind in KINDS else None,
    )
    return {**board, suspect_id: _judge(suspect, ledger, corrected, _catalog(catalog))}


def evaluate(
    board: Mapping[str, Suspect], ledger: Ledger, catalog: Iterable[Variable] | None = None
) -> dict[str, Suspect]:
    """New board re-judged against the correction as it stands now (call before every `board` event)."""
    corrected = ledger.corrected()
    cat = _catalog(catalog)
    return {k: _judge(s, ledger, corrected, cat) for k, s in board.items()}


def as_json(board: Mapping[str, Suspect]) -> list[dict]:
    """The board as plain dicts, in insertion order, for the SSE `board` event."""
    return [asdict(s) for s in board.values()]
