import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { CONTEXT_LAYER_IDS, EMPTY_VIEW, applyMapOp, mapViewAt, openingView } from "../map/mapView.ts";
import type { CaseLayers, MapContext, MapView } from "../map/mapView.ts";
import type { CaseLayerRow } from "../map/types.ts";
import type { MapOp } from "../events.ts";
import type { Investigation, Scene, SceneKind } from "../scenes.ts";
import { PLACE } from "./fixtures.ts";

const NO_CASE: MapContext = { caseLayers: null };

function lakeMeadCase(): CaseLayers {
  const raw = readFileSync(join(import.meta.dirname, "../../../../../sites/lake_mead/layers.json"), "utf8");
  const json = JSON.parse(raw) as { layers: CaseLayerRow[] };
  const rows: Record<string, CaseLayerRow> = {};
  for (const r of json.layers) rows[r.id] = r;
  return { siteId: "lake_mead", bbox: [-115.2, 35.7, -113.8, 36.8], rows };
}
const CASE: MapContext = { caseLayers: lakeMeadCase() };

const layer = (layer_id: string, extra: Partial<{ year: number | null; date: string | null; opacity: number }> = {}): MapOp => ({
  op: "show_layer", layer_id, date: null, year: null, opacity: 0.8, ...extra,
});
const fold = (ops: MapOp[], ctx: MapContext = NO_CASE, start: MapView = openingView(PLACE)): MapView =>
  ops.reduce((v, op) => applyMapOp(v, op, ctx), start);

const mk = (kind: SceneKind, mapOps: MapOp[] = []): Scene => ({
  key: `${kind}-${Math.random()}`, kind, question: null, tool: null, mapOps, stamps: [], note: null, complete: true,
});
const inv = (scenes: Scene[]): Investigation => ({
  place: PLACE, scenes, board: null, answer: null, done: null, error: null, finished: true,
});

test("context ids", () => {
  for (const id of ["true_colour", "true_colour_viirs", "land_cover", "base", "base_hq", "hillshade"]) {
    assert.ok(CONTEXT_LAYER_IDS.has(id), id);
  }
  assert.ok(!CONTEXT_LAYER_IDS.has("ndvi"));
});

test("opening shows land cover and flies in", () => {
  const v = openingView(PLACE);
  assert.equal(v.context?.layerId, "land_cover");
  assert.equal(v.context?.role, "context");
  assert.equal(v.context?.date, "2024-01-01");
  assert.equal(v.context?.year, 2024);
  assert.equal(v.context?.render.type, "tiles");
  if (v.context?.render.type === "tiles") {
    assert.ok(v.context.render.url.includes("/2024-01-01/"));
    assert.equal(v.context.render.maxzoom, 8);
  }
  assert.equal(v.evidence, null);
  assert.equal(v.curtain, null);
  assert.deepEqual(v.camera, { bbox: PLACE.bbox, pitch: 50, bearing: 0, seq: 1 });
  assert.deepEqual(v.place, { lat: PLACE.lat, lon: PLACE.lon, bbox: PLACE.bbox });
  assert.deepEqual(v.footprints, []);
  assert.deepEqual(v.notes, []);
});

test("evidence replaces evidence, context stays", () => {
  const v = fold([layer("ndvi"), layer("lst_day", { year: 2010, opacity: 0.6 })]);
  assert.equal(v.evidence?.layerId, "lst_day");
  assert.equal(v.evidence?.role, "evidence");
  assert.equal(v.evidence?.opacity, 0.6);
  assert.equal(v.evidence?.year, 2010);
  assert.equal(v.evidence?.resolution, "~1 km");
  assert.equal(v.evidence?.legend?.unit, "K");
  assert.equal(v.context?.layerId, "land_cover");
});

test("context layer replaces context and keeps evidence", () => {
  const v = fold([layer("ndvi"), layer("true_colour", { date: "2024-06-20" })]);
  assert.equal(v.context?.layerId, "true_colour");
  assert.equal(v.context?.date, "2024-06-20");
  assert.equal(v.evidence?.layerId, "ndvi");
});

test("show_layer clears the curtain", () => {
  const v = fold([
    { op: "show_before_after", layer_id: "ndvi", year_a: 2003, year_b: 2023, before_url: null, after_url: null, bbox: null },
    layer("ndvi"),
  ]);
  assert.equal(v.curtain, null);
});

test("satellite pair becomes a curtain of two images", () => {
  const op: MapOp = {
    op: "show_before_after", layer_id: "true_colour", year_a: 2003, year_b: 2024,
    before_url: "https://x/before.jpg", after_url: "https://x/after.jpg", bbox: null,
  };
  const v = fold([op]);
  assert.ok(v.curtain);
  assert.equal(v.curtain.layerId, "true_colour");
  assert.equal(v.curtain.yearA, 2003);
  assert.equal(v.curtain.yearB, 2024);
  assert.deepEqual(v.curtain.left.render, { type: "image", url: "https://x/before.jpg", bbox: PLACE.bbox });
  assert.deepEqual(v.curtain.right.render, { type: "image", url: "https://x/after.jpg", bbox: PLACE.bbox });
  const withBox = fold([{ ...op, bbox: [-1, -1, 1, 1] }]);
  assert.deepEqual(withBox.curtain?.left.render, { type: "image", url: "https://x/before.jpg", bbox: [-1, -1, 1, 1] });
});

test("catalog pair without urls becomes tile curtain", () => {
  const v = fold([
    { op: "show_before_after", layer_id: "true_colour", year_a: 2003, year_b: 2023, before_url: null, after_url: null, bbox: null },
  ]);
  assert.ok(v.curtain);
  assert.equal(v.curtain.left.render.type, "tiles");
  assert.ok(v.curtain.left.render.url.includes("/2003-07-01/"));
  assert.ok(v.curtain.right.render.url.includes("/2023-07-01/"));
  assert.equal(v.curtain.left.year, 2003);
  assert.equal(v.curtain.right.year, 2023);
});

test("case before_after row gives its two pictures", () => {
  const v = fold([
    { op: "show_before_after", layer_id: "before_after", year_a: 2003, year_b: 2024, before_url: null, after_url: null, bbox: null },
  ], CASE);
  assert.ok(v.curtain);
  assert.equal(v.curtain.left.render.url, "/sites/lake_mead/before.jpg");
  assert.equal(v.curtain.right.render.url, "/sites/lake_mead/after.jpg");
  assert.equal(v.curtain.left.render.type, "image");
  if (v.curtain.left.render.type === "image") assert.deepEqual(v.curtain.left.render.bbox, CASE.caseLayers?.bbox);
});

test("case layers resolve to /sites files", () => {
  const trend = fold([layer("trend_lst_day")], CASE);
  assert.deepEqual(trend.evidence?.render, { type: "image", url: "/sites/lake_mead/trend_lst_day.png", bbox: CASE.caseLayers?.bbox });
  assert.equal(trend.evidence?.source, "MODIS Terra land surface temperature (MOD11A2 v061), via AppEEARS");
  assert.equal(trend.evidence?.legend?.unit, "°C per decade");

  const yearly = fold([layer("lst_gibs", { year: 2010 })], CASE);
  assert.equal(yearly.evidence?.render.url, "/sites/lake_mead/layers/lst_gibs/2010.png");
  assert.equal(yearly.evidence?.year, 2010);

  const lastYear = fold([layer("lst_gibs")], CASE);
  assert.equal(lastYear.evidence?.render.url, "/sites/lake_mead/layers/lst_gibs/2024.png");
  assert.equal(lastYear.evidence?.year, 2024);

  const base = fold([layer("base_hq")], CASE);
  assert.equal(base.context?.render.url, "/sites/lake_mead/base_hq.jpg");
  assert.equal(base.context?.role, "context");
});

test("set_year re-renders evidence, or context when there is none", () => {
  const ev = fold([layer("lst_gibs", { year: 2010 }), { op: "set_year", year: 2015 }], CASE);
  assert.equal(ev.evidence?.render.url, "/sites/lake_mead/layers/lst_gibs/2015.png");
  assert.equal(ev.context?.layerId, "land_cover");
  assert.equal(ev.context?.year, 2024);

  const tiles = fold([layer("ndvi"), { op: "set_year", year: 2005 }]);
  assert.ok(tiles.evidence?.render.url.includes("/2005-07-01/"));
  assert.equal(tiles.evidence?.year, 2005);

  const ctxOnly = fold([{ op: "set_year", year: 2010 }]);
  assert.equal(ctxOnly.context?.year, 2010);
  assert.ok(ctxOnly.context?.render.url.includes("/2010-01-01/"));
});

test("unknown layer is skipped with a note", () => {
  const before = fold([layer("ndvi")]);
  const v = fold([layer("nope"), layer("nope_again")], NO_CASE, before);
  assert.equal(v.evidence?.layerId, "ndvi");
  assert.deepEqual(v.notes, ["A layer the map does not know was skipped."]);
  const caseOnly = fold([layer("trend_lst_day")], NO_CASE);
  assert.equal(caseOnly.evidence, null);
  assert.equal(caseOnly.notes.length, 1);
});

test("fly_to bumps seq and clamps pitch", () => {
  const v = fold([
    { op: "fly_to", bbox: [-1, -1, 1, 1], pitch: 120, bearing: 30 },
    { op: "fly_to", bbox: [-2, -2, 2, 2], pitch: -5, bearing: 0 },
  ]);
  assert.deepEqual(v.camera, { bbox: [-2, -2, 2, 2], pitch: 0, bearing: 0, seq: 3 });
  const one = fold([{ op: "fly_to", bbox: [-1, -1, 1, 1], pitch: 120, bearing: 30 }]);
  assert.equal(one.camera?.pitch, 85);
});

test("footprint replaces same source", () => {
  const fp = (label: string, source = "grace"): MapOp => ({
    op: "show_footprint", source, label, size: "~300 km", bbox: [-116, 34, -113, 37], approximate: true,
  });
  const v = fold([fp("a"), fp("b", "power"), fp("c")]);
  assert.equal(v.footprints.length, 2);
  assert.deepEqual(v.footprints.map((f) => [f.source, f.label]), [["power", "b"], ["grace", "c"]]);
  assert.equal(v.footprints[1].approximate, true);
});

test("applyMapOp does not mutate its input", () => {
  const start = openingView(PLACE);
  const snapshot = structuredClone(start);
  fold([layer("ndvi"), layer("nope"), { op: "fly_to", bbox: [0, 0, 1, 1], pitch: 10, bearing: 0 }], NO_CASE, start);
  assert.deepEqual(start, snapshot);
  assert.deepEqual(EMPTY_VIEW.notes, []);
});

test("ending pulls out", () => {
  const v = mapViewAt(inv([mk("opening"), mk("evidence", [layer("ndvi")]), mk("ending")]), 2, NO_CASE);
  assert.ok(v.camera);
  assert.equal(v.camera.pitch, 0);
  const [w, s, e, n] = v.camera.bbox;
  const [pw, ps, pe, pn] = PLACE.bbox;
  assert.ok(Math.abs((e - w) - 4 * (pe - pw)) < 1e-9);
  assert.ok(Math.abs((n - s) - 4 * (pn - ps)) < 1e-9);
  assert.ok(Math.abs((w + e) / 2 - (pw + pe) / 2) < 1e-9);
  assert.equal(v.evidence?.layerId, "ndvi");
});

test("ending pull-out is clamped to valid degrees", () => {
  const wide = { ...PLACE, bbox: [-170, -80, 170, 80] as [number, number, number, number] };
  const v = mapViewAt({ ...inv([mk("opening"), mk("ending")]), place: wide }, 1, NO_CASE);
  const [w, s, e, n] = v.camera?.bbox ?? [0, 0, 0, 0];
  assert.ok(w >= -180 && e <= 180 && s >= -90 && n <= 90);
});

test("scrubbing back shows that scene's map", () => {
  const i = inv([mk("opening"), mk("context"), mk("evidence"), mk("evidence", [layer("ndvi")])]);
  assert.equal(mapViewAt(i, 3, NO_CASE).evidence?.layerId, "ndvi");
  const back = mapViewAt(i, 1, NO_CASE);
  assert.equal(back.evidence, null);
  assert.deepEqual(back, openingView(PLACE));
});

test("no place yet gives the empty view", () => {
  assert.deepEqual(mapViewAt({ ...inv([]), place: null }, 0, NO_CASE), EMPTY_VIEW);
});
