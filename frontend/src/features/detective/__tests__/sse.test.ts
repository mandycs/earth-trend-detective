import { test } from "node:test";
import assert from "node:assert/strict";
import { createSseParser } from "../sse.ts";
import type { SseMessage } from "../sse.ts";

function run(chunks: string[], end = true): SseMessage[] {
  const out: SseMessage[] = [];
  const p = createSseParser((m) => out.push(m));
  for (const c of chunks) p.push(c);
  if (end) p.end();
  return out;
}

test("parses event and data", () => {
  assert.deepEqual(run(['event: place\ndata: {"a":1}\n\n']), [{ event: "place", data: '{"a":1}' }]);
});

test("joins several data lines with \\n", () => {
  assert.deepEqual(run(["data: a\ndata: b\n\n"]), [{ event: "message", data: "a\nb" }]);
});

test("ignores comments and blocks without data", () => {
  assert.deepEqual(run([": ping\n\nevent: x\n\n"]), []);
});

test("CRLF and CR line ends", () => {
  assert.deepEqual(run(["event: a\r\ndata: 1\r\n\r\n"]), [{ event: "a", data: "1" }]);
  assert.deepEqual(run(["event: a\rdata: 1\r\r"]), [{ event: "a", data: "1" }]);
});

test("strips one leading space only", () => {
  assert.deepEqual(run(["data:  x\n\n"]), [{ event: "message", data: " x" }]);
});

test("every split position yields the same messages", () => {
  const s = ': ping\r\n\r\nevent: place\r\ndata: {"a":1}\r\n\r\nevent: tool\ndata: x\ndata: y\n\nevent: done\rdata: {}\r\r';
  const whole = run([s]);
  assert.equal(whole.length, 3);
  for (let i = 0; i <= s.length; i++) {
    assert.deepEqual(run([s.slice(0, i), s.slice(i)]), whole, `split at ${i}`);
  }
});

test("end flushes a last block without blank line", () => {
  assert.deepEqual(run(["event: done\ndata: {}"]), [{ event: "done", data: "{}" }]);
});
