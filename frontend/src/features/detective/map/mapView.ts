// The map is a function of the scene (spec §5.5d): context, one evidence layer, a comparison curtain and
// data-cell footprints, folded from the agent's map ops. Pure: every call returns a fresh view.
import type { Bbox, MapOp, PlaceEvent } from "../events.ts";
import type { Investigation } from "../scenes.ts";
import type { CaseLayerRow, CatalogLayer } from "./types.ts";
import { catalogLayer, dateFor, maxZoomOf, tileUrl } from "./catalog.ts";

export type LayerRender = { type: "tiles"; url: string; maxzoom: number } | { type: "image"; url: string; bbox: Bbox };
export type LayerRole = "context" | "evidence";
export interface LayerView {
  key: string; layerId: string; title: string; source: string; resolution: string | null;
  legend: CatalogLayer["legend"] | null; render: LayerRender; opacity: number; role: LayerRole;
  year: number | null; date: string | null;
}
export interface CurtainView { layerId: string; title: string; source: string; left: LayerView; right: LayerView; yearA: number; yearB: number }
export interface FootprintView { source: string; label: string; size: string; bbox: Bbox; approximate: true }
export interface CameraView { bbox: Bbox; pitch: number; bearing: number; seq: number }
export interface MapView {
  place: { lat: number; lon: number; bbox: Bbox } | null; context: LayerView | null; evidence: LayerView | null;
  curtain: CurtainView | null; footprints: FootprintView[]; camera: CameraView | null; notes: string[];
}
export interface CaseLayers { siteId: string; bbox: Bbox; rows: Record<string, CaseLayerRow> }
export interface MapContext { caseLayers: CaseLayers | null }

export const CONTEXT_LAYER_IDS: ReadonlySet<string> = new Set([
  "true_colour", "true_colour_viirs", "land_cover", "base", "base_hq", "hillshade",
]);

export const UNKNOWN_LAYER_NOTE = "A layer the map does not know was skipped.";
const OPENING_LAYER = "land_cover";
const OPENING_PITCH = 50;
const DEFAULT_OPACITY = 0.8;
const MAX_PITCH = 85;
const PULL_OUT = 4;

export const EMPTY_VIEW: MapView = Object.freeze({
  place: null, context: null, evidence: null, curtain: null, footprints: [], camera: null, notes: [],
}) as MapView;

const roleOf = (id: string): LayerRole => (CONTEXT_LAYER_IDS.has(id) ? "context" : "evidence");
const clamp = (x: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, x));

function withNote(view: MapView, note: string): MapView {
  return view.notes.includes(note) ? view : { ...view, notes: [...view.notes, note] };
}

// ---- catalog (GIBS tiles) ----

interface When { date?: string | null; year?: number | null }

function catalogView(layer: CatalogLayer, when: When, opacity: number, role: LayerRole): LayerView {
  const date = dateFor(layer, when);
  const year = Number(date.slice(0, 4));
  return {
    key: `${layer.id}@${date}`, layerId: layer.id, title: layer.title, source: layer.source,
    resolution: layer.resolution, legend: layer.legend,
    render: { type: "tiles", url: tileUrl(layer, date), maxzoom: maxZoomOf(layer) },
    opacity, role, year: Number.isFinite(year) ? year : null, date,
  };
}

// ---- case rows (/sites/<id>/ files) ----

function rowSource(row: CaseLayerRow): string {
  if (typeof row.source === "string") return row.source;
  return row.source?.name ?? "";
}

/** Case legends carry `range: [min, max]`; mapped to the catalog shape, values copied as they are. */
function rowLegend(row: CaseLayerRow): CatalogLayer["legend"] | null {
  const lg = (row as { legend?: { unit?: unknown; range?: unknown } }).legend;
  if (!lg || typeof lg.unit !== "string") return null;
  const r = Array.isArray(lg.range) && lg.range.length === 2 ? lg.range : null;
  const n = (x: unknown): number | null => (typeof x === "number" ? x : null);
  return { unit: lg.unit, min: r ? n(r[0]) : null, max: r ? n(r[1]) : null };
}

/** The year to draw from a yearly row: the asked year when the row has it, else the nearest it has, else its last. */
function rowYear(row: CaseLayerRow, year: number | null | undefined): number | null {
  const years = row.years ?? [];
  if (years.length === 0) return year ?? null;
  if (year == null) return years[years.length - 1];
  return years.reduce((best, y) => (Math.abs(y - year) < Math.abs(best - year) ? y : best), years[0]);
}

function caseFile(cl: CaseLayers, file: string): string {
  return `/sites/${cl.siteId}/${file}`;
}

function caseView(cl: CaseLayers, row: CaseLayerRow, when: When, opacity: number, role: LayerRole): LayerView | null {
  let file: string;
  let year: number | null = null;
  if (row.file_pattern) {
    year = rowYear(row, when.year);
    if (year == null) return null;
    file = row.file_pattern.replaceAll("{YYYY}", String(year));
  } else if (row.file) {
    file = row.file;
  } else return null;
  return {
    key: `${cl.siteId}/${row.id}@${year ?? "file"}`, layerId: row.id, title: row.title ?? row.id,
    source: rowSource(row), resolution: row.pixel_m != null ? `${row.pixel_m} m` : null, legend: rowLegend(row),
    render: { type: "image", url: caseFile(cl, file), bbox: cl.bbox }, opacity, role, year, date: null,
  };
}

function resolveLayer(id: string, when: When, opacity: number, ctx: MapContext): LayerView | null {
  const role = roleOf(id);
  const layer = catalogLayer(id);
  if (layer) return catalogView(layer, when, opacity, role);
  const cl = ctx.caseLayers;
  const row = cl?.rows[id];
  if (cl && row) return caseView(cl, row, when, opacity, role);
  return null;
}

// ---- ops ----

function showLayer(view: MapView, op: Extract<MapOp, { op: "show_layer" }>, ctx: MapContext): MapView {
  const lv = resolveLayer(op.layer_id, { date: op.date, year: op.year }, op.opacity, ctx);
  if (!lv) return withNote(view, UNKNOWN_LAYER_NOTE);
  return { ...view, [lv.role]: lv, curtain: null };
}

function setYear(view: MapView, year: number, ctx: MapContext): MapView {
  const slot: LayerRole | null = view.evidence ? "evidence" : view.context ? "context" : null;
  if (!slot) return view;
  const cur = view[slot] as LayerView;
  const lv = resolveLayer(cur.layerId, { year }, cur.opacity, ctx);
  if (!lv) return view;
  return { ...view, [slot]: { ...lv, role: slot } };
}

function imagePair(
  layerId: string, title: string, source: string, urls: [string, string], bbox: Bbox, years: [number, number],
): CurtainView {
  const role = roleOf(layerId);
  const side = (url: string, year: number, s: string): LayerView => ({
    key: `${layerId}@${s}:${url}`, layerId, title, source, resolution: null, legend: null,
    render: { type: "image", url, bbox }, opacity: 1, role, year, date: null,
  });
  return {
    layerId, title, source, left: side(urls[0], years[0], "a"), right: side(urls[1], years[1], "b"),
    yearA: years[0], yearB: years[1],
  };
}

function showBeforeAfter(view: MapView, op: Extract<MapOp, { op: "show_before_after" }>, ctx: MapContext): MapView {
  const layer = catalogLayer(op.layer_id);
  const cl = ctx.caseLayers;
  const row = cl?.rows[op.layer_id];
  const title = layer?.title ?? row?.title ?? op.layer_id;
  const source = layer?.source ?? (row ? rowSource(row) : "");

  if (op.before_url && op.after_url) {
    const bbox = op.bbox ?? view.place?.bbox;
    if (!bbox) return withNote(view, UNKNOWN_LAYER_NOTE);
    const curtain = imagePair(op.layer_id, title, source, [op.before_url, op.after_url], bbox, [op.year_a, op.year_b]);
    return { ...view, curtain };
  }
  if (cl && row && row.kind === "before_after" && row.before && row.after) {
    const curtain = imagePair(
      op.layer_id, title, source, [caseFile(cl, row.before.file), caseFile(cl, row.after.file)], cl.bbox,
      [row.before.year, row.after.year],
    );
    return { ...view, curtain };
  }
  if (layer) {
    const role = roleOf(layer.id);
    const left = catalogView(layer, { year: op.year_a }, 1, role);
    const right = catalogView(layer, { year: op.year_b }, 1, role);
    return {
      ...view,
      curtain: { layerId: layer.id, title, source, left, right, yearA: op.year_a, yearB: op.year_b },
    };
  }
  return withNote(view, UNKNOWN_LAYER_NOTE);
}

function camera(view: MapView, bbox: Bbox, pitch: number, bearing: number): CameraView {
  return { bbox: [...bbox] as Bbox, pitch: clamp(pitch, 0, MAX_PITCH), bearing, seq: (view.camera?.seq ?? 0) + 1 };
}

export function applyMapOp(view: MapView, op: MapOp, ctx: MapContext): MapView {
  switch (op.op) {
    case "show_layer":
      return showLayer(view, op, ctx);
    case "set_year":
      return setYear(view, op.year, ctx);
    case "show_before_after":
      return showBeforeAfter(view, op, ctx);
    case "fly_to":
      return { ...view, camera: camera(view, op.bbox, op.pitch, op.bearing) };
    case "show_footprint": {
      const fp: FootprintView = { source: op.source, label: op.label, size: op.size, bbox: [...op.bbox] as Bbox, approximate: true };
      return { ...view, footprints: [...view.footprints.filter((f) => f.source !== op.source), fp] };
    }
  }
}

export function openingView(place: PlaceEvent): MapView {
  const layer = catalogLayer(OPENING_LAYER);
  const bbox = [...place.bbox] as Bbox;
  return {
    place: { lat: place.lat, lon: place.lon, bbox },
    context: layer ? catalogView(layer, {}, DEFAULT_OPACITY, "context") : null,
    evidence: null, curtain: null, footprints: [], notes: [],
    camera: { bbox: [...bbox] as Bbox, pitch: OPENING_PITCH, bearing: 0, seq: 1 },
  };
}

/** The place bbox grown `PULL_OUT`× around its centre, clamped to valid degrees. */
function pulledOut(bbox: Bbox): Bbox {
  const [w, s, e, n] = bbox;
  const cx = (w + e) / 2;
  const cy = (s + n) / 2;
  const hw = ((e - w) * PULL_OUT) / 2;
  const hh = ((n - s) * PULL_OUT) / 2;
  return [clamp(cx - hw, -180, 180), clamp(cy - hh, -90, 90), clamp(cx + hw, -180, 180), clamp(cy + hh, -90, 90)];
}

export function mapViewAt(inv: Investigation, index: number, ctx: MapContext): MapView {
  if (!inv.place) return EMPTY_VIEW;
  const upto = Number.isFinite(index) ? Math.min(Math.floor(index), inv.scenes.length - 1) : -1;
  let view = openingView(inv.place);
  for (let i = 0; i <= upto; i++) {
    for (const op of inv.scenes[i].mapOps) view = applyMapOp(view, op, ctx);
  }
  if (upto >= 0 && inv.scenes[upto].kind === "ending") {
    view = { ...view, camera: { ...camera(view, pulledOut(inv.place.bbox), 0, 0) } };
  }
  return view;
}
