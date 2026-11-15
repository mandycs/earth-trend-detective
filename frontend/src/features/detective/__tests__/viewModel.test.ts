import { test } from "node:test";
import assert from "node:assert/strict";
import { localDate, parseLatLon, turnCount, turnOutcomes, wrapTarget } from "../viewModel.ts";
import type { AnswerEvent, DetEvent, DoneEvent, PlaceEvent } from "../events.ts";
import type { Target } from "../request.ts";

const place = (thread: string): DetEvent => ({
  kind: "place",
  data: {
    thread_id: thread, follow_up: false, forked_from: null, id: "p", name: "P", lat: 1, lon: 2,
    bbox: [0, 0, 1, 1], tags: [], site_id: null, years: null,
  } satisfies PlaceEvent,
});
const answer = (text: string): DetEvent => ({
  kind: "answer", data: { text, checked: true, figures: [], source: "llm", not_measured: [] } satisfies AnswerEvent,
});
const done = (n: number): DetEvent => ({
  kind: "done", data: { thread_id: "t", n_tests: n, n_tests_branch: null, n_tool_calls: null } satisfies DoneEvent,
});

test("lat, lon parses with comma, space, semicolon and a real minus", () => {
  for (const s of ["36.87, -4.17", "36.87 -4.17", "36.87;−4.17", "  36.87 ,  -4.17  "]) {
    const r = parseLatLon(s);
    assert.ok(r.ok, s);
    if (r.ok) assert.deepEqual(r.target, { kind: "point", lat: 36.87, lon: -4.17 });
  }
});

test("lat, lon refuses junk and out-of-range values with a reason", () => {
  for (const s of ["", "abc", "36.87", "1, 2, 3", "1e3, 2"]) {
    const r = parseLatLon(s);
    assert.equal(r.ok, false, s);
  }
  const lat = parseLatLon("91, 0");
  assert.ok(!lat.ok && /Latitude/.test(lat.message));
  const lon = parseLatLon("0, 181");
  assert.ok(!lon.ok && /Longitude/.test(lon.message));
});

test("lon 180 wraps to -180; wrapTarget leaves boxes and cases alone", () => {
  const r = parseLatLon("0, 180");
  assert.ok(r.ok && r.target.kind === "point" && r.target.lon === -180);
  assert.deepEqual(wrapTarget({ kind: "point", lat: 1, lon: 190 }), { kind: "point", lat: 1, lon: -170 });
  const box: Target = { kind: "box", bbox: [0, 0, 1, 1] };
  assert.equal(wrapTarget(box), box);
});

test("each turn keeps its own answer and done", () => {
  const evs = [place("t"), answer("first"), done(3), place("t"), answer("second"), done(5)];
  const out = turnOutcomes(evs);
  assert.equal(out["ending-0"].answer?.text, "first");
  assert.equal(out["ending-0"].done?.n_tests, 3);
  assert.equal(out["ending-1"].answer?.text, "second");
  assert.equal(out["ending-1"].done?.n_tests, 5);
  assert.equal(turnCount(evs), 2);
  assert.equal(turnCount([]), 0);
});

test("done before the answer of the same turn is kept", () => {
  const out = turnOutcomes([place("t"), done(2), answer("a")]);
  assert.equal(out["ending-0"].answer?.text, "a");
  assert.equal(out["ending-0"].done?.n_tests, 2);
});

test("local date is YYYY-MM-DD with padding", () => {
  assert.equal(localDate(new Date(2026, 0, 5, 23, 59)), "2026-01-05");
  assert.equal(localDate(new Date(2026, 10, 15)), "2026-11-15");
});
