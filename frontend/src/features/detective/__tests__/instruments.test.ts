import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { parseRecording, replaySchedule } from "../replay.ts";
import { groupScenes } from "../scenes.ts";
import { questionReading, toolLine, varCatalog } from "../instruments.ts";

/** The live Lake Mead point run (recorded from the API on 15 Nov 2026). */
function meadRun() {
  const raw = JSON.parse(readFileSync(join(import.meta.dirname, "../../../../../backend/data/recordings/mead.json"), "utf8"));
  const rec = parseRecording(raw);
  assert.ok(rec);
  return groupScenes(replaySchedule(rec).map((e) => e.event), { ended: true });
}

test("each step names its instrument or method, with only the years the event carries", () => {
  const inv = meadRun();
  const vars = varCatalog(inv.scenes);
  const lines = inv.scenes.filter((s) => s.tool).map((s) => [s.tool!.tool, toolLine(s, vars)]);
  const by = (tool: string) => lines.filter(([t]) => t === tool).map(([, l]) => l);
  assert.deepEqual(by("profile_place"), ["MODIS land cover map · 2023"]);
  assert.deepEqual(by("get_series"), [
    "GRACE & GRACE-FO gravity satellites · Total water stored · 2003–2024",
    "NASA POWER · GPM rain satellites + MERRA-2 · Rainfall · 2003–2024",
    "NASA POWER · MERRA-2 weather model · Air temperature · 2003–2024",
  ]);
  assert.deepEqual(by("trend_test"), [
    "Trend test · Total water stored · 2003–2024 · month by month",
    "Trend test · Total water stored · 2014–2024 · month by month",
    "Trend test · Rainfall · 2003–2024 · year by year",
    "Trend test · Air temperature · 2003–2024 · month by month",
  ]);
  assert.deepEqual(by("climate_residual"), ["Climate check · Total water stored · against Rainfall, Air temperature, Rainfall over the past 12 months"]);
  assert.deepEqual(by("correlate"), ["Year-by-year match · Total water stored and Rainfall"]);
  assert.deepEqual(by("land_cover_change"), ["MODIS land cover · 2003 and 2023"]);
  assert.deepEqual(by("solved_case"), ["Solved case file · Lake Mead (USA)"]);
  // No jargon on the main line: the method names live in the disclosure only.
  for (const [, l] of lines) assert.doesNotMatch(l ?? "", /Mann|Kendall|Sen|Pearson|regression/i);
});

test("the question reading lists each record once, in order, and the methods behind them", () => {
  const r = questionReading(meadRun());
  assert.deepEqual(r.records.map((x) => x.label), ["Total water stored", "Rainfall", "Air temperature"]);
  assert.equal(r.records[0].instrument, "GRACE & GRACE-FO gravity satellites");
  assert.deepEqual(r.methods.map((m) => m.tool), ["trend_test", "climate_residual", "correlate", "land_cover_change"]);
  assert.match(r.methods[0].text, /Mann-Kendall/);
});

test("a step with nothing to name gets no line, and nothing is invented", () => {
  const inv = groupScenes([
    { kind: "place", data: { thread_id: "t", follow_up: false, forked_from: null, id: "p", name: "P", lat: 0, lon: 0, bbox: [0, 0, 1, 1], tags: [], site_id: null, years: null } },
    { kind: "tool_start", data: { id: "a", tool: "get_series", args: { var_id: "mystery" } } },
    { kind: "tool_done", data: { id: "a", tool: "get_series", summary: "", result: {}, evidence_id: null } },
    { kind: "tool_start", data: { id: "b", tool: "trend_test", args: {} } },
  ], { ended: true });
  const vars = varCatalog(inv.scenes);
  assert.equal(toolLine(inv.scenes[1], vars), null);
  assert.equal(toolLine(inv.scenes[2], vars), "Trend test");
  assert.equal(toolLine(inv.scenes[0], vars), null);
  assert.deepEqual(questionReading(inv).records, []);
});
