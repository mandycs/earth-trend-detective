import { test } from "node:test";
import assert from "node:assert/strict";
import { chartFor, trendLines } from "../chart.ts";
import type { Investigation, Scene } from "../scenes.ts";

const P = (year: number, value: number) => ({ year, value });
const mk = (key: string, tool: string, result: Record<string, unknown> | null): Scene => ({
  key, kind: "evidence", question: null, mapOps: [], stamps: [], note: null, complete: true,
  tool: { id: key, tool, args: {}, state: "done", summary: null, result, evidenceId: null, reason: null },
});
const inv = (scenes: Scene[], verdicts: Record<string, { verdict: "real" | "likely" | "unknown"; direction: "up" | "down" | "flat" }> = {}): Investigation => ({
  place: null, scenes, answer: null, done: null, error: null, finished: true,
  board: { suspects: [], n_tests: 1, verdicts },
});
const chart = [{ year: 2000, value: 1 }, { year: 2001, value: 2 }, { year: 2002, value: 3 }];
const series = mk("s", "get_series", { series_id: "x:1", var_id: "x", label: "Rain", unit: "mm/day", chart });
const trend = (extra: Record<string, unknown> = {}) =>
  mk("t", "trend_test", { test_id: "t1", series_id: "x:1", var_id: "x", slope_per_decade: 10, ci_low: 0, ci_high: 20, unit: "mm/day per decade", too_short: false, verdict: "unknown", direction: "flat", ...extra });

test("trendLines exact", () => {
  const t = trendLines(chart.map((c) => P(c.year, c.value)), 10, 0, 20);
  assert.deepEqual(t.line, [P(2000, 1), P(2002, 3)]);
  assert.deepEqual(t.low, [P(2000, 2), P(2002, 2)]);
  assert.deepEqual(t.high, [P(2000, 0), P(2002, 4)]);
  const n = trendLines(chart, 10, null, 20);
  assert.deepEqual(n.low, n.line);
  assert.deepEqual(n.high, n.line);
});

test("get_series scene charts its own points, no trend", () => {
  const m = chartFor(inv([series]), series)!;
  assert.equal(m.label, "Rain");
  assert.equal(m.unit, "mm/day");
  assert.equal(m.points.length, 3);
  assert.deepEqual(m.years, [2000, 2002]);
  assert.equal(m.trend, null);
  assert.equal(m.verdict, null);
});

test("non-finite values are dropped", () => {
  const s = mk("s", "get_series", { var_id: "x", chart: [...chart, { year: 2003, value: null }, { year: 2004, value: Number.NaN }] });
  assert.equal(chartFor(inv([s]), s)!.points.length, 3);
});

test("trend_test scene borrows the series points and adds the trend", () => {
  const t = trend();
  const m = chartFor(inv([series, t], { t1: { verdict: "real", direction: "down" } }), t)!;
  assert.equal(m.points.length, 3);
  assert.equal(m.label, "Rain");
  assert.equal(m.unit, "mm/day");
  assert.deepEqual(m.trend!.line, [P(2000, 1), P(2002, 3)]);
  assert.deepEqual(m.verdict, { verdict: "real", direction: "down" });
});

test("too short gives no trend line", () => {
  const t = trend({ too_short: true });
  assert.equal(chartFor(inv([series, t]), t)!.trend, null);
  const u = trend({ slope_per_decade: null });
  assert.equal(chartFor(inv([series, u]), u)!.trend, null);
});

test("fewer than 2 points is null", () => {
  const s = mk("s", "get_series", { var_id: "x", chart: [{ year: 2000, value: 1 }] });
  assert.equal(chartFor(inv([s]), s), null);
  const t = trend({ series_id: "none" });
  assert.equal(chartFor(inv([t]), t), null);
});

test("compare is null", () => {
  const c = mk("c", "compare", { var_id: "x", chart });
  assert.equal(chartFor(inv([c]), c), null);
});
