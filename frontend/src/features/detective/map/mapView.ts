// The map is a function of the scene (spec §5.5d): context, one evidence layer, a comparison curtain and
// data-cell footprints, folded from the agent's map ops. Pure: every call returns a fresh view.
import type { Bbox, MapOp, PlaceEvent } from "../events.ts";
import type { Investigation } from "../scenes.ts";
import type { CaseLayerRow, CatalogLayer } from "./types.ts";
import { catalogLayer, dateFor, maxZoomOf, tileUrl } from "./catalog.ts";
import { plainLegendLabels } from "../legendWords.ts";

export type LayerRender = { type: "tiles"; url: string; maxzoom: number } | { type: "image"; url: string; bbox: Bbox };
export type LayerRole = "context" | "evidence";
/** Catalog legend, widened with a case's `labels` and `stops` copied from layers.json (honesty cues such as
 * "Faded = not statistically significant" live in `labels`). Catalog legends never carry them. */
export type LayerLegend = CatalogLayer["legend"] & { labels?: string[]; stops?: string[] };
export interface LayerView {
  key: string; layerId: string; title: string; source: string; resolution: string | null;
  legend: LayerLegend | null; render: LayerRender; opacity: number; role: LayerRole;
  /** The year actually drawn (after snapping and clamping), never the year asked for. */
  year: number | null; date: string | null;
  /** The period a single-file case layer covers (e.g. a trend map), `[first, last]` from the row's `years`. */
  period: [number, number] | null;
  /** Drawn pixel for pixel (no smoothing): each pixel is one data cell, as in a tool's trend overlay. */
  crisp?: true;
}
/** The years drawn are `left.year` and `right.year`. */
export interface CurtainView { layerId: string; title: string; source: string; left: LayerView; right: LayerView }
export interface FootprintView { source: string; label: string; size: string; bbox: Bbox; approximate: true }
export interface CameraView { bbox: Bbox; pitch: number; bearing: number; seq: number }
export interface MapView {
  place: { lat: number; lon: number; bbox: Bbox } | null; context: LayerView | null; evidence: LayerView | null;
  curtain: CurtainView | null; footprints: FootprintView[]; camera: CameraView | null; notes: string[];
}
export interface CaseLayers { siteId: string; bbox: Bbox; rows: Record<string, CaseLayerRow> }

/**
 * The rows of a `sites/<id>/layers.json` file (`{site, version, layers: [...], timeline}`), keyed by row id. Rows
 * without a string id are skipped; anything that is not that shape gives no rows.
 */
export function caseRowsFrom(json: unknown): Record<string, CaseLayerRow> {
  const layers = json && typeof json === "object" ? (json as { layers?: unknown }).layers : undefined;
  const out: Record<string, CaseLayerRow> = {};
  if (!Array.isArray(layers)) return out;
  for (const r of layers) {
    if (r && typeof r === "object" && typeof (r as { id?: unknown }).id === "string") {
      const row = r as CaseLayerRow;
      out[row.id] = row;
    }
  }
  return out;
}
export interface MapContext {
  caseLayers: CaseLayers | null;
  /** Today as YYYY-MM-DD, for the safe default date of ongoing layers. Omitted: each layer's end date stands in. */
  now?: string | null;
  /** The backend's base URL, for overlay pictures the backend serves under a path (`/detective/maps/…`). */
  apiBase?: string | null;
}

export const CONTEXT_LAYER_IDS: ReadonlySet<string> = new Set([
  "true_colour", "true_colour_viirs", "land_cover", "base", "base_hq", "hillshade",
]);

export const UNKNOWN_LAYER_NOTE = "A layer the map does not know was skipped.";
export const NO_PLACE_NOTE = "A comparison with no place to draw it was skipped.";
export const CURTAIN_YEAR_NOTE = "This comparison shows two fixed pictures, so the year did not change.";
export const BAD_OVERLAY_NOTE = "A map picture with no usable address was skipped.";
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

function catalogView(layer: CatalogLayer, when: When, opacity: number, role: LayerRole, now?: string | null): LayerView {
  const date = dateFor(layer, when, now);
  const year = Number(date.slice(0, 4));
  return {
    key: `${layer.id}@${date}`, layerId: layer.id, title: layer.title, source: layer.source,
    resolution: layer.resolution, legend: layer.legend,
    render: { type: "tiles", url: tileUrl(layer, date), maxzoom: maxZoomOf(layer) },
    opacity, role, year: Number.isFinite(year) ? year : null, date, period: null,
  };
}

// ---- case rows (/sites/<id>/ files) ----

function rowSource(row: CaseLayerRow): string {
  if (typeof row.source === "string") return row.source;
  return row.source?.name ?? "";
}

const strings = (xs: unknown[]): string[] => xs.filter((x): x is string => typeof x === "string");

/** Case legends carry `range: [min, max]`, `labels` and `stops`; mapped to the catalog shape, values copied as they
 * are. `labels` is an object in layers.json ({more, less, faded, transparent}); its values keep the file's order. */
function rowLegend(row: CaseLayerRow): LayerLegend | null {
  const lg = row.legend;
  if (!lg || typeof lg.unit !== "string") return null;
  const r = Array.isArray(lg.range) && lg.range.length === 2 ? lg.range : null;
  const n = (x: unknown): number | null => (typeof x === "number" ? x : null);
  const out: LayerLegend = { unit: lg.unit, min: r ? n(r[0]) : null, max: r ? n(r[1]) : null };
  const labels = plainLegendLabels(Array.isArray(lg.labels) ? strings(lg.labels)
    : lg.labels && typeof lg.labels === "object" ? strings(Object.values(lg.labels)) : []);
  const stops = Array.isArray(lg.stops) ? strings(lg.stops) : [];
  return {
    ...out,
    ...(labels.length > 0 ? { labels } : {}),
    ...(stops.length > 0 ? { stops } : {}),
  };
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
  let period: [number, number] | null = null;
  if (row.file_pattern) {
    year = rowYear(row, when.year);
    if (year == null) return null;
    file = row.file_pattern.replaceAll("{YYYY}", String(year));
  } else if (row.file) {
    file = row.file;
    const ys = row.years ?? [];
    if (ys.length >= 2) period = [ys[0], ys[ys.length - 1]];
  } else return null;
  return {
    key: `${cl.siteId}/${row.id}@${year ?? "file"}`, layerId: row.id, title: row.title ?? row.id,
    source: rowSource(row), resolution: row.pixel_m != null ? `${row.pixel_m} m` : null, legend: rowLegend(row),
    render: { type: "image", url: caseFile(cl, file), bbox: cl.bbox }, opacity, role, year, date: null, period,
  };
}

function resolveLayer(id: string, when: When, opacity: number, ctx: MapContext): LayerView | null {
  const role = roleOf(id);
  const layer = catalogLayer(id);
  if (layer) return catalogView(layer, when, opacity, role, ctx.now);
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

/** A curtain side that can be redrawn for another year: catalog tiles or a yearly case row. */
function sideForYear(side: LayerView, year: number, ctx: MapContext): LayerView | null {
  if (side.render.type === "tiles") {
    const layer = catalogLayer(side.layerId);
    return layer ? catalogView(layer, { year }, side.opacity, side.role, ctx.now) : null;
  }
  const cl = ctx.caseLayers;
  const row = cl?.rows[side.layerId];
  if (!cl || !row || !row.file_pattern) return null;
  return caseView(cl, row, { year }, side.opacity, side.role);
}

function setYear(view: MapView, year: number, ctx: MapContext): MapView {
  if (view.curtain) {
    // The "before" side is the anchor; set_year moves the "after" side.
    const right = sideForYear(view.curtain.right, year, ctx);
    if (!right) return withNote(view, CURTAIN_YEAR_NOTE);
    return { ...view, curtain: { ...view.curtain, right } };
  }
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
    render: { type: "image", url, bbox }, opacity: 1, role, year, date: null, period: null,
  });
  return { layerId, title, source, left: side(urls[0], years[0], "a"), right: side(urls[1], years[1], "b") };
}

/** A curtain replaces the colored evidence layer: one colored layer at a time (DESIGN.md). */
const withCurtain = (view: MapView, curtain: CurtainView): MapView => ({ ...view, curtain, evidence: null });

function showBeforeAfter(view: MapView, op: Extract<MapOp, { op: "show_before_after" }>, ctx: MapContext): MapView {
  const layer = catalogLayer(op.layer_id);
  const cl = ctx.caseLayers;
  const row = cl?.rows[op.layer_id];
  const title = layer?.title ?? row?.title ?? op.layer_id;
  const source = layer?.source ?? (row ? rowSource(row) : "");

  if (op.before_url && op.after_url) {
    const bbox = op.bbox ?? view.place?.bbox;
    if (!bbox) return withNote(view, NO_PLACE_NOTE);
    return withCurtain(view, imagePair(op.layer_id, title, source, [op.before_url, op.after_url], bbox, [op.year_a, op.year_b]));
  }
  if (cl && row && row.kind === "before_after" && row.before && row.after) {
    return withCurtain(view, imagePair(
      op.layer_id, title, source, [caseFile(cl, row.before.file), caseFile(cl, row.after.file)], cl.bbox,
      [row.before.year, row.after.year],
    ));
  }
  if (layer) {
    const role = roleOf(layer.id);
    const left = catalogView(layer, { year: op.year_a }, 1, role, ctx.now);
    const right = catalogView(layer, { year: op.year_b }, 1, role, ctx.now);
    return withCurtain(view, { layerId: layer.id, title, source, left, right });
  }
  if (cl && row && row.file_pattern) {
    const role = roleOf(row.id);
    const left = caseView(cl, row, { year: op.year_a }, 1, role);
    const right = caseView(cl, row, { year: op.year_b }, 1, role);
    if (left && right) return withCurtain(view, { layerId: row.id, title, source, left, right });
  }
  return withNote(view, UNKNOWN_LAYER_NOTE);
}

/** A backend path is read from the backend; a full http(s) URL is kept; anything else is refused. */
export function overlayUrl(url: string, apiBase: string | null | undefined): string | null {
  if (/^https?:\/\//i.test(url)) return url;
  if (url.startsWith("/") && !url.startsWith("//")) return apiBase ? `${apiBase.replace(/\/$/, "")}${url}` : url;
  return null;
}

/** A tool's own per-pixel picture: the evidence layer, with the legend, source and period the tool sent. */
function overlay(view: MapView, op: Extract<MapOp, { op: "overlay" }>, ctx: MapContext): MapView {
  const url = overlayUrl(op.url, ctx.apiBase);
  if (!url) return withNote(view, BAD_OVERLAY_NOTE);
  const lg = op.legend;
  const legend: LayerLegend | null = lg
    ? {
        unit: lg.unit, min: lg.range ? lg.range[0] : null, max: lg.range ? lg.range[1] : null,
        ...(lg.labels.length > 0 ? { labels: [...lg.labels] } : {}),
        ...(lg.stops.length > 0 ? { stops: [...lg.stops] } : {}),
      }
    : null;
  const lv: LayerView = {
    key: `overlay@${url}`, layerId: `overlay:${op.url}`, title: op.title, source: op.source, resolution: op.resolution,
    legend, render: { type: "image", url, bbox: [...op.bounds] as Bbox }, opacity: 1, role: "evidence",
    year: null, date: null, period: op.period ? [op.period[0], op.period[1]] : null, crisp: true,
  };
  return { ...view, evidence: lv, curtain: null };
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
    case "overlay":
      return overlay(view, op, ctx);
    case "show_footprint": {
      const fp: FootprintView = { source: op.source, label: op.label, size: op.size, bbox: [...op.bbox] as Bbox, approximate: true };
      return { ...view, footprints: [...view.footprints.filter((f) => f.source !== op.source), fp] };
    }
  }
}

export function openingView(place: PlaceEvent, now?: string | null): MapView {
  const layer = catalogLayer(OPENING_LAYER);
  const bbox = [...place.bbox] as Bbox;
  return {
    place: { lat: place.lat, lon: place.lon, bbox },
    context: layer ? catalogView(layer, {}, DEFAULT_OPACITY, "context", now) : null,
    evidence: null, curtain: null, footprints: [], notes: [],
    camera: { bbox: [...bbox] as Bbox, pitch: OPENING_PITCH, bearing: 0, seq: 1 },
  };
}

/** The place bbox grown `PULL_OUT`× around its center, clamped to valid degrees. */
export function pulledOut(bbox: Bbox): Bbox {
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
  let view = openingView(inv.place, ctx.now);
  for (let i = 0; i <= upto; i++) {
    for (const op of inv.scenes[i].mapOps) view = applyMapOp(view, op, ctx);
  }
  if (upto >= 0 && inv.scenes[upto].kind === "ending") {
    view = { ...view, camera: { ...camera(view, pulledOut(inv.place.bbox), 0, 0) } };
  }
  return view;
}
