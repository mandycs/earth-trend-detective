import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "detective_run", Path(__file__).resolve().parents[1] / "scripts" / "detective_run.py"
)
detective_run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(detective_run)
parse_sse = detective_run.parse_sse

SAMPLE = [
    ": keep-alive\n",
    "event: place\n",
    'data: {"id": "point", "lat": 37.0}\n',
    "\n",
    "event: thinking\n",
    'data: {"text":\n',
    'data:  "Now the t2m series."}\n',
    "\n",
    ": another comment\n",
    "event: tool_start\r\n",
    'data: {"id": "t1", "tool": "get_series", "args": {}}\r\n',
    "\r\n",
    "event: done\n",
    'data: {"n_tests": 1, "n_tool_calls": 2}\n',
    "\n",
]


def test_parses_events_in_order_skipping_comments():
    got = list(parse_sse(SAMPLE))
    assert [name for name, _ in got] == ["place", "thinking", "tool_start", "done"]
    assert got[0][1] == {"id": "point", "lat": 37.0}
    assert got[2][1]["tool"] == "get_series"
    assert got[3][1] == {"n_tests": 1, "n_tool_calls": 2}


def test_multiline_data_joins_with_newline():
    got = dict(parse_sse(SAMPLE))
    assert got["thinking"] == {"text": "Now the t2m series."}


def test_stream_cut_without_blank_line_keeps_last_event():
    assert list(parse_sse(["event: done\n", 'data: {"n_tests": 0}\n'])) == [("done", {"n_tests": 0})]


def test_bad_json_is_kept_raw_and_comments_alone_give_nothing():
    assert list(parse_sse(["data: nope\n", "\n"])) == [("message", {"raw": "nope"})]
    assert list(parse_sse([": hi\n", "\n"])) == []


def test_summary_is_short_and_json_safe():
    line = detective_run.summary("tool_failed", {"tool": "get_series", "reason": "plain"})
    assert line == "get_series plain"
    json.dumps(list(parse_sse(SAMPLE)))


def test_a_stream_cut_mid_run_still_saves_what_came(tmp_path, monkeypatch):
    import httpx

    def cut(base_url, body, timeout, sink):
        sink.append({"t_ms": 5, "event": "place", "data": {"id": "point"}})
        raise httpx.RemoteProtocolError("peer closed connection")

    monkeypatch.setattr(detective_run, "record", cut)
    out = tmp_path / "run.json"
    code = detective_run.main(["--question", "q", "--lat", "1", "--lon", "2", "--out", str(out)])
    assert code == 1
    doc = json.loads(out.read_text())
    assert [e["event"] for e in doc["events"]] == ["place"] and doc["partial"] is True
