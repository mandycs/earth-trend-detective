"""Suspects are possible reasons for the change, not the changing variable; a removed note is retried."""

from app.catalog import load_catalog
from app.detective.ledger import Ledger
from app.detective.place import Place
from app.detective.session import Session
from app.detective.tools import TOOLS

PLACE = Place(lat=37.0, lon=-4.5, bbox=(-4.6, 36.9, -4.4, 37.1), tags=("agriculture",))


def _session() -> Session:
    return Session(ledger=Ledger(), place=PLACE, catalog=load_catalog())


def test_a_suspect_measured_by_the_target_itself_is_rejected():
    s = _session()
    out = TOOLS["update_board"].fn(s, suspect="water going down", status="open", evidence_ids=[], note="",
                                   target_var="grace_tws", kind="climate", suspect_var="grace_tws")
    assert out["status"] == "rejected"
    assert "possible reason" in out["reason"]
    assert s.board == {}


def test_a_series_id_of_the_target_is_also_the_target():
    s = _session()
    out = TOOLS["update_board"].fn(s, suspect="x", status="open", evidence_ids=[], note="",
                                   target_var="grace_tws", suspect_var="grace_tws:2003-2024")
    assert out["status"] == "rejected"


def test_a_removed_note_asks_for_a_retry_and_says_why_without_the_figure():
    s = _session()
    out = TOOLS["update_board"].fn(s, suspect="farms", status="open", evidence_ids=[],
                                   note="Wells rose 47% since 2010, caused by farms.")
    assert out["note_removed"] and "update_board again" in out["note_removed"]
    assert out["note_problems"], out
    assert all("47" not in p and "caused" not in p for p in out["note_problems"]), out["note_problems"]
    assert s.board["farms"].note == ""
