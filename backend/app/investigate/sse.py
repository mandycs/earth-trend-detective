"""Server-Sent Events framing plus a keepalive, so proxies do not cut a quiet stream.

The producer is a plain synchronous generator (the LLM and the data fetches block). It runs in a worker
thread that feeds a queue; the async side waits on the queue and, when nothing arrives for
`SSE_KEEPALIVE_SECONDS`, sends an SSE comment (`: keepalive`), which clients ignore. If the client goes
away the generator is cancelled, a stop flag is set and the worker closes the producer at its next event.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from collections.abc import AsyncIterator, Iterator
from typing import Any

DEFAULT_KEEPALIVE_SECONDS = 15.0
KEEPALIVE = ": keepalive\n\n"
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

_END = object()


def keepalive_seconds() -> float:
    """`SSE_KEEPALIVE_SECONDS` (default 15); a missing, bad or non-positive value falls back to the default."""
    try:
        value = float(os.environ.get("SSE_KEEPALIVE_SECONDS", DEFAULT_KEEPALIVE_SECONDS))
    except ValueError:
        return DEFAULT_KEEPALIVE_SECONDS
    return value if value > 0 else DEFAULT_KEEPALIVE_SECONDS


def frame(e: dict[str, Any]) -> str:
    return f"event: {e['event']}\ndata: {json.dumps(e['data'], ensure_ascii=False, allow_nan=False)}\n\n"


async def sse_stream(events: Iterator[dict[str, Any]], keepalive: float | None = None) -> AsyncIterator[str]:
    """Frames of `events`, with a keepalive comment after `keepalive` seconds without one."""
    interval = keepalive_seconds() if keepalive is None else keepalive
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    stop = threading.Event()

    def put(item: object) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, item)
        except RuntimeError:  # the loop is already closed
            stop.set()

    def work() -> None:
        try:
            for e in events:
                if stop.is_set():
                    break
                put(frame(e))
                if stop.is_set():
                    break
        except BaseException as exc:  # noqa: BLE001 - re-raised on the async side
            put(exc)
        finally:
            close = getattr(events, "close", None)
            if close is not None:
                try:
                    close()
                except Exception:  # noqa: BLE001
                    pass
            put(_END)

    worker = threading.Thread(target=work, name="sse-producer", daemon=True)
    worker.start()
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=interval)
            except asyncio.TimeoutError:
                yield KEEPALIVE
                continue
            if item is _END:
                return
            if isinstance(item, BaseException):
                raise item
            yield item
    finally:
        stop.set()
