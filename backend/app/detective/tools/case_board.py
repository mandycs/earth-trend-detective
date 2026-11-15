"""`update_board`: the model writes a suspect on the case board; the code decides its status.

Not cached by the ledger (each call is an instruction) and logs no tests. The note is the
model's own text on screen, so it is checked like a `thinking` line (`wording.screen_note`):
a note with a figure no tool returned, a cause claim or "proof" is not shown.
"""

from __future__ import annotations

from dataclasses import asdict

from app.detective import board
from app.detective.session import Session
from app.detective.wording import screen_note

NOTE_REMOVED = "The note was not shown: notes may only use figures from tool results and never claim a cause."


def update_board(session: Session, suspect: str, status: str, evidence_ids: list[str], note: str) -> dict:
    shown_note = screen_note(note, session)
    update = {"suspect": suspect, "status": status, "evidence_ids": evidence_ids, "note": shown_note}
    try:
        new_board = board.apply_update(session.board, update, session.ledger)
    except ValueError as exc:
        return {"status": "rejected", "reason": str(exc)}
    session.board = new_board
    entry = asdict(new_board[str(suspect).strip()])
    out = {**entry, "n_tests": session.ledger.n_finite()}
    if shown_note != (note or "").strip() and (note or "").strip():
        out["note_removed"] = NOTE_REMOVED
    return out
