import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { groupScenes } from "../scenes.ts";
import type { BoardEvent, DetEvent, MapOp, PlaceEvent } from "../events.ts";
import { EMPTY_VIEW, mapViewAt } from "../map/mapView.ts";
import type { CaseLayers, MapContext } from "../map/mapView.ts";
import type { CaseLayerRow } from "../map/types.ts";
import { catalogLayer, dateFor } from "../map/catalog.ts";
import { STACK_MAX, cellKmOf, stackFor } from "../stack/stackModel.ts";
import { PLACE, RUN_EVENTS } from "./fixtures.ts";

const NOW = "2026-11-15";
const NO_CASE: MapContext = { caseLayers: null, now: NOW };

function lakeMeadCase(): CaseLayers {
  const raw = readFileSync(join(import.meta.dirname, "../../../../../sites/lake_mead/layers.json"), "utf8");
  const json = JSON.parse(raw) as { layers: CaseLayerRow[] };
  const rows: Record<string, CaseLayerRow> = {};
  for (const r of json.layers) rows[r.id] = r;
  return { siteId: "lake_mead", bbox: [-115.2, 35.7, -113.8, 36.8], rows };
}

const POINT: PlaceEvent = { ...PLACE, id: "point", name: "Point", site_id: null, bbox: [59.4, 44.9, 59.6, 45.1] };

let n = 0;
const map = (op: MapOp): DetEvent => ({ kind: "map", data: op });
const layer = (layer_id: string, extra: { year?: number | null; date?: string | null } = {}): DetEvent =>
  map({ op: "show_layer", layer_id, date: extra.date ?? null, year: extra.year ?? null, opacity: 0.8 });
/** A tool scene: thinking + start + done, so later map ops land on it. */
function tool(name: string, result: Record<string, unknown>, evidence: string | null = null): DetEvent[] {
  n += 1;
  const id = `t${n}`;
  return [
    { kind: "thinking", data: { text: `step ${n}` } },
    { kind: "tool_start", data: { id, tool: name, args: {} } },
    { kind: "tool_done", data: { id, tool: name, summary: "Done.", result, evidence_id: evidence } },
  ];
}
const run = (place: PlaceEvent, body: DetEvent[], extra: DetEvent[] = []): DetEvent[] => [
  { kind: "place", data: place },
  ...body,
  { kind: "answer", data: { text: "A clue, not proof.", checked: true, figures: [], source: "llm", not_measured: [] } },
  ...extra,
  { kind: "done", data: { thread_id: "th1", n_tests: 1, n_tool_calls: 3, n_tests_branch: null } },
];
const stack = (events: DetEvent[], ctx: MapContext = NO_CASE, max = STACK_MAX) => {
  const inv = groupScenes(events, { ended: true });
  return stackFor(inv, mapViewAt(inv, inv.scenes.length - 1, ctx), { max, ctx });
};

test("the recorded Lake Mead run: the GRACE footprint becomes one coarse cell slab", () => {
  const m = stack([...RUN_EVENTS]);
  assert.equal(m.slabs.length, 1);
  const s = m.slabs[0];
  assert.equal(s.texture.kind, "cell");
  assert.equal(s.texture.kind === "cell" && s.texture.cellKm, 300);
  assert.deepEqual(s.texture.kind === "cell" && s.texture.bbox, [-116, 34, -113, 37]);
  assert.equal(s.resolution, "~300 km");
  assert.equal(s.source, "GRACE data cell (~300 km)");
  assert.equal(s.show.kind, "footprint");
  assert.equal(s.verdict, undefined);
});

test("cellKm reads the footprint size and never invents one", () => {
  assert.equal(cellKmOf("~300 km"), 300);
  assert.equal(cellKmOf("~50 km"), 50);
  assert.equal(cellKmOf("0.25 km"), 0.25);
  assert.equal(cellKmOf("one region"), null);
});

test("an empty investigation has no slabs", () => {
  const inv = groupScenes([]);
  const m = stackFor(inv, EMPTY_VIEW, { max: 5, ctx: NO_CASE });
  assert.deepEqual(m.slabs, []);
  assert.equal(m.bbox, null);
  // A place but no layer shown: still nothing to explode (the opening land cover is not evidence).
  assert.deepEqual(stack(run(POINT, tool("profile_place", {}))).slabs, []);
});

test("at most five slabs; the ones with a verdict first, then the most recent", () => {
  const events = run(POINT, [
    ...tool("get_series", { var_id: "ndvi", label: "Green vegetation", years: [2003, 2024] }, "e1"),
    layer("ndvi", { year: 2010 }),
    ...tool("trend_test", { test_id: "k1", var_id: "ndvi", label: "Green vegetation", verdict: "real", direction: "up", years: [2003, 2024] }, "e2"),
    layer("lst_day", { year: 2012 }),
    layer("snow_cover", { year: 2013 }),
    layer("precipitation", { year: 2014 }),
    layer("night_lights", { year: 2015 }),
    layer("sst", { year: 2016 }),
    layer("chlorophyll", { year: 2017 }),
  ], [{ kind: "board", data: { suspects: [], n_tests: 1, verdicts: { k1: { verdict: "real", direction: "up" } } } }]);
  const m = stack(events);
  assert.equal(m.slabs.length, 5);
  assert.deepEqual(m.slabs.map((s) => s.show.kind === "layer" && s.show.layer.layerId), [
    "ndvi", "chlorophyll", "sst", "night_lights", "precipitation",
  ]);
  assert.deepEqual(m.slabs[0].verdict, { verdict: "real", direction: "up", label: "Green vegetation" });
  assert.equal(m.slabs[1].verdict, undefined);
  // Evenly spaced heights, highest first.
  assert.deepEqual(m.slabs.map((s) => s.height), [5, 4, 3, 2, 1]);
  // Deterministic.
  assert.deepEqual(stack(events), m);
  assert.equal(stack(events, NO_CASE, 2).slabs.length, 2);
});

test("slabs carry the drawn year, not the asked year", () => {
  const lc = catalogLayer("land_cover");
  assert.ok(lc);
  const drawn = Number(dateFor(lc, { year: 2099 }).slice(0, 4));
  const m = stack(run(POINT, [...tool("land_cover_change", {}), layer("land_cover", { year: 2099 })]));
  assert.equal(m.slabs[0].year, drawn);
  assert.notEqual(m.slabs[0].year, 2099);

  const ctx: MapContext = { caseLayers: lakeMeadCase(), now: NOW };
  const mead = { ...PLACE, site_id: "lake_mead" };
  const c = stack(run(mead, [...tool("get_series", {}), layer("lst_gibs", { year: 1990 })]), ctx);
  assert.equal(c.slabs[0].year, 2003);
  assert.equal(c.slabs[0].texture.kind, "png");
  assert.equal(c.slabs[0].texture.kind === "png" && c.slabs[0].texture.url, "/sites/lake_mead/layers/lst_gibs/2003.png");
  assert.equal(c.slabs[0].resolution, "5600 m");
  assert.deepEqual(c.slabs[0].legend?.stops?.length, 9);
});

test("catalog layers become one WMS GetMap for the exact box and the drawn date", () => {
  const m = stack(run(POINT, [...tool("satellite_picture", {}), layer("true_colour", { year: 2024 })]));
  const t = m.slabs[0].texture;
  assert.equal(t.kind, "wms");
  const url = new URL(t.kind === "wms" ? t.url : "");
  assert.equal(url.searchParams.get("REQUEST"), "GetMap");
  assert.equal(url.searchParams.get("CRS"), "EPSG:4326");
  assert.equal(url.searchParams.get("BBOX"), "44.9,59.4,45.1,59.6");
  assert.equal(url.searchParams.get("TIME"), m.slabs[0].date);
  assert.equal(m.slabs[0].year, 2024);
  assert.deepEqual(m.bbox, POINT.bbox);
  // A free point has no relief model: a flat base with the true-colour picture.
  assert.equal(m.base?.kind, "flat");
  assert.equal(m.base?.heightmap, null);
  assert.ok(m.base?.picture?.url.includes("MODIS_Terra_CorrectedReflectance_TrueColor"));
});

test("a curtain gives both drawn years; a layer shown twice is one slab", () => {
  const m = stack(run(POINT, [
    ...tool("trend_test", {}),
    map({ op: "show_before_after", layer_id: "true_colour", year_a: 2003, year_b: 2024, before_url: null, after_url: null, bbox: null }),
    ...tool("climate_residual", {}),
    layer("true_colour", { year: 2024 }),
  ]));
  assert.deepEqual(m.slabs.map((s) => s.year), [2024, 2003]);
});

test("a data cell takes the verdict and stamp of the variables it measures", () => {
  const board: BoardEvent = {
    suspects: [{ id: "climate", label: "Less rain / warmer air", status: "hint", evidence: ["e8"], note: "", downgraded: null }],
    n_tests: 2,
    verdicts: { t2: { verdict: "real", direction: "down" } },
  };
  const m = stack(run(POINT, [
    ...tool("list_variables", { variables: [{ id: "grace_tws", source: "grace" }, { id: "t2m", source: "power" }] }),
    ...tool("get_series", { var_id: "grace_tws", label: "Total water stored", years: [2003, 2024] }, "e3"),
    map({ op: "show_footprint", source: "grace", label: "GRACE cell (~300 km)", size: "~300 km", bbox: [57.6, 43.7, 61.4, 46.3], approximate: true }),
    map({ op: "show_footprint", source: "power", label: "POWER cell (~50 km)", size: "~50 km", bbox: [59.2, 44.8, 59.8, 45.2], approximate: true }),
    ...tool("climate_residual", { var_id: "grace_tws", label: "Total water stored", test_id: "t2", verdict: "real", direction: "down" }, "e8"),
    { kind: "board", data: board },
  ]));
  assert.equal(m.slabs.length, 2);
  const grace = m.slabs[0];
  assert.equal(grace.key, "cell:grace");
  assert.equal(grace.title, "Total water stored");
  assert.deepEqual(grace.verdict, { verdict: "real", direction: "down", label: "Total water stored" });
  assert.deepEqual(grace.period, [2003, 2024]);
  assert.equal(grace.stamp?.status, "hint");
  assert.equal(grace.stamp?.label, "Less rain / warmer air");
  const power = m.slabs[1];
  assert.equal(power.texture.kind === "cell" && power.texture.cellKm, 50);
  assert.equal(power.verdict, undefined);
  assert.equal(power.stamp, undefined);
});

test("the stack shows the current turn only", () => {
  const first = run(POINT, [...tool("get_series", {}), layer("ndvi", { year: 2010 })]);
  const second = run({ ...POINT, follow_up: true }, [...tool("get_series", {}), layer("lst_day", { year: 2012 })]);
  const m = stack([...first, ...second]);
  assert.deepEqual(m.slabs.map((s) => s.show.kind === "layer" && s.show.layer.layerId), ["lst_day"]);
});

test("a solved case stands on its relief and its own picture", () => {
  const ctx: MapContext = { caseLayers: lakeMeadCase(), now: NOW };
  const mead = { ...PLACE, site_id: "lake_mead" };
  const m = stack(run(mead, [...tool("get_series", {}), layer("trend_lst_day")]), ctx);
  assert.equal(m.base?.kind, "relief");
  assert.equal(m.base?.heightmap?.url, "/sites/lake_mead/heightmap_rgb.png");
  assert.deepEqual(m.base?.heightmap?.rangeM, [165, 2373]);
  assert.equal(m.base?.source, "NASADEM elevation (NASA JPL / LP DAAC)");
  assert.equal(m.base?.picture?.url, "/sites/lake_mead/base_hq.jpg");
  assert.equal(m.base?.picture?.title, "Cloud-free satellite picture (30 m)");
  assert.deepEqual(m.bbox, [-115.2, 35.7, -113.8, 36.8]);
  assert.deepEqual(m.slabs[0].period, [2003, 2024]);
});

test("picking a slab shows that one layer on the map", async () => {
  const { showSlab, slabCaption } = await import("../stack/showSlab.ts");
  const events = run(POINT, [
    ...tool("get_series", { var_id: "grace_tws", label: "Total water stored", years: [2003, 2024] }),
    map({ op: "show_footprint", source: "grace", label: "GRACE cell (~300 km)", size: "~300 km", bbox: [57.6, 43.7, 61.4, 46.3], approximate: true }),
    ...tool("trend_test", {}),
    map({ op: "show_before_after", layer_id: "true_colour", year_a: 2003, year_b: 2024, before_url: null, after_url: null, bbox: null }),
    layer("ndvi", { year: 2012 }),
  ]);
  const inv = groupScenes(events, { ended: true });
  const end = mapViewAt(inv, inv.scenes.length - 1, NO_CASE);
  const m = stackFor(inv, end, { max: 5, ctx: NO_CASE });
  const byYear = (y: number) => m.slabs.find((s) => s.year === y && s.title.startsWith("True colour"));
  const before = byYear(2003);
  assert.ok(before);
  const v = showSlab(end, before);
  assert.equal(v.curtain, null);
  assert.equal(v.evidence, null);
  assert.equal(v.context?.year, 2003);
  assert.deepEqual(v.footprints, []);
  assert.equal(slabCaption(before), "True colour (MODIS Terra), 2003");
  const cell = m.slabs.find((s) => s.key === "cell:grace");
  assert.ok(cell);
  const c = showSlab(end, cell);
  assert.deepEqual(c.footprints.map((f) => f.source), ["grace"]);
  assert.equal(c.evidence, null);
  assert.equal(slabCaption(cell), "Total water stored, 2003–2024");
  const ndvi = m.slabs.find((s) => s.show.kind === "layer" && s.show.layer.layerId === "ndvi");
  assert.ok(ndvi);
  assert.equal(showSlab(end, ndvi).evidence?.layerId, "ndvi");
});
