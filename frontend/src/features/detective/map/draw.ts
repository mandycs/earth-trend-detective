// Pure helpers behind DetectiveMap and CurtainMap: what to draw, the legend lines, the camera padding and the
// point/box picking steps. No DOM, no maplibre: the components turn these into map calls.
import type { Bbox } from "../events.ts";
import type { Target } from "../request.ts";
import { boxFromCorners, wrapLon } from "../request.ts";
import { GIBS_ATTRIBUTION, TERRAIN, catalogLayer } from "./catalog.ts";
import type { CurtainView, LayerView, MapView } from "./mapView.ts";

/** Every map layer and source this feature adds starts with this, so it never touches the base style. */
export const DRAW_PREFIX = "det-";

export type DrawSpec =
  | { id: string; kind: "raster"; tiles: string[]; maxzoom: number; opacity: number; attribution: string }
  | { id: string; kind: "image"; url: string; bbox: Bbox; opacity: number; attribution: string; crisp: boolean }
  | { id: string; kind: "footprint"; bbox: Bbox; text: string }
  | { id: string; kind: "outline"; bbox: Bbox }
  | { id: string; kind: "point"; lat: number; lon: number };

export type MapSide = "main" | "curtain";

const slug = (s: string): string => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "x";

function layerSpec(id: string, lv: LayerView): DrawSpec {
  if (lv.render.type === "tiles") {
    return { id, kind: "raster", tiles: [lv.render.url], maxzoom: lv.render.maxzoom, opacity: lv.opacity, attribution: GIBS_ATTRIBUTION };
  }
  return {
    id, kind: "image", url: lv.render.url, bbox: [...lv.render.bbox] as Bbox, opacity: lv.opacity, attribution: lv.source,
    crisp: lv.crisp === true,
  };
}

/**
 * The vectors drawn on both maps: data-cell footprints, then the picked box. The main map shows a picked point as a
 * DOM marker; the curtain map asks for it as a layer (`point: true`) so it stays visible right of the divider.
 */
export function overlaySpecs(view: MapView, target: Target | null, opts: { point?: boolean } = {}): DrawSpec[] {
  const out: DrawSpec[] = view.footprints.map((fp) => ({
    id: `${DRAW_PREFIX}fp-${slug(fp.source)}`, kind: "footprint" as const, bbox: [...fp.bbox] as Bbox,
    text: `${fp.label} · approximate`,
  }));
  if (target && target.kind !== "point") out.push({ id: `${DRAW_PREFIX}target`, kind: "outline", bbox: [...target.bbox] as Bbox });
  if (target && target.kind === "point" && opts.point) {
    out.push({ id: `${DRAW_PREFIX}target`, kind: "point", lat: target.lat, lon: target.lon });
  }
  return out;
}

/** Context layers that are pictures, not coloured data: they may sit under one evidence layer. */
const PICTURE_CONTEXT: ReadonlySet<string> = new Set(["true_colour", "true_colour_viirs", "base", "base_hq", "hillshade"]);

/**
 * One coloured layer at a time (DESIGN.md): a coloured context (land cover) is drawn only while nothing else is;
 * a photograph or relief context stays under the evidence or the curtain.
 */
export function contextDrawn(view: MapView): boolean {
  if (!view.context) return false;
  if (PICTURE_CONTEXT.has(view.context.layerId)) return true;
  return !view.evidence && !view.curtain;
}

/**
 * Bottom to top, all below the base style's borders. The main map draws the context, then the evidence (or the
 * curtain's left side); the curtain map draws only the curtain's right side, so one coloured layer shows per side.
 */
export function drawSpecs(view: MapView, side: MapSide, target: Target | null): DrawSpec[] {
  const out: DrawSpec[] = [];
  if (side === "main") {
    if (view.context && contextDrawn(view)) out.push(layerSpec(`${DRAW_PREFIX}context`, view.context));
    const top = view.curtain ? view.curtain.left : view.evidence;
    if (top) out.push(layerSpec(`${DRAW_PREFIX}evidence`, top));
  } else if (view.curtain) {
    out.push(layerSpec(`${DRAW_PREFIX}evidence`, view.curtain.right));
  }
  return [...out, ...overlaySpecs(view, target)];
}

/** What decides whether a source must be rebuilt. Opacity is excluded: it is a paint change. */
export function specSignature(spec: DrawSpec): string {
  switch (spec.kind) {
    case "raster":
      return `raster:${spec.tiles.join("|")}:${spec.maxzoom}`;
    case "image":
      return `image:${spec.url}:${spec.bbox.join(",")}:${spec.crisp ? "crisp" : "smooth"}`;
    case "footprint":
      return `fp:${spec.bbox.join(",")}:${spec.text}`;
    case "outline":
      return `box:${spec.bbox.join(",")}`;
    case "point":
      return `pt:${spec.lon},${spec.lat}`;
  }
}

/** The map layer ids a spec adds, bottom to top. */
export function specLayerIds(spec: DrawSpec): string[] {
  switch (spec.kind) {
    case "raster":
      return [`${spec.id}-raster`];
    case "image":
      return [`${spec.id}-image`];
    case "footprint":
      return [`${spec.id}-edge`, `${spec.id}-label`];
    case "outline":
      return [`${spec.id}-edge`];
    case "point":
      return [`${spec.id}-dot`];
  }
}

/** Image source corners: top-left, top-right, bottom-right, bottom-left. */
export function imageCoordinates(bbox: Bbox): [[number, number], [number, number], [number, number], [number, number]] {
  const [w, s, e, n] = bbox;
  return [[w, n], [e, n], [e, s], [w, s]];
}

type Position = [number, number];
export interface PolygonFeature { type: "Feature"; properties: Record<string, never>; geometry: { type: "Polygon"; coordinates: Position[][] } }
export interface PointFeature { type: "Feature"; properties: { text: string }; geometry: { type: "Point"; coordinates: Position } }
export interface FeatureCollection { type: "FeatureCollection"; features: (PolygonFeature | PointFeature)[] }

export function bboxPolygon(bbox: Bbox): PolygonFeature {
  const [w, s, e, n] = bbox;
  return { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] } };
}

/** A footprint: its outline plus one label point on the north edge. */
export function footprintData(bbox: Bbox, text: string): FeatureCollection {
  const [w, , e, n] = bbox;
  return {
    type: "FeatureCollection",
    features: [bboxPolygon(bbox), { type: "Feature", properties: { text }, geometry: { type: "Point", coordinates: [(w + e) / 2, n] } }],
  };
}

// ---- camera ----

export const READING_BREAKPOINT = 1100;
const EDGE = 48;

export interface Padding { top: number; right: number; bottom: number; left: number }

/** fitBounds padding: the reading column takes 40 % of the width at ≥ 1100 px. Shrunk when the map is too small. */
export function fitPadding(width: number, height: number): Padding {
  const left = width >= READING_BREAKPOINT ? Math.round(width * 0.4) : EDGE;
  const pad: Padding = { top: EDGE, right: EDGE + 24, bottom: EDGE + 48, left };
  const fitsX = pad.left + pad.right < width - 64;
  const fitsY = pad.top + pad.bottom < height - 64;
  return {
    top: fitsY ? pad.top : 8, bottom: fitsY ? pad.bottom : 8,
    left: fitsX ? pad.left : 8, right: fitsX ? pad.right : 8,
  };
}

/** Where the curtain divider starts: the middle of the map that the reading column leaves visible. */
export function initialSplit(width: number): number {
  return width >= READING_BREAKPOINT ? 70 : 50;
}

// ---- picking ----

export type PickMode = "point" | "box";
export type PickResult = { target: Target } | { error: string };
export interface Corner { lat: number; lon: number }

/** One tap. Point mode answers at once; box mode keeps the first corner and answers on the second tap. */
export function pickStep(pending: Corner | null, mode: PickMode, at: Corner): { pending: Corner | null; result: PickResult | null } {
  if (mode === "point") return { pending: null, result: { target: { kind: "point", lat: at.lat, lon: wrapLon(at.lon) } } };
  if (!pending) return { pending: { lat: at.lat, lon: at.lon }, result: null };
  const box = boxFromCorners(pending, at);
  return { pending: null, result: box.ok ? { target: { kind: "box", bbox: box.bbox } } : { error: box.message } };
}

export const OPPOSITE_CORNER_HINT = "Tap the opposite corner";

// ---- words on screen ----

const sideYear = (lv: LayerView, fallback: string): string => (lv.year != null ? String(lv.year) : fallback);

export function curtainYears(c: CurtainView): [string, string] {
  return [sideYear(c.left, "Before"), sideYear(c.right, "After")];
}

export function curtainAriaLabel(c: CurtainView): string {
  const [a, b] = curtainYears(c);
  return `Slide between ${a} and ${b}`;
}

/** The time a layer shows, as drawn: a full date for daily/monthly tiles, the year otherwise, or a file's period. */
export function drawnWhen(lv: LayerView): string | null {
  if (lv.period) return `Period: ${lv.period[0]}–${lv.period[1]}`;
  const dates = lv.date ? catalogLayer(lv.layerId)?.dates : undefined;
  if (lv.date && dates && dates.step !== "annual" && !dates.years?.length) return `Date drawn: ${lv.date}`;
  return lv.year != null ? `Year drawn: ${lv.year}` : null;
}

/** The value as written, with a real minus sign. */
const signed = (n: number): string => String(n).replace("-", "−");

export interface LegendEntry {
  key: string; role: string; title: string; when: string | null; unit: string | null; range: string | null;
  ramp: string[]; labels: string[]; source: string; resolution: string | null;
}

function entryFor(lv: LayerView, role: string, when: string | null): LegendEntry {
  const lg = lv.legend;
  return {
    key: `${role}:${lv.key}`, role, title: lv.title, when,
    unit: lg?.unit ?? null,
    // "−1.6 to 1.6", not "-1.6–1.6": a dash between two signed numbers reads as a third minus.
    range: lg && lg.min != null && lg.max != null ? `${signed(lg.min)} to ${signed(lg.max)}` : null,
    // TODO(catalog): GIBS catalog legends carry only a `colormap` XML URL (layerCatalog.generated.ts), no stops, so
    // they get no ramp here. Copy the stops into the catalog at generation time; never invent them on the front.
    ramp: lg?.stops ?? [], labels: lg?.labels ?? [],
    source: lv.source,
    resolution: lv.resolution ? `${lv.resolution} pixels, ${lv.crisp ? "drawn as they are" : "smoothed for display"}` : null,
  };
}

export interface FootprintLine { key: string; text: string; size: string; source: string }

export interface LegendModel {
  entries: LegendEntry[]; footprints: FootprintLine[]; curtain: string | null; terrain: string;
}

export const TERRAIN_LINE = `${TERRAIN.attribution} · Heights ×${TERRAIN.exaggeration}`;

/** DEM tile errors tolerated before the relief is dropped and the map goes flat. */
export const DEM_ERRORS_BEFORE_FLAT = 3;

/** The map's accessible name, which says what a tap does. */
export function mapLabel(pickEnabled: boolean, mode: PickMode): string {
  if (!pickEnabled) return "Globe showing the investigation.";
  return mode === "box" ? "Globe. Tap two corners to draw a box." : "Globe. Tap a place to investigate it.";
}

/** Every drawn layer, top first: the evidence (or the curtain's sides), the context, then the footprints. */
export function legendModel(view: MapView, opts: { flat?: boolean } = {}): LegendModel | null {
  const entries: LegendEntry[] = [];
  let curtain: string | null = null;
  if (view.curtain) {
    const [a, b] = curtainYears(view.curtain);
    curtain = `Left: ${a} · Right: ${b}`;
    entries.push(entryFor(view.curtain.left, "Compared", null));
  } else if (view.evidence) {
    entries.push(entryFor(view.evidence, "Evidence", drawnWhen(view.evidence)));
  }
  if (view.context && contextDrawn(view)) entries.push(entryFor(view.context, "Context", drawnWhen(view.context)));
  const footprints = view.footprints.map((fp) => ({
    key: fp.source, text: `${fp.label} · approximate`, size: fp.size, source: fp.source,
  }));
  if (entries.length === 0 && footprints.length === 0) return null;
  return { entries, footprints, curtain, terrain: opts.flat ? TERRAIN.attribution : TERRAIN_LINE };
}
