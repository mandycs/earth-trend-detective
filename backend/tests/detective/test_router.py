"""POST /detective and the iterate endpoints: the investigation as events (all offline)."""

import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from app import gather
from app.detective import router as detective_router
from app.detective.persistence import open_persistence
from app.detective.tools import TOOLS, ToolSpec
from app.investigate import landcover
from app.investigate.landcover import LandCover
from app.main import app

POINT = {"lat": 37.0, "lon": -4.5}
GOOD_ANSWER = "From 2003 to 2024, air temperature here went up."


class FakeModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kw):
        return self


def _synthetic(start=2003, end=2024, slope_per_year=0.05):
    idx = pd.date_range(f"{start}-01-01", f"{end}-12-01", freq="MS")
    t = np.arange(idx.size) / 12.0
    rng = np.random.default_rng(0)
    seasonal = 5 * np.sin(2 * np.pi * idx.month / 12)
    return pd.Series(10 + seasonal + slope_per_year * t + rng.normal(0, 0.2, idx.size), index=idx)


@pytest.fixture
def offline(monkeypatch):
    calls = []

    def fake_power(site, variables, catalog, start, end):
        calls.append(tuple(v.id for v in variables))
        return {v.id: _synthetic(start, end).rename(v.id) for v in variables}

    monkeypatch.setattr(gather, "FETCHERS", {**gather.FETCHERS, "power": fake_power})
    cover = LandCover(year=2023, shares={"Croplands": 0.6, "Grasslands": 0.4})
    monkeypatch.setattr(landcover, "fetch_land_cover", lambda lat, lon, year, client=None: cover)
    return calls


def _call(name, args, cid, thinking="Checking."):
    return AIMessage(content=thinking, tool_calls=[{"name": name, "args": args, "id": cid}])


def _test_run(var, n, answer="Air temperature went up from 2003 to 2024."):
    """Agent + narrator messages for: get_series var, trend_test var, stop, answer."""
    return [
        _call("get_series", {"var_id": var}, f"{var}-s{n}", f"Now the {var} series."),
        _call("trend_test", {"series_id": f"{var}:2003-2024"}, f"{var}-t{n}", f"Is {var} really changing?"),
        AIMessage(content="I have what I need."),
        AIMessage(content=answer),
    ]


@pytest.fixture
def persistence():
    return MemorySaver(), InMemoryStore()


@pytest.fixture
def client_with(persistence):
    def make(messages, model=True, persist=None):
        fake = FakeModel(messages=iter(messages)) if model else None
        app.dependency_overrides[detective_router.get_detective_model] = lambda: fake
        app.dependency_overrides[detective_router.get_persistence] = lambda: persist or persistence
        return TestClient(app)

    yield make
    app.dependency_overrides.clear()


def _events(response):
    out = []
    for block in response.text.split("\n\n"):
        if not block.strip():
            continue
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def _post(client, **body):
    r = client.post("/detective", json={"question": "Is it getting warmer here?", **body})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")
    return _events(r)


def _done(events):
    assert events[-1][0] == "done"
    return events[-1][1]


def test_requires_location(client_with):
    client = client_with([])
    r = client.post("/detective", json={"question": "Is it warmer?"})
    assert r.status_code == 422
    assert "Pick a point or draw a box on the map first." in r.text
    r = client.post("/detective", json={"question": "Is it warmer?", "lat": 37.0})
    assert r.status_code == 422


def test_bbox_alone_is_a_location(client_with, offline):
    client = client_with([AIMessage(content="Nothing to test."), AIMessage(content="Nothing was tested yet.")])
    events = _post(client, bbox=[-4.6, 36.9, -4.4, 37.1])
    kind, place = events[0]
    assert kind == "place"
    assert place["bbox"] == [-4.6, 36.9, -4.4, 37.1]
    assert place["lat"] == pytest.approx(37.0) and place["lon"] == pytest.approx(-4.5)


def test_bad_bbox_is_rejected(client_with):
    client = client_with([])
    r = client.post("/detective", json={"question": "Is it warmer?", "bbox": [1, 2, 0, 3]})
    assert r.status_code == 422


def test_unknown_case(client_with):
    client = client_with([])
    r = client.post("/detective", json={"question": "Is it warmer?", "site_id": "atlantis"})
    assert r.status_code == 422
    assert "Unknown case." in r.text


def test_solved_case_place_copies_site_tags(client_with, offline):
    from app.sites import load_sites

    site = load_sites().sites[0]
    client = client_with([AIMessage(content="Nothing to test."), AIMessage(content="Nothing was tested yet.")])
    kind, place = _post(client, site_id=site.id)[0]
    assert kind == "place"
    assert place["site_id"] == site.id and place["tags"] == list(site.tags)
    assert place["bbox"] == list(site.bbox) and place["lon"] == site.point[0] and place["lat"] == site.point[1]


def test_no_model_streams_error(client_with):
    client = client_with([], model=False)
    events = _post(client, **POINT)
    assert events == [("error", {"message": "The investigator needs a language model key on the server."})]


def test_event_order(client_with, offline):
    client = client_with(_test_run("t2m", 1, GOOD_ANSWER))
    events = _post(client, **POINT)
    kinds = [k for k, _ in events]
    assert kinds == [
        "place",
        "thinking", "tool_start", "tool_done",
        "thinking", "tool_start", "tool_done", "board",  # the trend test changed the verdicts
        "board", "answer", "done",
    ]  # fmt: skip
    data = [d for _, d in events]
    assert data[1] == {"text": "Now the t2m series."}
    assert data[2] == {"id": "t2m-s1", "tool": "get_series", "args": {"var_id": "t2m"}}
    series_done = data[3]
    assert series_done["id"] == "t2m-s1" and series_done["tool"] == "get_series"
    assert series_done["result"]["chart"]  # the front's chart travels in the event
    assert series_done["evidence_id"] == "e1" and series_done["summary"]
    trend_done = data[6]
    assert trend_done["result"]["verdict"] == "real" and trend_done["evidence_id"] == "e2"
    verdicts = {"t1": {"verdict": "real", "direction": "up"}}
    assert data[7] == {"suspects": [], "n_tests": 1, "verdicts": verdicts}
    assert data[8] == {"suspects": [], "n_tests": 1, "verdicts": verdicts}
    assert data[9] == {"text": GOOD_ANSWER, "checked": True, "figures": ["2003", "2024"], "source": "llm"}
    done = data[10]
    assert done["n_tests"] == 1 and done["n_tests_branch"] == 1 and done["n_tool_calls"] == 2 and done["thread_id"]
    assert data[0]["thread_id"] == done["thread_id"]


def test_map_and_board_events(client_with, offline):
    messages = [
        _call("fly_to", {"bbox": [-5, 36, -4, 37], "pitch": 40}, "m1", "Let me frame the place."),
        _call("get_series", {"var_id": "t2m"}, "s1"),
        _call("trend_test", {"series_id": "t2m:2003-2024"}, "t1"),
        _call(
            "update_board",
            {"suspect": "warming", "status": "supported", "evidence_ids": ["e2"], "note": "The trend is real."},
            "b1",
        ),
        AIMessage(content="Done."),
        AIMessage(content=GOOD_ANSWER),
    ]
    events = _post(client_with(messages), **POINT)
    maps = [d for k, d in events if k == "map"]
    assert maps == [{"op": "fly_to", "bbox": [-5.0, 36.0, -4.0, 37.0], "pitch": 40.0, "bearing": 0.0}]
    boards = [d for k, d in events if k == "board"]
    assert len(boards) == 3  # after the test, when the board changed, and with the final answer
    assert boards[0]["suspects"] == [] and boards[0]["verdicts"] == {"t1": {"verdict": "real", "direction": "up"}}
    boards = boards[1:]
    suspect = boards[0]["suspects"][0]
    assert {k: suspect[k] for k in ("id", "status", "claimed", "evidence", "note", "downgraded")} == {
        "id": "warming",
        "status": "hint",  # the variable's own trend is not a link (board.py)
        "claimed": "supported",
        "evidence": ["e2"],
        "note": "The trend is real.",
        "downgraded": "no test links it to Air temperature",
    }
    assert boards[0]["n_tests"] == 1


def test_stream_tool_failure_becomes_event(client_with, offline, monkeypatch):
    def down(site, variables, catalog, start, end):
        raise TimeoutError("source slow")

    monkeypatch.setattr(gather, "FETCHERS", {**gather.FETCHERS, "power": down})

    def broken(session, **kw):
        raise RuntimeError("boom at https://api.example.com/v1?api_key=SECRET in /srv/app/x.py")

    monkeypatch.setitem(TOOLS, "list_variables", ToolSpec(broken, "x", TOOLS["list_variables"].args_schema))
    messages = [
        _call("get_series", {"var_id": "t2m"}, "s1"),
        _call("list_variables", {}, "l1"),
        AIMessage(content="The source is down."),
        AIMessage(content="Nothing was tested yet."),
    ]
    events = _post(client_with(messages), **POINT)
    failed = [d for k, d in events if k == "tool_failed"]
    assert [f["id"] for f in failed] == ["s1", "l1"]
    assert failed[0]["tool"] == "get_series" and failed[0]["reason"]
    # an exception's text never reaches the UI, only the code's own sentence
    assert failed[1] == {"id": "l1", "tool": "list_variables", "reason": "The tool stopped with an error."}
    assert not [d for k, d in events if k == "tool_done"]  # never both
    assert _done(events)["n_tests"] == 0


def test_error_outside_tools_is_one_plain_event(client_with, monkeypatch):
    def explode(*a, **kw):
        raise RuntimeError("secret https://example.com/?key=abc")

    monkeypatch.setattr(detective_router, "build_graph", explode)
    events = _post(client_with([]), **POINT)
    assert [k for k, _ in events] == ["error"]
    assert "http" not in events[0][1]["message"] and "key" not in events[0][1]["message"]


def test_follow_up_keeps_the_fdr_family(client_with, offline):
    client = client_with(_test_run("t2m", 1) + _test_run("precip", 2))
    first = _done(_post(client, **POINT))
    events = _post(client, **POINT, thread_id=first["thread_id"])
    second = _done(events)
    assert second["thread_id"] == first["thread_id"]
    assert second["n_tests"] == 2  # the first run's test is still in the family
    assert second["n_tool_calls"] == 2  # the budget counts per run


def test_follow_up_elsewhere_starts_a_new_thread(client_with, offline):
    client = client_with(_test_run("t2m", 1) + _test_run("precip", 2))
    first = _done(_post(client, **POINT))
    second = _done(_post(client, lat=40.0, lon=-3.7, thread_id=first["thread_id"]))
    assert second["thread_id"] != first["thread_id"]
    assert second["n_tests"] == 1


def test_follow_up_after_restart(client_with, offline, tmp_path):
    db = tmp_path / "detective.sqlite"
    messages = _test_run("t2m", 1) + _test_run("precip", 2)
    saver, store = open_persistence(db)
    client = client_with(messages, persist=(saver, store))
    first = _done(_post(client, **POINT))
    detective_router.close_persistence(saver, store)

    reopened = open_persistence(db)  # a new process: new connections, new graph
    app.dependency_overrides[detective_router.get_persistence] = lambda: reopened
    second = _done(_post(client, **POINT, thread_id=first["thread_id"]))
    detective_router.close_persistence(*reopened)
    assert second["n_tests"] == 2
    assert len(offline) == 2  # the t2m series came back from the store, only precip was fetched


def test_history_lists_steps(client_with, offline):
    client = client_with(_test_run("t2m", 1))
    tid = _done(_post(client, **POINT))["thread_id"]
    r = client.get(f"/detective/{tid}/history")
    assert r.status_code == 200
    steps = r.json()
    assert [s.get("tool") for s in steps] == [None, "trend_test", "get_series"]  # newest first
    assert [s["n_tests"] for s in steps] == [1, 1, 0]
    assert steps[0]["kind"] == "answer" and steps[1]["kind"] == "tool"
    assert steps[1]["summary"]
    for s in steps:
        assert s["checkpoint_id"] and isinstance(s["step"], int) and s["created_at"]
    assert client.get("/detective/nope/history").status_code == 404


def test_fork_keeps_all_tests_of_the_thread_in_the_correction(client_with, offline):
    messages = [
        _call("get_series", {"var_id": "t2m"}, "s1"),
        _call("trend_test", {"series_id": "t2m:2003-2024"}, "t1"),
        _call("get_series", {"var_id": "precip"}, "s2"),
        _call("trend_test", {"series_id": "precip:2003-2024"}, "t2"),
        AIMessage(content="Done."),
        AIMessage(content="Air temperature went up from 2003 to 2024."),
        # the fork
        _call("get_series", {"var_id": "solar"}, "s3"),
        _call("trend_test", {"series_id": "solar:2003-2024"}, "t3"),
        _call("trend_test", {"series_id": "t2m:2003-2024"}, "t4"),  # cached: not a new test
        AIMessage(content="Done."),
        AIMessage(content="Air temperature went up from 2003 to 2024."),
    ]
    client = client_with(messages)
    first = _done(_post(client, **POINT))
    assert first["n_tests"] == 2
    steps = client.get(f"/detective/{first['thread_id']}/history").json()
    after_first_test = [s for s in steps if s.get("tool") == "trend_test"][-1]  # oldest trend_test
    assert after_first_test["n_tests"] == 1

    events = _post(
        client, **POINT, thread_id=first["thread_id"], checkpoint_id=after_first_test["checkpoint_id"]
    )
    forked = _done(events)
    assert forked["thread_id"] == first["thread_id"]
    # the branch holds t2m and solar; the family is every test the thread ever ran: t2m, precip, solar
    assert forked["n_tests_branch"] == 2
    assert forked["n_tests"] == 3
    assert forked["n_tool_calls"] == 3
    final_board = [d for k, d in events if k == "board"][-1]
    assert final_board["n_tests"] == 3


def test_fork_from_unknown_checkpoint(client_with, offline):
    client = client_with(_test_run("t2m", 1))
    tid = _done(_post(client, **POINT))["thread_id"]
    r = client.post("/detective", json={"question": "Again?", **POINT, "thread_id": tid, "checkpoint_id": "nope"})
    assert r.status_code == 404


def test_get_case_reopens_an_investigation(client_with, offline):
    messages = [
        _call("fly_to", {"bbox": [-5, 36, -4, 37]}, "m1"),
        *_test_run("t2m", 1),
    ]
    client = client_with(messages)
    tid = _done(_post(client, **POINT))["thread_id"]
    r = client.get(f"/detective/{tid}")
    assert r.status_code == 200
    case = r.json()
    assert case["thread_id"] == tid
    assert case["answer"] == {
        "text": "Air temperature went up from 2003 to 2024.",
        "checked": True,
        "figures": ["2003", "2024"],
        "source": "llm",
    }
    assert case["board"] == {"suspects": [], "n_tests": 1, "verdicts": {"t1": {"verdict": "real", "direction": "up"}}}
    assert [op["op"] for op in case["map"]] == ["fly_to"]
    assert case["place"]["lat"] == 37.0 and case["question"] == "Is it getting warmer here?"
    assert client.get("/detective/nope").status_code == 404


def test_persistence_opens_and_closes_with_the_app(tmp_path, monkeypatch):
    monkeypatch.setenv("DETECTIVE_DB", str(tmp_path / "d.sqlite"))
    with TestClient(app):  # runs the lifespan
        saver, store = detective_router.get_persistence()
        assert detective_router.get_persistence() == (saver, store)
        assert saver.conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert store.conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    with pytest.raises(Exception):
        saver.conn.execute("SELECT 1")
    assert detective_router._persistence is None


class DownModel(FakeModel):
    def _generate(self, *a, **kw):
        raise RuntimeError("401 invalid x-api-key")


def test_model_failure_is_shown(client_with, offline, persistence):
    app.dependency_overrides[detective_router.get_detective_model] = lambda: DownModel(messages=iter(()))
    app.dependency_overrides[detective_router.get_persistence] = lambda: persistence
    try:
        events = _post(TestClient(app), **POINT)
    finally:
        app.dependency_overrides.clear()
    failed = [d for k, d in events if k == "tool_failed"]
    assert failed == [{"id": None, "tool": "agent", "reason": "The model did not answer."}]
    answer = next(d for k, d in events if k == "answer")
    assert answer["source"] == "template" and answer["checked"] is True
    assert events[-1][0] == "done"


def test_made_up_thread_id_is_not_used(client_with, offline):
    client = client_with(_test_run("t2m", 1))
    events = _post(client, **POINT, thread_id="demo")
    assert events[0][1]["thread_id"] != "demo"
    assert _done(events)["thread_id"] == events[0][1]["thread_id"]
    assert len(events[0][1]["thread_id"]) == 32  # a uuid4 hex from the server
    assert client.get("/detective/demo").status_code == 404


def test_fork_with_a_checkpoint_of_another_thread(client_with, offline):
    client = client_with(_test_run("t2m", 1) + _test_run("t2m", 2))
    a = _done(_post(client, **POINT))["thread_id"]
    b = _done(_post(client, **POINT))["thread_id"]
    step_of_a = client.get(f"/detective/{a}/history").json()[0]["checkpoint_id"]
    r = client.post("/detective", json={"question": "Again?", **POINT, "thread_id": b, "checkpoint_id": step_of_a})
    assert r.status_code == 404


def test_reading_a_thread_builds_no_graph(client_with, offline, monkeypatch):
    client = client_with(_test_run("t2m", 1))
    tid = _done(_post(client, **POINT))["thread_id"]

    def no_graph(*a, **kw):
        raise AssertionError("a GET must not build the graph")

    monkeypatch.setattr(detective_router, "build_graph", no_graph)
    assert client.get(f"/detective/{tid}").status_code == 200
    assert client.get(f"/detective/{tid}/history").status_code == 200


def test_scrub_masks_links_keys_and_paths():
    from app.detective.events import scrub

    text = scrub(
        "failed at api.example.com/v1/x?a=1 and https://h.io/p; api_key=XYZ token: abc "
        "Bearer eyJabc in /home/user/app/x.py or C:\\Users\\me\\x.py, about 0.5 °C/decade"
    )
    for leak in ("example.com", "h.io", "XYZ", "abc", "eyJabc", "/home/user", "Users"):
        assert leak not in text
    assert "°C/decade" in text


# --------------------------------------------------------------------------- final review fixes


class StrictModel(FakeModel):
    """Refuses a conversation with a tool call left without its result, as the providers do."""

    def _generate(self, messages, *a, **kw):
        from langchain_core.messages import ToolMessage

        answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
        for m in messages:
            for call in getattr(m, "tool_calls", None) or []:
                if call["id"] not in answered:
                    raise ValueError("tool_use ids were found without tool_result blocks")
        return super()._generate(messages, *a, **kw)


def test_a_stopped_run_does_not_break_the_follow_up(offline):
    from app.detective.events import DetectiveRequest, prepare_run, stream_run
    from app.detective.graph import build_graph

    model = StrictModel(
        messages=iter(
            [
                _call("get_series", {"var_id": "t2m"}, "s1", "Now the air temperature."),
                # the follow-up
                _call("get_series", {"var_id": "t2m"}, "s2"),
                AIMessage(content="Done."),
                AIMessage(content="Nothing was tested yet."),
            ]
        )
    )
    graph = build_graph(model, checkpointer=MemorySaver(), store=InMemoryStore())
    run = prepare_run(graph, DetectiveRequest(question="Is it warmer?", **POINT))
    stream = stream_run(graph, run)
    for kind, _ in ((e["event"], e["data"]) for e in stream):
        if kind == "tool_start":
            break
    stream.close()  # the user stopped the run (or the server died) before the tool ran
    assert graph.get_state(run.config).next == ("tools",)

    follow = prepare_run(graph, DetectiveRequest(question="And now?", thread_id=run.thread_id, **POINT))
    events = [(e["event"], e["data"]) for e in stream_run(graph, follow)]
    assert not [d for k, d in events if k == "tool_failed"], events  # the model answered
    assert [d["tool"] for k, d in events if k == "tool_done"] == ["get_series"]
    answer = next(d for k, d in events if k == "answer")
    assert answer["source"] == "llm" and events[-1][0] == "done"


def test_thinking_with_an_unchecked_figure_or_a_cause_is_replaced(client_with, offline):
    probe = "Rain fell 47% since the dam was built, caused by farms."
    messages = [
        _call("get_series", {"var_id": "precip"}, "s1", probe),
        _call(
            "update_board",
            {"suspect": "farms", "status": "open", "evidence_ids": [], "note": probe},
            "b1",
            "Writing the suspect down.",
        ),
        AIMessage(content="Done."),
        AIMessage(content="Nothing was tested yet."),
    ]
    events = _post(client_with(messages), **POINT)
    thinking = [d["text"] for k, d in events if k == "thinking"]
    assert thinking == ["Next: get_series.", "Writing the suspect down."]
    start = next(d for k, d in events if k == "tool_start" and d["tool"] == "update_board")
    assert start["args"]["note"] == ""
    board = [d for k, d in events if k == "board"][-1]
    assert board["suspects"][0]["note"] == ""
    shown = json.dumps([d for k, d in events if k != "place"])
    assert "47%" not in shown and "caused by farms" not in shown


def test_a_broken_database_does_not_take_the_api_down(monkeypatch):
    def broken(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(detective_router, "open_persistence", broken)
    with TestClient(app) as client:  # the lifespan runs and must not raise
        assert client.get("/health").status_code == 200
        r = client.get("/detective/abc/history")
        assert r.status_code == 503
        assert "not ready" in r.json()["detail"]
    assert detective_router._persistence is None
