import asyncio
import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.investigate.sse import KEEPALIVE, SSE_HEADERS, keepalive_seconds, sse_stream


def ev(n):
    return {"event": "step", "data": {"n": n}}


def collect(events, keepalive):
    async def run():
        return [x async for x in sse_stream(events, keepalive)]

    return asyncio.run(run())


def test_slow_producer_gets_keepalives_between_events():
    def slow():
        yield ev(1)
        time.sleep(0.35)
        yield ev(2)

    out = collect(slow(), 0.1)
    assert out[0].startswith("event: step")
    assert out[-1].startswith("event: step")
    assert out.count(KEEPALIVE) >= 2
    assert all(x == KEEPALIVE or x.startswith("event:") for x in out)


def test_fast_producer_has_no_keepalives():
    out = collect(iter([ev(1), ev(2), ev(3)]), 5)
    assert len(out) == 3 and KEEPALIVE not in out


def test_error_in_producer_propagates():
    def boom():
        yield ev(1)
        raise ValueError("x")

    async def run():
        got = []
        with pytest.raises(ValueError):
            async for x in sse_stream(boom(), 5):
                got.append(x)
        return got

    assert len(asyncio.run(run())) == 1


def test_disconnect_stops_producer():
    produced = []
    closed = threading.Event()

    def endless():
        try:
            n = 0
            while True:
                n += 1
                produced.append(n)
                yield ev(n)
                time.sleep(0.02)
        finally:
            closed.set()

    async def run():
        agen = sse_stream(endless(), 5)
        await agen.__anext__()
        await agen.aclose()  # what Starlette does when the client leaves

    asyncio.run(run())
    assert closed.wait(2)
    n = len(produced)
    time.sleep(0.1)
    assert len(produced) == n


def test_response_headers_and_keepalive_over_http(monkeypatch):
    monkeypatch.setenv("SSE_KEEPALIVE_SECONDS", "0.05")
    app = FastAPI()

    def slow():
        yield ev(1)
        time.sleep(0.2)
        yield ev(2)

    @app.get("/s")
    def s():
        return StreamingResponse(sse_stream(slow()), media_type="text/event-stream", headers=SSE_HEADERS)

    r = TestClient(app).get("/s")
    assert r.headers["x-accel-buffering"] == "no" and r.headers["cache-control"] == "no-cache"
    assert ": keepalive\n\n" in r.text and r.text.count("event: step") == 2


def test_env_parsing(monkeypatch):
    monkeypatch.delenv("SSE_KEEPALIVE_SECONDS", raising=False)
    assert keepalive_seconds() == 15
    monkeypatch.setenv("SSE_KEEPALIVE_SECONDS", "3")
    assert keepalive_seconds() == 3
    for bad in ("abc", "0", "-2"):
        monkeypatch.setenv("SSE_KEEPALIVE_SECONDS", bad)
        assert keepalive_seconds() == 15
