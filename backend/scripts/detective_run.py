"""Record one real detective run: POST /detective, stream the SSE, save every event with its time offset.

    python scripts/detective_run.py --question "..." --lat 36.87 --lon -4.17 --out data/recordings/vinuela.json

The file holds `{"question", "request", "started_at", "events": [{"t_ms", "event", "data"}]}` and is what
the front replay reads. Nothing about headers, keys or the environment is printed or saved.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from pathlib import Path

import httpx


def parse_sse(lines: Iterable[str]) -> Iterator[tuple[str, dict]]:
    """Yield (event, data) per SSE message. Lines starting with ':' are comments; several `data:` lines join with a newline."""
    name = "message"
    data: list[str] = []
    for raw in lines:
        line = raw.rstrip("\r\n")
        if line == "":
            if data:
                yield name, _loads("\n".join(data))
            name, data = "message", []
        elif line.startswith(":"):
            continue
        else:
            field, _, value = line.partition(":")
            value = value[1:] if value.startswith(" ") else value
            if field == "event":
                name = value
            elif field == "data":
                data.append(value)
    if data:  # a stream cut without the final blank line
        yield name, _loads("\n".join(data))


def _loads(text: str) -> dict:
    try:
        value = json.loads(text)
    except ValueError:
        return {"raw": text}
    return value if isinstance(value, dict) else {"value": value}


def summary(event: str, data: dict) -> str:
    """One short line per event, for the terminal."""
    if event == "place":
        return f"{data.get('name')} ({data.get('lat')}, {data.get('lon')})"
    if event == "thinking":
        return str(data.get("text", ""))[:80]
    if event in ("tool_start", "tool_done", "tool_failed"):
        extra = data.get("reason") or data.get("summary") or ""
        return f"{data.get('tool')} {str(extra)[:70]}".strip()
    if event == "map":
        return str(data.get("op"))
    if event == "board":
        return ", ".join(f"{s.get('id')}={s.get('status')}" for s in data.get("suspects", []))[:100]
    if event == "answer":
        return f"checked={data.get('checked')} source={data.get('source')} {str(data.get('text', ''))[:60]}"
    if event == "done":
        return f"n_tests={data.get('n_tests')} n_tool_calls={data.get('n_tool_calls')}"
    if event == "error":
        return str(data.get("message", ""))[:100]
    return ""


def build_request(args: argparse.Namespace) -> dict:
    body: dict = {"question": args.question}
    if args.site_id:
        body["site_id"] = args.site_id
    else:
        body["lat"], body["lon"] = args.lat, args.lon
    if args.thread_id:
        body["thread_id"] = args.thread_id
    return body


def record(base_url: str, body: dict, timeout: float) -> list[dict]:
    events: list[dict] = []
    t0 = time.monotonic()
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
        with client.stream("POST", f"{base_url.rstrip('/')}/detective", json=body) as resp:
            if resp.status_code != 200:
                resp.read()
                raise SystemExit(f"HTTP {resp.status_code}: {resp.text[:200]}")
            for name, data in parse_sse(resp.iter_lines()):
                t_ms = int((time.monotonic() - t0) * 1000)
                events.append({"t_ms": t_ms, "event": name, "data": data})
                print(f"{t_ms:>7} ms  {name:<11} {summary(name, data)}", flush=True)
    return events


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-url", default="http://127.0.0.1:8766")
    ap.add_argument("--question", required=True)
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--site-id")
    ap.add_argument("--thread-id")
    ap.add_argument("--out")
    ap.add_argument("--timeout", type=float, default=600.0, help="seconds without data before giving up")
    args = ap.parse_args(argv)
    if not args.site_id and (args.lat is None or args.lon is None):
        ap.error("give --site-id or both --lat and --lon")

    body = build_request(args)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        events = record(args.base_url, body, args.timeout)
    except httpx.HTTPError as exc:
        print(f"request failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        doc = {"question": args.question, "request": body, "started_at": started, "events": events}
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"saved {len(events)} events to {out}")
    if not any(e["event"] == "done" for e in events):
        print("no done event", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
