"""The detective graph: a real tool loop, a budget, a checked answer, a resumable case (all offline)."""

import json
from itertools import count

import numpy as np
import pandas as pd
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from app import gather
from app.catalog import load_catalog
from app.detective.graph import BUDGET_REACHED, build_graph, new_case
from app.detective.ledger import Ledger
from app.detective.persistence import series_namespace
from app.detective.place import Place
from app.detective.report import ledger_report
from app.detective.session import Session
from app.detective.tools import TOOLS, ToolSpec, data
from app.investigate import landcover
from app.investigate.landcover import LandCover

PLACE = Place(lat=37.0, lon=-4.5, bbox=(-4.6, 36.9, -4.4, 37.1), tags=("vegetated",))
CONFIG = {"configurable": {"thread_id": "thread-1"}}


class FakeModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kw):
        return self


def _synthetic(start=2003, end=2024, slope_per_year=0.05):
    idx = pd.date_range(f"{start}-01-01", f"{end}-12-01", freq="MS")
    t = np.arange(idx.size) / 12.0
    rng = np.random.default_rng(0)
    seasonal = 5 * np.sin(2 * np.pi * idx.month / 12)
    return pd.Series(10 + seasonal + slope_per_year * t + rng.normal(0, 0.2, idx.size), index=idx)


def _noisy(start, end, slope, seed):
    idx = pd.date_range(f"{start}-01-01", f"{end}-12-01", freq="MS")
    rng = np.random.default_rng(seed)
    return pd.Series(10 + slope * np.arange(idx.size) / 12 + rng.normal(0, 1, idx.size), index=idx)


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


def _start(question="Is it getting warmer here?"):
    return {"messages": [HumanMessage(question)], "case": new_case(PLACE)}


def _tool_messages(state):
    return [m for m in state["messages"] if isinstance(m, ToolMessage)]


def _graph(agent, narrator=None, max_tool_calls=40, max_seconds=None, store=None, saver=None):
    return build_graph(
        agent,
        narrator=narrator,
        max_tool_calls=max_tool_calls,
        max_seconds=max_seconds,
        checkpointer=saver or MemorySaver(),
        store=store if store is not None else InMemoryStore(),
    )


GOOD_ANSWER = "From 2003 to 2024, air temperature here went up. The value covers a data cell of about 50 km."


def test_graph_runs_tools_and_concludes(offline):
    agent = FakeModel(
        messages=iter(
            [
                _call("profile_place", {}, "c1", "First, what kind of place is this."),
                _call("get_series", {"var_id": "t2m"}, "c2", "Now the air temperature."),
                _call("trend_test", {"series_id": "t2m:2003-2024"}, "c3", "Is it really changing?"),
                AIMessage(content="I have what I need."),
                AIMessage(content=GOOD_ANSWER),  # conclude: same model narrates by default
            ]
        )
    )
    store = InMemoryStore()
    graph = _graph(agent, store=store)
    state = graph.invoke(_start(), CONFIG)

    tools = _tool_messages(state)
    assert [m.name for m in tools] == ["profile_place", "get_series", "trend_test"]
    assert [m.tool_call_id for m in tools] == ["c1", "c2", "c3"]
    series_msg = json.loads(tools[1].content)
    assert series_msg["status"] == "ok" and "chart" not in series_msg
    assert tools[1].artifact["chart"]  # the full result travels beside the message, for the front
    trend_msg = json.loads(tools[2].content)
    assert trend_msg["verdict"] == "real" and trend_msg["n_tests_so_far"] == 1

    assert state["tool_calls"] == 3
    answer = state["answer"]
    assert answer == {
        "text": GOOD_ANSWER,
        "checked": True,
        "figures": ["2003", "2024", "50"],
        "source": "llm",
        "n_tests": 1,
    }
    assert isinstance(state["messages"][-1], AIMessage) and state["messages"][-1].content == GOOD_ANSWER

    case = state["case"]
    assert [k.split(":")[0] for k in case["ledger"]["by_key"]] == ["profile_place", "get_series", "trend_test"]
    assert case["series_ids"] == ["t2m:2003-2024"]
    assert case["failures"] == []
    assert store.get(series_namespace("thread-1"), "t2m:2003-2024") is not None
    assert graph.get_state(CONFIG).values["case"] == case  # the checkpoint holds the case


def test_follow_up_resumes_the_case_from_checkpoint_and_store(offline):
    first = [
        _call("get_series", {"var_id": "t2m"}, "c1"),
        AIMessage(content="Done."),
        AIMessage(content="Air temperature data is ready."),
    ]
    second = [
        _call("trend_test", {"series_id": "t2m:2003-2024"}, "c2"),
        AIMessage(content="Done."),
        AIMessage(content="Air temperature went up from 2003 to 2024."),
    ]
    agent = FakeModel(messages=iter(first + second))
    graph = _graph(agent)
    graph.invoke(_start(), CONFIG)
    state = graph.invoke({"messages": [HumanMessage("Is that change real?")]}, CONFIG)

    assert len(offline) == 1  # the series came back from the store, not from the source
    assert json.loads(_tool_messages(state)[-1].content)["verdict"] == "real"
    assert state["tool_calls"] == 1  # the budget counts per run
    assert state["answer"]["checked"] is True and state["answer"]["n_tests"] == 1


def test_graph_stops_at_tool_budget(offline):
    ids = count(1)
    agent = FakeModel(messages=(_call("list_variables", {}, f"c{next(ids)}") for _ in count()))
    narrator = FakeModel(messages=iter([AIMessage(content="Nothing was tested yet.")]))
    state = _graph(agent, narrator=narrator, max_tool_calls=3).invoke(_start(), CONFIG)

    tools = _tool_messages(state)
    assert len(tools) == 3
    assert all(json.loads(m.content).get("variables") for m in tools)  # all three really ran
    assert len({m.tool_call_id for m in tools}) == 3
    assert state["tool_calls"] == 3
    assert state["answer"]["text"] == "Nothing was tested yet."


def test_budget_answers_pending_tool_calls_and_concludes(offline):
    agent = FakeModel(messages=iter([_call("list_variables", {}, "c1")]))
    narrator = FakeModel(messages=iter([AIMessage(content="Nothing was tested yet.")]))
    state = _graph(agent, narrator=narrator, max_seconds=0).invoke(_start(), CONFIG)

    tools = _tool_messages(state)
    assert [(m.tool_call_id, m.content) for m in tools] == [("c1", BUDGET_REACHED)]
    assert state["tool_calls"] == 0
    assert state["case"]["ledger"]["results"] == {}
    assert state["answer"]["source"] == "llm"


def test_tool_exception_is_a_failed_tool_message(offline, monkeypatch):
    def boom(session):
        raise RuntimeError("socket closed")

    monkeypatch.setitem(TOOLS, "list_variables", ToolSpec(boom, "x", TOOLS["list_variables"].args_schema))
    agent = FakeModel(
        messages=iter(
            [
                _call("list_variables", {}, "c1"),
                _call("no_such_tool", {}, "c2"),
                _call("get_series", {"start": 2003}, "c3"),  # missing var_id
                AIMessage(content="Done."),
                AIMessage(content="Nothing could be tested."),
            ]
        )
    )
    state = _graph(agent).invoke(_start(), CONFIG)

    contents = [json.loads(m.content) for m in _tool_messages(state)]
    assert [c["status"] for c in contents] == ["failed", "failed", "failed"]
    assert "socket closed" in contents[0]["reason"]
    assert [(f["tool"], f["id"]) for f in state["case"]["failures"]] == [
        ("list_variables", "c1"),
        ("no_such_tool", "c2"),
        ("get_series", "c3"),
    ]
    assert all(f["reason"] for f in state["case"]["failures"])
    assert state["answer"]["checked"] is True


def _tested_graph(narrations):
    agent = FakeModel(
        messages=iter(
            [
                _call("get_series", {"var_id": "t2m"}, "c1"),
                _call("trend_test", {"series_id": "t2m:2003-2024"}, "c2"),
                AIMessage(content="Done."),
            ]
        )
    )
    narrator = FakeModel(messages=iter([AIMessage(content=t) for t in narrations]))
    return _graph(agent, narrator=narrator), narrator


def test_conclude_rejects_invented_figure(offline):
    bad = "About 42 % of the warming here is not explained by the climate we measured — a clue, not proof."
    graph, narrator = _tested_graph([bad, bad, "never read"])
    answer = graph.invoke(_start(), CONFIG)["answer"]

    assert answer["source"] == "template"
    assert answer["checked"] is True  # written by code from the report, not by the model
    assert "42" not in answer["text"] and answer["text"]
    assert answer["n_tests"] == 1
    assert next(narrator.messages).content == "never read"  # exactly one retry


def test_conclude_accepts_a_fixed_retry(offline):
    bad = "About 42 % of the warming is new."
    graph, _ = _tested_graph([bad, "Air temperature went up from 2003 to 2024."])
    answer = graph.invoke(_start(), CONFIG)["answer"]
    assert answer["source"] == "llm" and answer["checked"] is True
    assert answer["text"] == "Air temperature went up from 2003 to 2024."


def test_conclude_rejects_saying_this_part_is_human(offline):
    graph, _ = _tested_graph(["Air temperature went up, and this part is human.", "Still, it is man-made."])
    answer = graph.invoke(_start(), CONFIG)["answer"]
    assert answer["source"] == "template"


def test_conclude_keeps_the_answer_short(offline):
    long = "Air temperature went up. It went up from 2003. It went up to 2024. It is up."
    graph, _ = _tested_graph([long, long])
    assert graph.invoke(_start(), CONFIG)["answer"]["source"] == "template"


def test_ledger_report_uses_session_corrected_verdicts(offline):
    s = Session(ledger=Ledger(), place=PLACE, catalog=load_catalog())
    data.profile_place(s)
    got = data.get_series(s, var_id="t2m")
    trend = data.trend_test(s, series_id=got["series_id"])
    report = ledger_report(s)

    row = next(r for r in report["variables"] if r["id"] == "t2m")
    assert row["label"] == "Air temperature"
    assert row["verdict"] == "real" and row["direction"] == "up"
    assert row["sen_slope_per_decade"] == trend["slope_per_decade"]
    assert row["residual_pct_non_climate"] is None
    assert (report["start"], report["end"]) == (2003, 2024)
    assert set(s.ledger.figures()) <= set(report["figures"])
    assert {50.0, 300.0} <= set(report["figures"])  # data-cell sizes may be stated
    assert report["n_tests"] == 1


def test_conclude_rejudges_the_board_into_the_case(offline):
    agent = FakeModel(
        messages=iter(
            [
                _call("get_series", {"var_id": "t2m"}, "c1"),
                _call("trend_test", {"series_id": "t2m:2003-2024"}, "c2"),
                _call(
                    "update_board",
                    {"suspect": "warming", "status": "supported", "evidence_ids": ["e2", "e9"], "note": "It rose."},
                    "c3",
                ),
                AIMessage(content="Done."),
            ]
        )
    )
    narrator = FakeModel(messages=iter([AIMessage(content="Air temperature went up from 2003 to 2024.")]))
    state = _graph(agent, narrator=narrator).invoke(_start(), CONFIG)
    suspect = state["case"]["board"]["warming"]
    assert suspect["status"] == "supported" and suspect["evidence"] == ["e2"] and suspect["dropped"] == ["e9"]
    assert json.loads(_tool_messages(state)[-1].content)["status"] == "supported"


def test_report_figures_exclude_p_and_q_and_the_answer_cannot_quote_them(offline, monkeypatch):
    from app.detective.nodes import check

    def weak(site, variables, catalog, start, end):  # a faint trend, so p and q are not 0
        return {v.id: _noisy(start, end, 0.01, 3).rename(v.id) for v in variables}

    monkeypatch.setattr(gather, "FETCHERS", {**gather.FETCHERS, "power": weak})
    s = Session(ledger=Ledger(), place=PLACE, catalog=load_catalog())
    got = data.get_series(s, var_id="t2m")
    trend = data.trend_test(s, series_id=got["series_id"])
    report = ledger_report(s, "Is it warmer?")
    assert 0 < trend["p_value"] < 1 and 0 < trend["q_session"] < 1
    assert trend["p_value"] not in report["figures"] and trend["q_session"] not in report["figures"]
    assert all("q_session" not in row for row in report["variables"])
    ok, _, rejected = check(f"The odds it is chance are {trend['p_value']}.", report)
    assert not ok and rejected



def test_ledger_report_carries_a_real_residual_row_and_the_template_uses_detective_wording(offline, monkeypatch):
    from app.detective.nodes import template_answer
    from app.detective.tools import analysis

    def fake_grace(site, variables, catalog, start, end):
        return {v.id: _noisy(start, end, -0.4, 1).rename(v.id) for v in variables}

    def flat_climate(site, variables, catalog, start, end):
        return {v.id: _noisy(start, end, 0.0, sum(map(ord, v.id))).rename(v.id) for v in variables}

    monkeypatch.setattr(gather, "FETCHERS", {**gather.FETCHERS, "grace": fake_grace, "power": flat_climate})
    s = Session(ledger=Ledger(), place=PLACE, catalog=load_catalog())
    data.trend_test(s, series_id=data.get_series(s, var_id="grace_tws")["series_id"])
    res = analysis.climate_residual(s, var_id="grace_tws")
    assert res["pct_not_explained"] is not None, {k: v for k, v in res.items() if k not in ("label",)}
    row = next(r for r in ledger_report(s)["variables"] if r["id"] == "grace_tws")
    assert row["residual_pct_non_climate"] == res["pct_not_explained"]
    assert row["residual_pct_range"] == res["pct_range"]
    text, _ = template_answer(ledger_report(s, "Is the water going down?"))
    assert "not explained by the climate we measured — a clue, not proof" in text, text
