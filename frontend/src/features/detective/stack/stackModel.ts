// The exploded evidence stack (Task 17): the layers the agent drew in the current turn, as slabs over the relief of
// the same box. Pure and deterministic: every figure on a slab is copied from a tool result, the catalog or
// sites/<id>/; nothing here computes a number that is printed.
import type { Direction, Verdict } from "../../../story/types";
import type { StampBeat } from "../board.ts";
import { verdictFor } from "../board.ts";
import type { Bbox, MapOp } from "../events.ts";
import type { Investigation, Scene } from "../scenes.ts";
import { BLUE_MARBLE, blueMarbleUrl, catalogLayer, wmsUrl } from "../map/catalog.ts";
import { applyMapOp, openingView, pulledOut } from "../map/mapView.ts";
import type { CaseLayers, FootprintView, LayerLegend, LayerView, MapContext, MapView } from "../map/mapView.ts";

export const STACK_MAX = 5;

export interface StackVerdict { verdict: Verdict; direction: Direction; label: string | null }
export type SlabTexture = { kind: "wms"; url: string } | { kind: "png"; url: string };
/** What picking the slab shows on the main map. */
export type SlabShow = { kind: "layer"; layer: LayerView };
export interface Slab {
  key: string; title: string; source: string; resolution: string | null;
  /** The drawn year (never the asked one), or the period a single-file layer or a tested series covers. */
  year: number | null; date: string | null; period: [number, number] | null;
  legend: LayerLegend | null; verdict?: StackVerdict; stamp?: StampBeat; texture: SlabTexture;
  /** Drawn from the solved case's own files, not by this turn (only in an investigation's stack). */
  fromCase?: true;
  /** Evenly spaced steps above the base: the first slab is the highest (n), the last sits at 1. */
  height: number;
  show: SlabShow;
}
export interface StackPicture { url: string; title: string; source: string; resolution: string | null }
export interface StackBase {
  /** "relief": a NASADEM heightmap from sites/<id>/; "flat": a free point, the picture on a flat plane. */
  kind: "relief" | "flat";
  title: string; source: string; resolution: string | null;
  heightmap: { url: string; encoding: "terrain-rgb" | "grey"; rangeM: [number, number] | null } | null;
  picture: StackPicture | null;
}
/**
 * A data cell the turn showed (a footprint). Not a map: one value covers the whole cell, so it is drawn as an outline
 * on the ground, never as a slab. It carries the verdict and stamp of the variables it measures.
 */
export interface StackCell {
  key: string; title: string; label: string; size: string; cellKm: number | null; bbox: Bbox;
  period: [number, number] | null; verdict?: StackVerdict; stamp?: StampBeat;
  /** The cell is at least as big as the stack's box on every side: its outline is the box's own edge. */
  coversBox: boolean;
  footprint: FootprintView;
}
export interface StackModel {
  bbox: Bbox | null; base: StackBase | null; slabs: Slab[]; cells: StackCell[];
  /** Said under the title when fewer than two records could be drawn as maps. */
  note: string | null;
}

export const EMPTY_STACK: StackModel = Object.freeze({ bbox: null, base: null, slabs: [], cells: [], note: null }) as StackModel;

export const ONE_MAP_NOTE = "Only one record could be drawn as a map here.";
export const NO_MAP_NOTE = "No record here could be drawn as a map: the data cells are outlined on the ground.";

/** The honest line for a thin stack: nothing when two or more records are maps. */
export function stackNote(slabs: number, cells: number): string | null {
  if (slabs === 1) return ONE_MAP_NOTE;
  if (slabs === 0 && cells > 0) return NO_MAP_NOTE;
  return null;
}

/** Something to explode: at least one map slab or one data cell. */
export function hasStack(m: StackModel | null): m is StackModel {
  return !!m && (m.slabs.length > 0 || m.cells.length > 0);
}

/**
 * The solved case a place sits in, for its stack: the place's own `site_id`, else the case whose box holds the
 * place's centre (a point typed inside Lake Mead is in the Lake Mead case). A case the agent only cited from
 * elsewhere is not used: its layers would be of another place.
 */
export function stackCaseSite(
  place: { lat: number; lon: number; site_id: string | null } | null,
  cases: readonly { id: string; bbox: Bbox }[],
): string | null {
  if (!place) return null;
  if (place.site_id) return place.site_id;
  const hit = cases.find(({ bbox: [w, s, e, n] }) => place.lon >= w && place.lon <= e && place.lat >= s && place.lat <= n);
  return hit?.id ?? null;
}

/** "~300 km" → 300. Only read from the footprint's own size text; null when it carries no km figure. */
export function cellKmOf(size: string): number | null {
  const m = /(\d+(?:\.\d+)?)\s*km/i.exec(size);
  return m ? Number(m[1]) : null;
}

// ---- what the turn tested ----

interface Tested {
  varId: string; testId: string | null; label: string | null; years: [number, number] | null;
  evidence: string[]; verdict: { verdict: Verdict; direction: Direction } | null;
}

const str = (x: unknown): string | null => (typeof x === "string" && x !== "" ? x : null);
function years(x: unknown): [number, number] | null {
  return Array.isArray(x) && x.length === 2 && typeof x[0] === "number" && typeof x[1] === "number" ? [x[0], x[1]] : null;
}

function testedIn(scenes: readonly Scene[], board: Investigation["board"]): Tested[] {
  const out: Tested[] = [];
  for (const s of scenes) {
    const t = s.tool;
    if (!t || t.state !== "done" || !t.result) continue;
    const r = t.result;
    const varId = str(r.var_id) ?? str(t.args.var_id);
    if (!varId) continue;
    const testId = str(r.test_id);
    const evidence = [t.evidenceId, str(r.evidence_id)].filter((e): e is string => e !== null);
    out.push({
      varId, testId, label: str(r.label), years: years(r.years), evidence,
      verdict: testId ? verdictFor(testId, board, r) : null,
    });
  }
  return out;
}

/** var id → source id ("grace_tws" → "grace"), from every list_variables result of the thread. */
function varSources(scenes: readonly Scene[]): Map<string, string> {
  const out = new Map<string, string>();
  for (const s of scenes) {
    const vs = s.tool?.tool === "list_variables" ? s.tool.result?.variables : null;
    if (!Array.isArray(vs)) continue;
    for (const v of vs) {
      const o = v as Record<string, unknown> | null;
      const id = str(o?.id);
      const src = str(o?.source);
      if (id && src) out.set(id, src);
    }
  }
  return out;
}

// ---- what the turn drew ----

type Drawn = { kind: "layer"; layer: LayerView } | { kind: "footprint"; footprint: FootprintView };

function drawnKey(d: Drawn): string {
  return d.kind === "layer" ? d.layer.key : `cell:${d.footprint.source}`;
}

/** Layers and footprints an op brought onto the map (compared with the view before it). */
function introduced(before: MapView, after: MapView, op: MapOp): Drawn[] {
  if (op.op === "show_footprint") {
    const fp = after.footprints.find((f) => f.source === op.source);
    return fp ? [{ kind: "footprint", footprint: fp }] : [];
  }
  if (op.op === "fly_to") return [];
  const out: Drawn[] = [];
  if (after.curtain && after.curtain !== before.curtain) {
    out.push({ kind: "layer", layer: after.curtain.left }, { kind: "layer", layer: after.curtain.right });
  }
  for (const slot of ["context", "evidence"] as const) {
    const lv = after[slot];
    if (lv && lv !== before[slot]) out.push({ kind: "layer", layer: lv });
  }
  return out;
}

/** Index of the current turn's opening scene (0 when there is none). */
function turnStart(scenes: readonly Scene[]): number {
  for (let i = scenes.length - 1; i >= 0; i--) if (scenes[i].kind === "opening") return i;
  return 0;
}

// ---- slabs ----

function varsOfLayer(lv: LayerView, ctx: MapContext): Set<string> {
  const row = ctx.caseLayers?.rows[lv.layerId] as { var?: unknown } | undefined;
  const v = str(row?.var);
  // Catalog layers name their variable by id only when the ids are the same (ndvi, lst_day, soil_moisture).
  return new Set(v ? [v] : [lv.layerId]);
}

function varsOfCell(fp: FootprintView, tested: Tested[], sources: Map<string, string>): Set<string> {
  const out = new Set<string>();
  for (const t of tested) {
    const src = sources.get(t.varId);
    if (src === fp.source || (!src && (t.varId === fp.source || t.varId.startsWith(`${fp.source}_`)))) out.add(t.varId);
  }
  return out;
}

function stampFor(evidence: Set<string>, board: Investigation["board"]): StampBeat | undefined {
  let found: StampBeat | undefined;
  for (const sp of board?.suspects ?? []) {
    if (sp.status === "open") continue;
    if (sp.evidence.some((e) => evidence.has(e))) {
      found = { suspectId: sp.id, label: sp.label, status: sp.status, downgraded: sp.downgraded };
    }
  }
  return found;
}

function textureOf(lv: LayerView, bbox: Bbox): SlabTexture {
  if (lv.render.type === "image") return { kind: "png", url: lv.render.url };
  const layer = catalogLayer(lv.layerId);
  if (layer && lv.date) return { kind: "wms", url: wmsUrl(layer, lv.date, bbox) };
  return { kind: "png", url: lv.render.url };
}

type Draft = Omit<Slab, "height">;

function findings(vars: Set<string>, tested: Tested[], inv: Investigation): { mine: Tested[]; verdict?: StackVerdict; stamp?: StampBeat } {
  const mine = tested.filter((t) => vars.has(t.varId));
  const lastVerdict = [...mine].reverse().find((t) => t.verdict);
  const verdict = lastVerdict?.verdict
    ? { verdict: lastVerdict.verdict.verdict, direction: lastVerdict.verdict.direction, label: lastVerdict.label }
    : undefined;
  const stamp = stampFor(new Set(mine.flatMap((t) => t.evidence)), inv.board);
  return { mine, ...(verdict ? { verdict } : {}), ...(stamp ? { stamp } : {}) };
}

function layerDraft(lv: LayerView, bbox: Bbox): Draft {
  return {
    key: lv.key, title: lv.title, source: lv.source, resolution: lv.resolution, year: lv.year, date: lv.date,
    period: lv.period, legend: lv.legend, texture: textureOf(lv, bbox), show: { kind: "layer", layer: lv },
  };
}

function withFindings(d: Draft, tested: Tested[], inv: Investigation, ctx: MapContext): Draft {
  const { verdict, stamp } = findings(varsOfLayer(d.show.layer, ctx), tested, inv);
  return { ...d, ...(verdict ? { verdict } : {}), ...(stamp ? { stamp } : {}) };
}

function covers(cell: Bbox, box: Bbox): boolean {
  return cell[0] <= box[0] && cell[1] <= box[1] && cell[2] >= box[2] && cell[3] >= box[3];
}

function cellFor(fp: FootprintView, box: Bbox, tested: Tested[], sources: Map<string, string>, inv: Investigation): StackCell {
  const { mine, verdict, stamp } = findings(varsOfCell(fp, tested, sources), tested, inv);
  const label = [...mine].reverse().find((t) => t.label)?.label ?? null;
  const period = [...mine].reverse().find((t) => t.years)?.years ?? null;
  return {
    key: `cell:${fp.source}`, title: label ?? "Data cell", label: fp.label, size: fp.size, cellKm: cellKmOf(fp.size),
    bbox: [...fp.bbox] as Bbox, period, coversBox: covers(fp.bbox, box), footprint: fp,
    ...(verdict ? { verdict } : {}), ...(stamp ? { stamp } : {}),
  };
}

interface CaseRowLike { id: string; kind?: string; file?: string; title?: string; source?: unknown; encoding?: unknown; range_m?: unknown }

function rowSource(row: CaseRowLike): string {
  if (typeof row.source === "string") return row.source;
  return str((row.source as { name?: unknown } | null)?.name) ?? "";
}

function baseFor(bbox: Bbox, ctx: MapContext): StackBase {
  const cl = ctx.caseLayers;
  const rows = cl ? (Object.values(cl.rows) as CaseRowLike[]) : [];
  const relief = rows.find((r) => r.kind === "heightmap" && r.file);
  if (cl && relief?.file) {
    const pic = cl.rows.base_hq ?? cl.rows.base;
    const range = years(relief.range_m);
    return {
      kind: "relief", title: relief.title ?? "Terrain height", source: rowSource(relief), resolution: null,
      heightmap: {
        url: `/sites/${cl.siteId}/${relief.file}`, encoding: relief.encoding === "terrain-rgb" ? "terrain-rgb" : "grey",
        rangeM: range,
      },
      picture: pic?.file
        ? { url: `/sites/${cl.siteId}/${pic.file}`, title: pic.title ?? pic.id, source: rowSource(pic as CaseRowLike), resolution: null }
        : null,
    };
  }
  // A free point: no relief model, and a picture with no clouds on a flat plane. A daily true-colour picture is often
  // mostly cloud; the Blue Marble composite (the same picture as the globe's base) never is. A true-colour picture
  // the run drew is a slab of its own.
  return {
    kind: "flat", title: "Flat base: no relief model for this place", source: BLUE_MARBLE.source, resolution: null,
    heightmap: null,
    picture: { url: blueMarbleUrl(bbox), title: BLUE_MARBLE.title, source: BLUE_MARBLE.source, resolution: null },
  };
}

/**
 * The current turn's evidence as a stack. Slabs: the distinct layers drawn during the turn, those with a verdict
 * first, then the most recent; then, when the place is in a solved case (`ctx.caseLayers`), that case's own data
 * layers (trend first, yearly ones at their last year), with no repeats; at most `max` in all. Data cells
 * (footprints) are never slabs: they are outlined on the ground (`cells`). `view` is the map view at the ending
 * (its place box stands in when the investigation has no place of its own).
 */
export function stackFor(inv: Investigation, view: MapView, opts: { max?: number; ctx: MapContext }): StackModel {
  const place = inv.place;
  if (!place) return EMPTY_STACK;
  const ctx = opts.ctx;
  const max = Math.max(0, Math.floor(opts.max ?? STACK_MAX));
  // A solved case: its own box. Else the box the ending frames (the place grown 4×): a point's own 0.2° box is
  // too small for a 500 m layer to read as anything but a few blocks.
  const bbox = ctx.caseLayers ? ([...ctx.caseLayers.bbox] as Bbox) : pulledOut(view.place?.bbox ?? place.bbox);
  const from = turnStart(inv.scenes);

  // Replay the whole thread (set_year depends on what is on the map), collecting only the current turn.
  const order = new Map<string, Drawn>();
  let v = openingView(place, ctx.now);
  inv.scenes.forEach((s, i) => {
    for (const op of s.mapOps) {
      const next = applyMapOp(v, op, ctx);
      if (i >= from) {
        for (const d of introduced(v, next, op)) {
          const k = drawnKey(d);
          order.delete(k); // shown again: it moves to the most recent place
          order.set(k, d);
        }
      }
      v = next;
    }
  });

  const turn = inv.scenes.slice(from);
  const tested = testedIn(turn, inv.board);
  const sources = varSources(inv.scenes);
  const drawn = [...order.values()].reverse();
  const own = drawn.flatMap((d) => (d.kind === "layer" ? [withFindings(layerDraft(d.layer, bbox), tested, inv, ctx)] : []));
  const ownOrdered = [...own.filter((s) => s.verdict), ...own.filter((s) => !s.verdict)];
  const seen = new Set(ownOrdered.map((s) => s.key));
  const fromCase = (ctx.caseLayers ? caseDrafts(ctx.caseLayers, ctx, bbox) : [])
    .filter((d) => !seen.has(d.key))
    .map((d): Draft => ({ ...withFindings(d, tested, inv, ctx), fromCase: true }));
  const picked = [...ownOrdered, ...fromCase].slice(0, max);
  const slabs = picked.map((s, i): Slab => ({ ...s, height: picked.length - i }));
  const cells = drawn.flatMap((d) => (d.kind === "footprint" ? [cellFor(d.footprint, bbox, tested, sources, inv)] : []));
  return { bbox, base: baseFor(bbox, ctx), slabs, cells, note: stackNote(slabs.length, cells.length) };
}

// ---- a solved case's own layers (story mode "Layers") ----

/** Row kinds that are data layers a case ships, in the order they stack: the analysed trend first. */
const CASE_SLAB_KINDS: readonly string[] = ["trend", "yearly"];

/**
 * A solved case's own data layers as a stack, with no investigation: each trend map over its period, each yearly
 * layer at its last year (the year drawn is on the card). Pictures, relief and shading are the base, not slabs.
 * No verdicts or stamps: nothing was tested in this view.
 */
export function stackForCase(cl: CaseLayers, opts: { max?: number; now?: string | null } = {}): StackModel {
  const max = Math.max(0, Math.floor(opts.max ?? STACK_MAX));
  const ctx: MapContext = { caseLayers: cl, now: opts.now ?? null };
  const bbox = [...cl.bbox] as Bbox;
  const picked = caseDrafts(cl, ctx, bbox).slice(0, max);
  const slabs = picked.map((d, i): Slab => ({ ...d, height: picked.length - i }));
  return { bbox, base: baseFor(bbox, ctx), slabs, cells: [], note: slabs.length === 1 ? ONE_MAP_NOTE : null };
}

/** A case's data layers as slab drafts, in stacking order, textured for `bbox`. */
function caseDrafts(cl: CaseLayers, ctx: MapContext, bbox: Bbox): Draft[] {
  const rows = Object.values(cl.rows)
    .filter((r) => CASE_SLAB_KINDS.includes(r.kind) && (r.file || r.file_pattern))
    .sort((a, b) => CASE_SLAB_KINDS.indexOf(a.kind) - CASE_SLAB_KINDS.indexOf(b.kind));
  const place = { lat: (bbox[1] + bbox[3]) / 2, lon: (bbox[0] + bbox[2]) / 2, bbox };
  const empty: MapView = { place, context: null, evidence: null, curtain: null, footprints: [], camera: null, notes: [] };
  const drafts: Draft[] = [];
  for (const r of rows) {
    const years = r.years ?? [];
    const last = years.length > 0 ? years[years.length - 1] : null;
    const v = applyMapOp(empty, { op: "show_layer", layer_id: r.id, date: null, year: last, opacity: 1 }, ctx);
    const lv = v.evidence ?? v.context;
    if (lv) drafts.push(layerDraft(lv, bbox));
  }
  return drafts;
}

export const CASE_STACK_EMPTY = "This case has no data layers to stack.";
export const CASE_STACK_FAILED = "The layers could not be loaded. Try again.";

/** What the story's "Layer stack" button says after a load: nothing when the stack opens, else why not. */
export function caseStackNote(r: { failed: true } | { slabs: number }): string | null {
  if ("failed" in r) return CASE_STACK_FAILED;
  return r.slabs > 0 ? null : CASE_STACK_EMPTY;
}
