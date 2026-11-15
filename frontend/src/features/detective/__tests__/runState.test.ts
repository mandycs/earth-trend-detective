import { test } from "node:test";
import assert from "node:assert/strict";
import { CUT_MESSAGE, IDLE_RUN, STOP_MESSAGE, runReducer } from "../runState.ts";
import type { RunAction, RunState } from "../runState.ts";
import { PLACE } from "./fixtures.ts";
import type { DetEvent } from "../events.ts";

const run = (actions: RunAction[], from: RunState = IDLE_RUN): RunState => actions.reduce(runReducer, from);
const ev = (event: DetEvent): RunAction => ({ type: "event", event });
const DONE: DetEvent = { kind: "done", data: { thread_id: "th1", n_tests: 1, n_tests_branch: null, n_tool_calls: null } };
const THINK: DetEvent = { kind: "thinking", data: { text: "x" } };
const start: RunAction = { type: "start", mode: "live", keepThread: false };

test("end without done is cut", () => {
  const s = run([start, ev({ kind: "place", data: PLACE }), ev(THINK), { type: "end" }]);
  assert.equal(s.status, "cut");
  assert.equal(s.message, CUT_MESSAGE);
  assert.equal(s.events.length, 2);
});

test("end after done is finished", () => {
  const s = run([start, ev(THINK), ev(DONE), { type: "end" }]);
  assert.equal(s.status, "finished");
  assert.equal(s.message, null);
});

test("end after an error event is finished", () => {
  const s = run([start, ev({ kind: "error", data: { message: "boom" } }), { type: "end" }]);
  assert.equal(s.status, "finished");
});

test("stop after finished changes nothing", () => {
  const done = run([start, ev(DONE), { type: "end" }]);
  assert.equal(runReducer(done, { type: "stop" }), done);
});

test("stop while streaming keeps the steps", () => {
  const s = run([start, ev(THINK), { type: "stop" }]);
  assert.equal(s.status, "stopped");
  assert.equal(s.message, STOP_MESSAGE);
  assert.equal(s.events.length, 1);
});

test("first event moves connecting to streaming", () => {
  const s = run([start]);
  assert.equal(s.status, "connecting");
  assert.equal(runReducer(s, ev(THINK)).status, "streaming");
});

test("thread id follows the place event", () => {
  const s = run([start, ev({ kind: "place", data: PLACE })]);
  assert.equal(s.threadId, "th1");
  const d = run([start, ev({ kind: "done", data: { ...DONE.data, thread_id: "th2" } as never })]);
  assert.equal(d.threadId, "th2");
});

test("follow-up keeps the thread, new case drops it", () => {
  const first = run([start, ev({ kind: "place", data: PLACE }), ev(DONE), { type: "end" }]);
  const follow = runReducer(first, { type: "start", mode: "live", keepThread: true });
  assert.equal(follow.threadId, "th1");
  assert.equal(follow.events.length, 0);
  assert.equal(follow.status, "connecting");
  const fresh = runReducer(first, { type: "start", mode: "live", keepThread: false });
  assert.equal(fresh.threadId, null);
});

test("fail sets the message and reset goes idle", () => {
  const s = run([start, { type: "fail", message: "nope" }]);
  assert.equal(s.status, "failed");
  assert.equal(s.message, "nope");
  assert.deepEqual(runReducer(s, { type: "reset" }), IDLE_RUN);
});

test("events after stop are ignored", () => {
  const s = run([start, { type: "stop" }, ev(THINK)]);
  assert.equal(s.events.length, 0);
});

test("fail after stop or before any start is ignored", () => {
  const stopped = run([start, { type: "stop" }, { type: "fail", message: "late" }]);
  assert.equal(stopped.status, "stopped");
  assert.notEqual(stopped.message, "late");
  assert.deepEqual(runReducer(IDLE_RUN, { type: "fail", message: "x" }), IDLE_RUN);
});
