import { test } from "node:test";
import assert from "node:assert/strict";
import { RECORDING_NAME, parseRecording, replaySchedule, targetFromRequest } from "../replay.ts";
import type { Recording } from "../replay.ts";

const rec = (ts: number[], event = "thinking"): Recording => ({
  question: "q", request: {}, started_at: "2026-11-15T10:00:00Z",
  events: ts.map((t_ms) => ({ t_ms, event, data: { text: "hm" } })),
});

test("rejects names outside the pattern", () => {
  for (const bad of ["../x", "", "Vinuela", "a/b", "a.json"]) assert.equal(RECORDING_NAME.test(bad), false, bad);
  for (const ok of ["vinuela", "lake-mead_2"]) assert.equal(RECORDING_NAME.test(ok), true, ok);
});

test("caps gaps", () => {
  assert.deepEqual(replaySchedule(rec([0, 100, 20000, 20100])).map((s) => s.atMs), [0, 100, 6100, 6200]);
});

test("honours a custom cap", () => {
  assert.deepEqual(replaySchedule(rec([0, 5000]), 1000).map((s) => s.atMs), [0, 1000]);
});

test("never goes back in time", () => {
  assert.deepEqual(replaySchedule(rec([0, 500, 300])).map((s) => s.atMs), [0, 500, 500]);
});

test("drops unknown events", () => {
  const r = rec([0, 100]);
  r.events[0] = { t_ms: 0, event: "mystery", data: {} };
  const s = replaySchedule(r);
  assert.equal(s.length, 1);
  assert.equal(s[0].event.kind, "thinking");
});

test("bad recording is null", () => {
  assert.equal(parseRecording({ question: "q" }), null);
  assert.equal(parseRecording(null), null);
  assert.equal(parseRecording({ question: "q", events: [{ event: 3 }] }), null);
  assert.equal(parseRecording({ question: "q", events: [] })?.events.length, 0);
});

test("target from request", () => {
  assert.deepEqual(targetFromRequest({ lat: 1, lon: 2 }), { kind: "point", lat: 1, lon: 2 });
  assert.deepEqual(targetFromRequest({ bbox: [1, 2, 3, 4] }), { kind: "box", bbox: [1, 2, 3, 4] });
  const c = targetFromRequest({ site_id: "vinuela", bbox: [1, 2, 3, 4] });
  assert.deepEqual(c, { kind: "case", siteId: "vinuela", name: "vinuela", bbox: [1, 2, 3, 4] });
  assert.equal(targetFromRequest({}), null);
});
