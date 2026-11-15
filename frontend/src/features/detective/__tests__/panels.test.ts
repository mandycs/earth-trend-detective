import { test } from "node:test";
import assert from "node:assert/strict";
import {
  askBlocker, boardToggleLabel, checkLine, compareSides, forkLine, historyEnabled, notMeasuredLine,
  recordedDate, replayLine, stepRow, toolLabel,
} from "../panels.ts";
import { chartView } from "../chartView.ts";
import type { ChartModel } from "../chart.ts";
import type { AnswerEvent } from "../events.ts";
import type { Scene } from "../scenes.ts";

const answer = (checked: boolean): AnswerEvent => ({ text: "t", checked, figures: [], source: "llm", not_measured: [] });
const done = { thread_id: "th", n_tests: 7, n_tests_branch: null, n_tool_calls: null };
const sc = (extra: Partial<Scene>): Scene => ({
  key: "k", kind: "evidence", question: null, tool: null, mapOps: [], stamps: [], note: null, complete: true, ...extra,
});
const tool = (name: string, state: "running" | "done" | "failed" | "unfinished") => ({
  id: "i", tool: name, args: {}, state, summary: null, result: null, evidenceId: null, reason: null,
});

test("tool labels are plain and fall back", () => {
  assert.equal(toolLabel("trend_test"), "Is it real?");
  assert.equal(toolLabel("years_needed"), "How many years would it take?");
  assert.equal(toolLabel("years_needed_for"), "How many years would it take?");
  assert.equal(toolLabel("solved_case"), "A solved case");
  assert.equal(toolLabel("frobnicate"), "Checking the data");
  assert.equal(toolLabel("toString"), "Checking the data");
});

test("ask blocker gives a visible reason", () => {
  assert.equal(askBlocker(null, "q"), "Pick a place first");
  assert.equal(askBlocker({ kind: "point", lat: 1, lon: 2 }, "   "), "Write a question");
  assert.equal(askBlocker({ kind: "point", lat: 1, lon: 2 }, "Hot?"), null);
});

test("check line, with and without done", () => {
  assert.equal(checkLine(answer(true), done), "✓ every figure checked · 7 tests run");
  assert.equal(checkLine(answer(false), done), "Not every figure could be checked · 7 tests run");
  assert.equal(checkLine(answer(true), null), "✓ every figure checked");
  assert.equal(checkLine(answer(false), null), "Not every figure could be checked");
});

test("replay and fork lines", () => {
  assert.equal(recordedDate("2026-11-15T09:30:00Z"), "15 Nov 2026");
  assert.equal(recordedDate("garbage"), "garbage");
  assert.equal(replayLine("2026-11-15T09:30:00Z"), "Replay of a recorded run · recorded 15 Nov 2026");
  assert.equal(replayLine(""), "Replay of a recorded run");
  assert.equal(forkLine(3, "trend of rain"), "Re-running from step 3: trend of rain");
  assert.equal(notMeasuredLine("Snow", "no data"), "Snow — no data");
  assert.equal(notMeasuredLine("Snow", null), "Snow");
});

test("step rows by state", () => {
  assert.deepEqual(stepRow(sc({ tool: tool("trend_test", "done") })), { icon: "✓", label: "Is it real?", state: "done" });
  assert.equal(stepRow(sc({ tool: tool("trend_test", "running") })).icon, "…");
  assert.equal(stepRow(sc({ tool: tool("trend_test", "failed") })).icon, "✕");
  assert.equal(stepRow(sc({ tool: tool("trend_test", "unfinished") })).icon, "✕");
  assert.equal(stepRow(sc({ kind: "opening" })).label, "The place");
  assert.equal(stepRow(sc({ kind: "error" })).icon, "✕");
  assert.equal(stepRow(sc({ kind: "note" })).label, "A note");
});

test("board toggle and history gate", () => {
  assert.equal(boardToggleLabel(3), "Case board (3 suspects)");
  assert.equal(boardToggleLabel(1), "Case board (1 suspect)");
  assert.equal(historyEnabled("finished", "live", "th"), true);
  assert.equal(historyEnabled("streaming", "live", "th"), false);
  assert.equal(historyEnabled("finished", "replay", "th"), false);
  assert.equal(historyEnabled("finished", "live", null), false);
});

test("compare sides", () => {
  const out = compareSides({
    a: { test_id: "t1", place: { lat: -12.345, lon: 4 }, years: [2000, 2020] },
    b: { test_id: "t2", place: { lat: 1, lon: 2 } },
  });
  assert.equal(out?.[0].place, "−12.35, 4.00");
  assert.equal(out?.[0].years, "2000–2020");
  assert.equal(out?.[1].years, null);
  assert.equal(out?.[1].testId, "t2");
  assert.equal(compareSides({ a: {} }), null);
  assert.equal(compareSides(null), null);
});

const model = (values: number[], trend = false): ChartModel => {
  const points = values.map((value, i) => ({ year: 2000 + i, value }));
  const last = points[points.length - 1].year;
  return {
    label: "Rain", unit: "mm", points, years: [2000, last], verdict: null,
    trend: trend
      ? {
        line: [{ year: 2000, value: 0 }, { year: last, value: 10 }],
        low: [{ year: 2000, value: 1 }, { year: last, value: 5 }],
        high: [{ year: 2000, value: -1 }, { year: last, value: 15 }],
      }
      : null,
  };
};

test("chart view places points and survives a zero range", () => {
  const v = chartView(model([1, 3, 2]), 100, 100, 0);
  assert.equal(v.path, "M0.0,100.0L50.0,0.0L100.0,50.0");
  assert.equal(v.min.point.value, 1);
  assert.equal(v.max?.point.value, 3);
  const flat = chartView(model([0, 0, 0]), 100, 100, 0);
  assert.ok(flat.dots.every((d) => Number.isFinite(d.y) && d.y === 50));
  assert.equal(flat.max, null);
  const flat5 = chartView(model([5, 5]), 100, 100, 0);
  assert.ok(flat5.dots.every((d) => d.y === 50));
});

test("chart view includes the band in the y-domain", () => {
  const v = chartView(model([2, 4, 6], true), 100, 160, 0);
  assert.ok(v.trend && v.band);
  // The high line's last value (15) is the top of the canvas.
  assert.ok(v.band.split(" ").some((p) => p.endsWith(",0.0")));
});
