"""`update_board`: the model writes a suspect on the case board; the code decides its status.

Not cached by the ledger (each call is an instruction) and logs no tests.
"""

from __future__ import annotations

from dataclasses import asdict

from app.detective import board
from app.detective.session import Session


def update_board(session: Session, suspect: str, status: str, evidence_ids: list[str], note: str) -> dict:
    update = {"suspect": suspect, "status": status, "evidence_ids": evidence_ids, "note": note}
    try:
        new_board = board.apply_update(session.board, update, session.ledger)
    except ValueError as exc:
        return {"status": "rejected", "reason": str(exc)}
    session.board = new_board
    entry = asdict(new_board[str(suspect).strip()])
    return {**entry, "n_tests": session.ledger.n_tests}
