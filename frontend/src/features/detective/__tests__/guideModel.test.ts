import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { parseRecording, replaySchedule } from "../replay.ts";
import { groupScenes } from "../scenes.ts";
import { EMPTY_VIEW, mapViewAt } from "../map/mapView.ts";
import type { MapView } from "../map/mapView.ts";
import {
  FRAMING, GENERIC_ITEMS, argsLine, howItWorks, landCoverWords, lookingAt, plainGuide, techGuide, toolCalls,
} from "../guide/guideModel.ts";
import { providerOfSource } from "../guide/datasets.ts";

function recorded(name: string) {
  const raw = JSON.parse(readFileSync(join(import.meta.dirname, `recordings/${name}.json`), "utf8"));
  const rec = parseRecording(raw);
  assert.ok(rec);
  const events = replaySchedule(rec).map((e) => e.event);
  const inv = groupScenes(events, { ended: true });
  return { rec, events, inv };
}

const MEAD_POINT = { kind: "point" as const, lat: 36.1, lon: -114.7 };

test("an empty globe gets the generic explanation", () => {
  const g = plainGuide(EMPTY_VIEW, null, null);
  assert.equal(g.generic, true);
  assert.deepEqual(g.items.map((i) => i.key), GENERIC_ITEMS.map((i) => i.key));
  assert.equal(g.framing, FRAMING);
  assert.equal(g.steps.length, 4);
  assert.match(g.steps[1].text, /water, rain, heat/);
});

test("the mead ending: pin, dashed square with its size from the event, the curtain years, land cover words", () => {
  const { inv } = recorded("mead");
  const view = mapViewAt(inv, inv.scenes.length - 1, { caseLayers: null });
  const items = lookingAt(view, MEAD_POINT);
  const keys = items.map((i) => i.key);
  assert.equal(keys[0], "pin");
  const cell = items.find((i) => i.mark === "cell");
  assert.ok(cell);
  assert.match(cell.text, /~300 km across/);
  const curtain = items.find((i) => i.key === "curtain");
  assert.ok(curtain);
  assert.match(curtain.text, /2003 on the left, 2023 on the right/);
  const layer = items.find((i) => i.key === "curtain-layer");
  assert.ok(layer);
  assert.match(layer.text, /red patches = cities/);
  assert.match(layer.text, /blue = water/);
});

test("every figure in the plain items comes from the view", () => {
  const { inv } = recorded("mead");
  const view = mapViewAt(inv, inv.scenes.length - 1, { caseLayers: null });
  const text = lookingAt(view, MEAD_POINT).map((i) => [i.title, i.text, ...i.lines].join(" ")).join(" ");
  const allowed = new Set(["300", "2003", "2023"]);
  for (const n of text.match(/\d+/g) ?? []) assert.ok(allowed.has(n), `unexpected figure ${n}`);
});

test("a yearly layer says the year drawn and carries its own legend words", () => {
  const view: MapView = {
    ...EMPTY_VIEW,
    evidence: {
      key: "k", layerId: "year_lst_day", title: "Daytime ground temperature: year by year", source: "MODIS via AppEEARS",
      resolution: "1000 m", legend: { unit: "°C", min: -3, max: 3, labels: ["↑ more heat (warmer ground) than usual"], stops: ["#00f", "#f00"] },
      render: { type: "image", url: "/x.png", bbox: [0, 0, 1, 1] }, opacity: 1, role: "evidence", year: 2019, date: null, period: null,
    },
  };
  const [it] = lookingAt(view, null);
  assert.match(it.text, /compared with its usual/);
  assert.deepEqual(it.lines, ["↑ more heat (warmer ground) than usual", "Showing 2019."]);
  assert.deepEqual(it.ramp, ["#00f", "#f00"]);
});

test("step 2 names the records this run fetched", () => {
  const { inv } = recorded("mead");
  assert.match(howItWorks(inv)[1].text, /Here: Total water stored, Rainfall, Air temperature\./);
});

test("land cover words only name classes the key shows", () => {
  assert.equal(landCoverWords([{ name: "Water", colours: ["blue"] }]), "Each color is a kind of ground: blue = water.");
});

test("under the hood: records with dataset, provider and period from events; tool calls in order", () => {
  const { inv, events } = recorded("mead");
  const view = mapViewAt(inv, inv.scenes.length - 1, { caseLayers: null });
  const t = techGuide(view, inv, events);
  const grace = t.records.find((r) => r.varId === "grace_tws");
  assert.ok(grace);
  assert.equal(grace.dataset, "TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4");
  assert.equal(grace.period, "2003–2024");
  assert.match(grace.provider ?? "", /JPL/);
  const t2m = t.records.find((r) => r.varId === "t2m");
  assert.equal(t2m?.resolution, "~50 km");
  assert.equal(t.calls.length, 18);
  assert.equal(t.calls[0].tool, "profile_place");
  assert.ok(t.calls.every((c) => c.state === "done"));
  assert.ok(t.calls.some((c) => c.tool === "trend_test" && c.args === 'series_id: "grace_tws:2003-2024", start: 2014'));
  assert.ok(t.methods.find((m) => m.tool === "climate_residual")?.used);
  assert.ok(t.layers.some((l) => l.role === "Data cell outline" && l.resolution === "~300 km"));
  // A yearly layer says its year, not the tile date it was drawn from.
  assert.deepEqual(t.layers.filter((l) => l.key.startsWith("curtain")).map((l) => l.when), ["2003", "2023"]);
});

test("tool calls: a failed call is marked, a running one stays running", () => {
  const calls = toolCalls([
    { kind: "tool_start", data: { id: "a", tool: "get_series", args: { var_id: "ndvi" } } },
    { kind: "tool_start", data: { id: "b", tool: "trend_test", args: {} } },
    { kind: "tool_failed", data: { id: "a", tool: "get_series", reason: "no data" } },
  ]);
  assert.deepEqual(calls.map((c) => c.state), ["failed", "running"]);
  assert.equal(argsLine({ var_id: "ndvi" }), 'var_id: "ndvi"');
});

test("non-NASA servers are labeled honestly", () => {
  assert.match(providerOfSource("NOAA CoastWatch ERDDAP") ?? "", /not NASA/);
  assert.match(providerOfSource("NASA MODIS ..., via GIBS") ?? "", /GIBS/);
});
