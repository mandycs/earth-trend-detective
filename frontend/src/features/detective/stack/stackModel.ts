// The exploded evidence stack (Task 17): the layers the agent drew in the current turn, as slabs over the relief of
// the same box. Pure and deterministic: every figure on a slab is copied from a tool result, the catalog or
// sites/<id>/; nothing here computes a number that is printed.
import type { Direction, Verdict } from "../../../story/types";
import type { StampBeat } from "../board.ts";
import { verdictFor } from "../board.ts";
import type { Bbox, MapOp } from "../events.ts";
import type { Investigation, Scene } from "../scenes.ts";
import { BLUE_MARBLE, blueMarbleUrl, catalogLayer, wmsUrl } from "../map/catalog.ts";
import { applyMapOp, openingView } from "../map/mapView.ts";
import type { FootprintView, LayerLegend, LayerView, MapContext, MapView } from "../map/mapView.ts";

export const STACK_MAX = 5;

export interface StackVerdict { verdict: Verdict; direction: Direction; label: string | null }
export type SlabTexture =
  | { kind: "wms"; url: string }
  | { kind: "png"; url: string }
  /** One coarse block: the data cell (footprint bbox) where one value covers everything inside. */
  | { kind: "cell"; cellKm: number | null; bbox: Bbox };
/** What picking the slab shows on the main map. */
export type SlabShow = { kind: "layer"; layer: LayerView } | { kind: "footprint"; footprint: FootprintView };
export interface Slab {
  key: string; title: string; source: string; resolution: string | null;
  /** The drawn year (never the asked one), or the period a single-file layer or a tested series covers. */
  year: number | null; date: string | null; period: [number, number] | null;
  legend: LayerLegend | null; verdict?: StackVerdict; stamp?: StampBeat; texture: SlabTexture;
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
export interface StackModel { bbox: Bbox | null; base: StackBase | null; slabs: Slab[] }

export const EMPTY_STACK: StackModel = Object.freeze({ bbox: null, base: null, slabs: [] }) as StackModel;

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

function draftFor(d: Drawn, bbox: Bbox, tested: Tested[], sources: Map<string, string>, inv: Investigation, ctx: MapContext): Draft {
  const vars = d.kind === "layer" ? varsOfLayer(d.layer, ctx) : varsOfCell(d.footprint, tested, sources);
  const mine = tested.filter((t) => vars.has(t.varId));
  const lastVerdict = [...mine].reverse().find((t) => t.verdict);
  const verdict = lastVerdict?.verdict
    ? { verdict: lastVerdict.verdict.verdict, direction: lastVerdict.verdict.direction, label: lastVerdict.label }
    : undefined;
  const stamp = stampFor(new Set(mine.flatMap((t) => t.evidence)), inv.board);
  const extra = { ...(verdict ? { verdict } : {}), ...(stamp ? { stamp } : {}) };
  if (d.kind === "layer") {
    const lv = d.layer;
    return {
      key: lv.key, title: lv.title, source: lv.source, resolution: lv.resolution, year: lv.year, date: lv.date,
      period: lv.period, legend: lv.legend, texture: textureOf(lv, bbox), show: { kind: "layer", layer: lv }, ...extra,
    };
  }
  const fp = d.footprint;
  const label = [...mine].reverse().find((t) => t.label)?.label ?? null;
  const period = [...mine].reverse().find((t) => t.years)?.years ?? null;
  return {
    key: `cell:${fp.source}`, title: label ?? "Data cell", source: fp.label, resolution: fp.size, year: null, date: null,
    period, legend: null, texture: { kind: "cell", cellKm: cellKmOf(fp.size), bbox: [...fp.bbox] as Bbox },
    show: { kind: "footprint", footprint: fp }, ...extra,
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
 * The current turn's evidence as a stack. Slabs: the distinct layers and data cells drawn during the turn, those
 * with a verdict first, then the most recent; at most `max`. `view` is the map view at the ending (its place box
 * stands in when the investigation has no place of its own).
 */
export function stackFor(inv: Investigation, view: MapView, opts: { max?: number; ctx: MapContext }): StackModel {
  const place = inv.place;
  if (!place) return EMPTY_STACK;
  const ctx = opts.ctx;
  const max = Math.max(0, Math.floor(opts.max ?? STACK_MAX));
  const bbox = [...(ctx.caseLayers?.bbox ?? view.place?.bbox ?? place.bbox)] as Bbox;
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
  const drawn = [...order.values()];
  const recentFirst = drawn.map((d) => draftFor(d, bbox, tested, sources, inv, ctx)).reverse();
  const picked = [...recentFirst.filter((s) => s.verdict), ...recentFirst.filter((s) => !s.verdict)].slice(0, max);
  const slabs = picked.map((s, i): Slab => ({ ...s, height: picked.length - i }));
  return { bbox, base: baseFor(bbox, ctx), slabs };
}
