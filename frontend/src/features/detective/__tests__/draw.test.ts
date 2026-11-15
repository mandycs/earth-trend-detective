import { test } from "node:test";
import assert from "node:assert/strict";
import {
  TERRAIN_LINE, curtainAriaLabel, drawSpecs, drawnWhen, fitPadding, footprintData, imageCoordinates, initialSplit,
  contextDrawn, legendModel, mapLabel, overlaySpecs, pickStep, specLayerIds, specSignature,
} from "../map/draw.ts";
import { applyMapOp, openingView } from "../map/mapView.ts";
import type { MapView } from "../map/mapView.ts";
import type { MapOp } from "../events.ts";
import { PLACE } from "./fixtures.ts";

const NOW = { caseLayers: null, now: "2026-11-15" };
const fold = (ops: MapOp[]): MapView => ops.reduce((v, op) => applyMapOp(v, op, NOW), openingView(PLACE, NOW.now));
const show = (layer_id: string, year: number | null = null): MapOp => ({ op: "show_layer", layer_id, date: null, year, opacity: 0.8 });
const compare: MapOp = { op: "show_before_after", layer_id: "ndvi", year_a: 2003, year_b: 2024, before_url: null, after_url: null, bbox: null };
const footprint: MapOp = { op: "show_footprint", source: "grace", label: "GRACE cell", size: "~300 km", bbox: [-116, 35, -113, 38], approximate: true };

test("one coloured layer at a time: land cover is drawn alone, and leaves when evidence arrives", () => {
  const opening = openingView(PLACE, NOW.now);
  assert.equal(opening.context?.layerId, "land_cover");
  assert.deepEqual(drawSpecs(opening, "main", null).map((s) => s.id), ["det-context"]);
  assert.ok(contextDrawn(opening));
  const withEvidence = fold([show("ndvi", 2020)]);
  assert.equal(contextDrawn(withEvidence), false);
  const specs = drawSpecs(withEvidence, "main", null);
  assert.deepEqual(specs.map((s) => s.id), ["det-evidence"]);
  const ev = specs[0];
  assert.equal(ev.kind, "raster");
  if (ev.kind === "raster") {
    assert.equal(ev.attribution, "NASA GIBS");
    assert.equal(ev.maxzoom, 7);
    assert.match(ev.tiles[0], /MODIS_Terra_NDVI_Monthly|NDVI/);
  }
});

test("a photograph context stays under the evidence", () => {
  const v = fold([show("true_colour"), show("ndvi", 2020)]);
  assert.ok(contextDrawn(v));
  assert.deepEqual(drawSpecs(v, "main", null).map((s) => s.id), ["det-context", "det-evidence"]);
  assert.deepEqual(legendModel(v)?.entries.map((e) => e.role), ["Evidence", "Context"]);
});

test("a curtain puts its left side on the main map and only its right side on the curtain map", () => {
  const v = fold([show("ndvi", 2020), compare]);
  const main = drawSpecs(v, "main", null);
  const side = drawSpecs(v, "curtain", null);
  assert.deepEqual(main.map((s) => s.id), ["det-evidence"]);
  assert.deepEqual(side.map((s) => s.id), ["det-evidence"]);
  assert.notEqual(specSignature(main[0]), specSignature(side[0]));
  assert.deepEqual(drawSpecs(fold([show("ndvi")]), "curtain", null), []);
});

test("footprints are labelled approximate and the picked box is an outline; a point is not a layer", () => {
  const v = fold([footprint]);
  const box = drawSpecs(v, "main", { kind: "box", bbox: [-115, 36, -114, 37] });
  assert.deepEqual(box.slice(1).map((s) => s.kind), ["footprint", "outline"]);
  const fp = box[1];
  if (fp.kind === "footprint") assert.equal(fp.text, "GRACE cell · approximate");
  assert.deepEqual(specLayerIds(fp), ["det-fp-grace-edge", "det-fp-grace-label"]);
  const point = drawSpecs(v, "main", { kind: "point", lat: 1, lon: 2 });
  assert.equal(point.filter((s) => s.kind === "outline" || s.kind === "point").length, 0);
});

test("the curtain map draws a picked point as a layer", () => {
  const specs = overlaySpecs(fold([]), { kind: "point", lat: 1, lon: 2 }, { point: true });
  assert.deepEqual(specs, [{ id: "det-target", kind: "point", lat: 1, lon: 2 }]);
  assert.deepEqual(specLayerIds(specs[0]), ["det-target-dot"]);
});

test("the map names what a tap does", () => {
  assert.equal(mapLabel(false, "box"), "Globe showing the investigation.");
  assert.equal(mapLabel(true, "box"), "Globe. Tap two corners to draw a box.");
  assert.equal(mapLabel(true, "point"), "Globe. Tap a place to investigate it.");
});

test("signature ignores opacity", () => {
  const a = drawSpecs(fold([show("ndvi", 2020)]), "main", null)[0];
  const b = { ...a, opacity: 0.2 };
  assert.equal(specSignature(a), specSignature(b));
});

test("geometry helpers", () => {
  assert.deepEqual(imageCoordinates([0, 1, 2, 3]), [[0, 3], [2, 3], [2, 1], [0, 1]]);
  const fc = footprintData([0, 1, 2, 3], "x · approximate");
  assert.equal(fc.features.length, 2);
  assert.deepEqual(fc.features[1].geometry.coordinates, [1, 3]);
});

test("padding keeps the reading column clear at ≥ 1100 px", () => {
  assert.equal(fitPadding(2000, 1000).left, 800);
  assert.equal(fitPadding(1099, 900).left, 48);
  const tiny = fitPadding(150, 150);
  assert.deepEqual(tiny, { top: 8, bottom: 8, left: 8, right: 8 });
  assert.equal(initialSplit(1400), 70);
  assert.equal(initialSplit(800), 50);
});

test("point picking answers at once with the longitude wrapped", () => {
  assert.deepEqual(pickStep(null, "point", { lat: 10, lon: 190 }), {
    pending: null, result: { target: { kind: "point", lat: 10, lon: -170 } },
  });
});

test("box picking takes two taps and reports a bad box as an error", () => {
  const first = pickStep(null, "box", { lat: 36, lon: -115 });
  assert.equal(first.result, null);
  assert.deepEqual(first.pending, { lat: 36, lon: -115 });
  const second = pickStep(first.pending, "box", { lat: 37, lon: -114 });
  assert.deepEqual(second, { pending: null, result: { target: { kind: "box", bbox: [-115, 36, -114, 37] } } });
  const bad = pickStep({ lat: 36, lon: -115 }, "box", { lat: 36.001, lon: -115.001 });
  assert.equal(bad.pending, null);
  assert.ok(bad.result && "error" in bad.result);
});

test("curtain label names the two years drawn", () => {
  const v = fold([compare]);
  assert.ok(v.curtain);
  if (v.curtain) assert.equal(curtainAriaLabel(v.curtain), `Slide between ${v.curtain.left.year} and ${v.curtain.right.year}`);
});

test("drawn time: annual layers say the year, daily ones the date", () => {
  const v = openingView(PLACE, NOW.now);
  assert.ok(v.context);
  if (v.context) assert.equal(drawnWhen(v.context), `Year drawn: ${v.context.year}`);
  const tc = fold([show("true_colour")]).context;
  assert.ok(tc);
  if (tc) assert.equal(drawnWhen(tc), `Date drawn: ${tc.date}`);
});

test("legend lists every drawn layer with source, resolution and range from the catalog", () => {
  const m = legendModel(fold([show("ndvi", 2020), footprint]));
  assert.ok(m);
  if (!m) return;
  assert.deepEqual(m.entries.map((e) => e.role), ["Evidence"]);
  const ev = m.entries[0];
  assert.equal(ev.range, "0–1");
  assert.equal(ev.unit, "NDVI (no unit)");
  assert.match(ev.resolution ?? "", / pixels, smoothed for display$/);
  assert.ok(ev.source.length > 0);
  assert.equal(m.footprints[0].text, "GRACE cell · approximate");
  assert.equal(m.terrain, "Relief: AWS Terrain Tiles (Mapzen), not a NASA product · Heights ×1.5");
  assert.equal(TERRAIN_LINE, m.terrain);
  assert.equal(m.curtain, null);
  assert.equal(legendModel(fold([show("ndvi", 2020)]), { flat: true })?.terrain, "Relief: AWS Terrain Tiles (Mapzen), not a NASA product");
  assert.deepEqual(legendModel(openingView(PLACE, NOW.now))?.entries.map((e) => e.role), ["Context"]);
});

test("legend shows the curtain's two years and no range when a bound is missing", () => {
  const m = legendModel(fold([compare]));
  assert.ok(m);
  if (!m) return;
  assert.match(m.curtain ?? "", /^Left: \d{4} · Right: \d{4}$/);
  assert.equal(m.entries[0].role, "Compared");
  const tc = legendModel(fold([show("true_colour")]));
  assert.equal(tc?.entries[0].range, null);
});

test("an empty view has no legend", () => {
  const empty: MapView = { place: null, context: null, evidence: null, curtain: null, footprints: [], camera: null, notes: [] };
  assert.equal(legendModel(empty), null);
});
