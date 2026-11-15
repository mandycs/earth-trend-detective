"""The case board: suspects and the evidence for each, kept honest by the code.

The model asks for a status; the code decides what it may show:

- `supported` needs at least one evidence test whose Benjamini-Hochberg q (over every
  test of the thread) is below 0.05; otherwise it is shown as `hint`, flagged
  `downgraded = "fails correction over N tests"`.
- `ruled_out` needs an evidence test with no clear trend (verdict `unknown`) that had
  enough years (`too_short is False`); otherwise it is shown as `open`.

Later tests change the correction, so `evaluate` re-judges the whole board from the
status each suspect was claimed with. Every function returns a new board.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field, replace

from app.detective.ledger import Ledger
from app.stats.verdict import REAL_Q, Verdict

STATUSES = ("open", "supported", "hint", "ruled_out")
RULED_OUT_DOWNGRADE = "needs a test with enough years and no clear trend"


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


def _judge(suspect: Suspect, ledger: Ledger, corrected: Mapping) -> Suspect:
    tests = [t for e in suspect.evidence for t in (_test_ids(e, ledger, corrected) or []) if t in corrected]
    status, downgraded = suspect.claimed, None
    if suspect.claimed == "supported":
        if not any(corrected[t][0] < REAL_Q for t in tests):  # NaN q compares False
            n = ledger.n_finite()  # every test of the thread that ran, not only this branch
            status, downgraded = "hint", f"fails correction over {n} {'test' if n == 1 else 'tests'}"
    elif suspect.claimed == "ruled_out":
        if not any(corrected[t][1] == Verdict.UNKNOWN and not _too_short(ledger, t) for t in tests):
            status, downgraded = "open", RULED_OUT_DOWNGRADE
    return replace(suspect, status=status, downgraded=downgraded)


def _clean_ids(ids: Iterable[str] | None) -> list[str]:
    out: list[str] = []
    for i in ids or []:
        s = str(i).strip()
        if s and s not in out:
            out.append(s)
    return out


def apply_update(board: Mapping[str, Suspect], update: Mapping, ledger: Ledger) -> dict[str, Suspect]:
    """New board with `update` ({suspect, status, evidence_ids, note, label?}) applied and judged."""
    suspect_id = str(update.get("suspect") or "").strip()
    if not suspect_id:
        raise ValueError("a suspect name is needed")
    claimed = str(update.get("status") or "").strip()
    if claimed not in STATUSES:
        raise ValueError(f"unknown status {claimed!r}; use one of {', '.join(STATUSES)}")
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
    )
    return {**board, suspect_id: _judge(suspect, ledger, corrected)}


def evaluate(board: Mapping[str, Suspect], ledger: Ledger) -> dict[str, Suspect]:
    """New board re-judged against the correction as it stands now (call before every `board` event)."""
    corrected = ledger.corrected()
    return {k: _judge(s, ledger, corrected) for k, s in board.items()}


def as_json(board: Mapping[str, Suspect]) -> list[dict]:
    """The board as plain dicts, in insertion order, for the SSE `board` event."""
    return [asdict(s) for s in board.values()]
