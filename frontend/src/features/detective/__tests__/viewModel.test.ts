import { test } from "node:test";
import assert from "node:assert/strict";
import {
  focusTargetFor, forkKeepTurns, forkTurn, localDate, parseLatLon, previewCamera, trimToTurn, turnCount, turnOutcomes, wrapTarget,
} from "../viewModel.ts";
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

test("focus goes to Stop when a live run starts, nowhere for a replay", () => {
  assert.equal(focusTargetFor("idle", "connecting", "live", false), "stop");
  assert.equal(focusTargetFor("finished", "connecting", "live", true), "stop");
  assert.equal(focusTargetFor("failed", "connecting", "live", false), "stop");
  assert.equal(focusTargetFor("idle", "connecting", "replay", false), null);
  assert.equal(focusTargetFor("connecting", "streaming", "live", false), null);
});

test("focus goes to the answer, or the scene, when a run ends", () => {
  assert.equal(focusTargetFor("streaming", "finished", "live", true), "answer");
  assert.equal(focusTargetFor("streaming", "finished", "replay", true), "answer");
  assert.equal(focusTargetFor("streaming", "finished", "live", false), "scene");
  assert.equal(focusTargetFor("streaming", "stopped", "live", false), "scene");
  assert.equal(focusTargetFor("connecting", "failed", "live", false), "scene");
  assert.equal(focusTargetFor("streaming", "cut", "live", false), "scene");
});

test("no focus move without a transition into or out of a run", () => {
  assert.equal(focusTargetFor("idle", "idle", "live", false), null);
  assert.equal(focusTargetFor("finished", "idle", "live", true), null);
  assert.equal(focusTargetFor("stopped", "failed", "live", false), null);
});

test("a fork step belongs to the turn of the answers before it", () => {
  const steps = [
    { step: 30, kind: "answer" }, { step: 24, kind: "tool" }, { step: 14, kind: "answer" }, { step: 4, kind: "tool" },
  ];
  assert.equal(forkTurn(steps, { step: 4, kind: "tool" }), 0);
  assert.equal(forkTurn(steps, { step: 14, kind: "answer" }), 0);
  assert.equal(forkTurn(steps, { step: 24, kind: "tool" }), 1);
  assert.equal(forkTurn(steps, { step: 30, kind: "answer" }), 1);
});

test("trimToTurn keeps turns up to and including the given one", () => {
  const evs = [place("t"), answer("a"), place("t"), answer("b"), place("t"), answer("c")];
  assert.equal(trimToTurn(evs, 0).length, 2);
  assert.equal(trimToTurn(evs, 1).length, 4);
  assert.equal(trimToTurn(evs, 5).length, 6);
  assert.equal(turnCount(trimToTurn(evs, 1)), 2);
});

test("preview camera frames the target with a negative seq", () => {
  const p = previewCamera({ kind: "point", lat: 36.87, lon: -4.17 }, 2);
  assert.equal(p.seq, -2);
  assert.equal(p.pitch, 0);
  assert.ok(p.bbox[0] < -4.17 && p.bbox[2] > -4.17 && p.bbox[1] < 36.87 && p.bbox[3] > 36.87);
  const c = previewCamera({ kind: "case", siteId: "x", name: "X", bbox: [1, 2, 3, 4] }, 1);
  assert.deepEqual(c.bbox, [1, 2, 3, 4]);
});

test("a fork keeps the turns before the step, and its own turn only from its answer", () => {
  const steps = [
    { step: 30, kind: "answer" }, { step: 24, kind: "tool" }, { step: 14, kind: "answer" }, { step: 4, kind: "tool" },
  ];
  assert.equal(forkKeepTurns(steps, { step: 4, kind: "tool" }), -1);
  assert.equal(forkKeepTurns(steps, { step: 14, kind: "answer" }), 0);
  assert.equal(forkKeepTurns(steps, { step: 24, kind: "tool" }), 0);
  assert.equal(forkKeepTurns(steps, { step: 30, kind: "answer" }), 1);
  const evs = [place("t"), answer("a")];
  assert.equal(trimToTurn(evs, -1).length, 0);
});

test("an answer that lands after the run is over takes the focus once", () => {
  assert.equal(focusTargetFor("finished", "finished", "live", true, false), "answer");
  assert.equal(focusTargetFor("finished", "finished", "live", true, true), null);
  assert.equal(focusTargetFor("idle", "idle", "live", true, false), null);
});
