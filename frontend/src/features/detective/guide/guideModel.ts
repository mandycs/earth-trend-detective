// "How to read this map": the words of the guide, built from what is drawn right now. Pure: no DOM, no React.
// Two tiers. Plain words for anyone (a 16-year-old in front of a projector); "Under the hood" for the curious, with
// datasets, methods and the tool calls of this run. Every figure printed (sizes, years, resolutions) is copied from
// the map view or from an event; nothing is computed or guessed for printing.
import type { DetEvent } from "../events.ts";
import type { Investigation } from "../scenes.ts";
import type { Target } from "../request.ts";
import type { LayerView, MapView } from "../map/mapView.ts";
import { contextDrawn, curtainYears } from "../map/draw.ts";
import { catalogLayer } from "../map/catalog.ts";
import { LAND_COVER_CLASSES, landCoverClasses } from "../map/landCover.ts";
import type { LandCoverClass } from "../map/landCover.ts";
import { instrumentOf, questionReading, varCatalog } from "../instruments.ts";
import { STATUS_WORDS } from "../board.ts";
import { PROVIDERS, VAR_DATASETS, providerOfSource } from "./datasets.ts";

// ---------------------------------------------------------------- plain words

export type GuideMark = "pin" | "box" | "cell" | "layer" | "curtain" | "picture";
export interface PlainItem {
  key: string; mark: GuideMark; title: string; text: string;
  /** Extra lines: the layer's own legend words, the year drawn. */
  lines: string[];
  ramp: string[]; classes: readonly LandCoverClass[];
}
export interface StampLine { icon: string; text: string; meaning: string }
export interface PlainGuide {
  /** Nothing is drawn yet: the items explain what will appear. */
  generic: boolean;
  items: PlainItem[];
  steps: { title: string; text: string }[];
  stamps: { verdicts: StampLine[]; suspects: StampLine[] };
  framing: string;
}

export const FRAMING = "The satellites measure. Alibi tests. You decide.";
export const CLUE_LINE = "Whatever Alibi finds is a clue, not proof.";

/** What a layer's colors mean, in everyday words, by layer id. Meaning only: colors are named only when a key
 * with the real colors is drawn next to the words (land cover). */
const LAYER_WORDS: Readonly<Record<string, string>> = {
  true_colour: "A real photo from space, like looking down from a very high plane.",
  true_colour_viirs: "A real photo from space, like looking down from a very high plane.",
  base: "A real photo from space, like looking down from a very high plane.",
  base_hq: "A cloud-free photo from space, sharp enough to see fields and roads.",
  before_after: "Two real photos from space of the same spot, years apart.",
  hillshade: "Shading that makes hills and valleys pop out.",
  precipitation: "Rain falling that day: the heavier the rain, the stronger the color.",
  ndvi: "How green the plants are, from bare ground to thick green.",
  ndvi_gibs: "How green the plants are, from bare ground to thick green.",
  lst_day: "How hot the ground gets by day. That is the ground itself, not the air.",
  lst_gibs: "How hot the ground gets by day. That is the ground itself, not the air.",
  year_lst_day: "How hot the ground was that year, compared with its usual.",
  trend_lst_day: "Where the ground has been heating up or cooling down over the years.",
  soil_moisture: "How wet the soil is down where plant roots are.",
  snow_cover: "Where snow covers the ground.",
  night_lights: "Lights at night: bright spots are towns and cities.",
  active_fires: "Dots are fires or very hot spots the satellite saw.",
  sst: "How warm the sea surface is.",
  chlorophyll: "How much tiny algae floats in the water.",
};

/** Land cover in plain words, naming only colors that the key beside it really shows. */
export function landCoverWords(classes: readonly LandCoverClass[] = LAND_COVER_CLASSES): string {
  const has = (n: string) => classes.some((c) => c.name === n);
  const parts = [
    has("Urban / built-up") ? "red patches = cities and towns" : null,
    has("Water") ? "blue = water" : null,
    has("Forest") ? "green = forest" : null,
    has("Barren") ? "gray = bare ground" : null,
  ].filter((x): x is string => !!x);
  return `Each color is a kind of ground${parts.length ? `: ${parts.join(", ")}` : ""}.`;
}

/** The time a layer shows, said plainly; null when the view carries none. */
export function whenPlain(lv: LayerView): string | null {
  if (lv.period) return `It sums up ${lv.period[0]}–${lv.period[1]}.`;
  const dates = lv.date ? catalogLayer(lv.layerId)?.dates : undefined;
  if (lv.date && dates && dates.step !== "annual" && !dates.years?.length) return `Picture from ${lv.date}.`;
  return lv.year != null ? `Showing ${lv.year}.` : null;
}

function layerWords(lv: LayerView): string {
  const classes = landCoverClasses(lv.layerId);
  if (classes.length > 0) return landCoverWords(classes);
  if (Object.hasOwn(LAYER_WORDS, lv.layerId)) return LAYER_WORDS[lv.layerId];
  const base = lv.layerId.replace(/^(year|trend)_/, "").replace(/_gibs$/, "");
  if (Object.hasOwn(LAYER_WORDS, base)) return LAYER_WORDS[base];
  if (lv.layerId.startsWith("overlay:")) return "A map the detective made for this question, one colored square per data cell.";
  const unit = lv.legend?.unit;
  return unit ? `The colors show ${unit}.` : "One record drawn as a map.";
}

function layerItem(lv: LayerView, key: string, title: string): PlainItem {
  const legendLines = lv.legend?.labels ?? [];
  const when = whenPlain(lv);
  const picture = !lv.legend?.stops?.length && landCoverClasses(lv.layerId).length === 0 && /picture|photo|true colour/i.test(`${lv.legend?.unit ?? ""} ${lv.title}`);
  return {
    key, mark: picture ? "picture" : "layer", title: `${title}: ${lv.title}`, text: layerWords(lv),
    lines: [...legendLines, ...(when ? [when] : [])],
    ramp: lv.legend?.stops ?? [], classes: landCoverClasses(lv.layerId),
  };
}

const item = (key: string, mark: GuideMark, title: string, text: string): PlainItem => ({
  key, mark, title, text, lines: [], ramp: [], classes: [],
});

/** What is on the map right now, top first. Empty when nothing is drawn. */
export function lookingAt(view: MapView, target: Target | null): PlainItem[] {
  const out: PlainItem[] = [];
  if (target?.kind === "point") out.push(item("pin", "pin", "The pin", "The place you asked about."));
  else if (target?.kind === "box") out.push(item("box", "box", "The box", "The area you drew. Alibi looks at all of it."));
  for (const fp of view.footprints) {
    out.push(item(`cell:${fp.source}`, "cell", "The dashed square",
      `One satellite value covers this whole square (${fp.size} across), not just your spot. It can't see a single street or field, and the outline is approximate.`));
  }
  if (view.curtain) {
    const [a, b] = curtainYears(view.curtain);
    out.push(item("curtain", "curtain", "The curtain", `Drag the line across the map to compare two years: ${a} on the left, ${b} on the right.`));
    out.push({ ...layerItem(view.curtain.left, "curtain-layer", "Compared"), lines: view.curtain.left.legend?.labels ?? [] });
  } else if (view.evidence) {
    out.push(layerItem(view.evidence, "evidence", "Colored layer"));
  }
  if (view.context && contextDrawn(view)) out.push(layerItem(view.context, "context", "Underneath"));
  return out;
}

/** The same items before any investigation: what will appear, said generically. */
export const GENERIC_ITEMS: readonly PlainItem[] = [
  item("pin", "pin", "The pin", "Click or tap the globe to drop it on the place you want to ask about, or draw a box."),
  item("cell", "cell", "The dashed square", "Satellites measure in squares. One value covers the whole square, not just your spot, so the square shows how big it is."),
  item("layer", "layer", "One colored layer", "Alibi paints one record at a time on the ground, like heat, plants or water, so colors never mix."),
  item("curtain", "curtain", "The curtain", "When Alibi compares two years, drag the line across the map to see before and after."),
];

const VERDICT_STAMPS: readonly StampLine[] = [
  { icon: "↑↓", text: "Real", meaning: "It is really changing, and very unlikely to be chance." },
  { icon: "↑↓", text: "Likely", meaning: "Probably changing. A strong hint, not certain yet." },
  { icon: "?", text: "Can't tell yet", meaning: "Too noisy or too short to tell a real change from chance." },
];
const SUSPECT_STAMPS: readonly StampLine[] = [
  { ...pick("supported"), meaning: "This explanation survived every test so far. Still a clue, not proof." },
  { ...pick("hint"), meaning: "Points this way, but not strong enough yet." },
  { ...pick("ruled_out"), meaning: "Tested with enough years, and there is no clear change." },
  { ...pick("trend_only"), meaning: "It is changing too, but no test links it to this change." },
];
function pick(id: keyof typeof STATUS_WORDS): { icon: string; text: string } {
  const w = STATUS_WORDS[id];
  return { icon: w.icon, text: w.text.charAt(0) + w.text.slice(1).toLowerCase() };
}

/** "How Alibi works", in four steps. Step 2 names this run's records when there are some. */
export function howItWorks(inv: Investigation | null): { title: string; text: string }[] {
  const records = inv && inv.place ? questionReading(inv).records.map((r) => r.label) : [];
  return [
    { title: "You ask", text: "Pick a place and ask in your own words, like “Is this lake shrinking?”" },
    {
      title: "Alibi picks the records",
      text: records.length > 0
        ? `It chooses the satellite records that fit the place. Here: ${records.join(", ")}.`
        : "It chooses the satellite records that fit the place: water, rain, heat, plants, snow…",
    },
    { title: "It tests them", text: "Is the change real, or just noise? And does the climate we measured explain it, or is something else going on?" },
    { title: "It shows you", text: "The evidence goes on the map and each suspect gets a stamp. You read it and decide." },
  ];
}

export function plainGuide(view: MapView, target: Target | null, inv: Investigation | null): PlainGuide {
  const items = lookingAt(view, target);
  const generic = items.length === 0;
  return {
    generic,
    items: generic ? [...GENERIC_ITEMS] : items,
    steps: howItWorks(inv),
    stamps: { verdicts: [...VERDICT_STAMPS], suspects: [...SUSPECT_STAMPS] },
    framing: FRAMING,
  };
}

// ---------------------------------------------------------------- the stack, plainly

export const STACK_PLAIN: readonly string[] = [
  "Think of a cake cut open: the ground of your place sits at the bottom, and every slab above it is one satellite record drawn as a map over the same box.",
  "Same box, different records: you can see which changes line up.",
  "A dashed outline on the ground is a record whose single value covers the whole square, so it can't be a map.",
  "Pick a slab to see it full size on the map. The stamp on it says how sure the test is.",
];
export const STACK_TECH: readonly string[] = [
  "Each slab is a texture from the run: GIBS tiles or a case PNG in the box's bounds. The base is a NASADEM heightmap when the place is a solved case, a flat plane otherwise.",
  "Slabs keep their native resolution and their own color scale; the gap between slabs is for reading only, not a value.",
];

// ---------------------------------------------------------------- under the hood

export interface TechLayer { key: string; role: string; title: string; source: string; provider: string | null; resolution: string | null; when: string | null }
export interface TechRecord {
  varId: string; label: string; dataset: string | null; instrument: string | null; provider: string | null;
  resolution: string | null; period: string | null;
}
export interface TechMethod { tool: string; name: string; gloss: string; used: boolean }
export interface ToolCall { key: string; tool: string; args: string; state: "running" | "done" | "failed" }
export interface TechGuide { layers: TechLayer[]; records: TechRecord[]; methods: TechMethod[]; calls: ToolCall[] }

const str = (x: unknown): string | null => (typeof x === "string" && x !== "" ? x : null);
const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

function techLayer(lv: LayerView, key: string, role: string): TechLayer {
  const dates = lv.date ? catalogLayer(lv.layerId)?.dates : undefined;
  const daily = !!(lv.date && dates && dates.step !== "annual" && !dates.years?.length);
  const when = lv.period ? `${lv.period[0]}–${lv.period[1]}` : daily ? lv.date : lv.year != null ? String(lv.year) : null;
  return { key, role, title: lv.title, source: lv.source, provider: providerOfSource(lv.source), resolution: lv.resolution, when };
}

/** The core methods, each with a one-line plain gloss; `used` when its tool ran in this run. */
const CORE_METHODS: readonly { tool: string; name: string; gloss: string }[] = [
  { tool: "trend_test", name: "Mann-Kendall trend test, Hamed & Rao correction", gloss: "Counts how often later values beat earlier ones; the correction stops neighboring months, which look alike, from faking a trend." },
  { tool: "trend_test", name: "Sen slope", gloss: "How fast it changes: the middle value of the slopes between every pair of points, so one odd year can't drag it." },
  { tool: "climate_residual", name: "Climate residual (RESTREND-style)", gloss: "Predicts the record from the climate we measured, then checks if what is left over still trends. Left over = not explained by that climate." },
  { tool: "correlate", name: "Pearson correlation on year-on-year changes", gloss: "Do two records go up and down together from one year to the next? Using the changes removes the shared long-term trend." },
  { tool: "trend_test", name: "False discovery rate (Benjamini-Hochberg), across the conversation", gloss: "The more tests you run, the more flukes you get. Every trend and link test of the whole conversation is corrected together; the climate check keeps its own test." },
];

function records(inv: Investigation): TechRecord[] {
  const vars = varCatalog(inv.scenes);
  const res = new Map<string, string>();
  for (const s of inv.scenes) {
    const r = s.tool?.result;
    if (s.tool?.tool === "list_variables" && r && Array.isArray(r.variables)) {
      for (const v of r.variables) if (isObj(v) && str(v.id) && str(v.resolution)) res.set(v.id as string, v.resolution as string);
    }
  }
  const out: TechRecord[] = [];
  const seen = new Set<string>();
  for (const s of inv.scenes) {
    const t = s.tool;
    if (!t || t.tool !== "get_series" || t.state !== "done") continue;
    const varId = str(t.result?.var_id) ?? str(t.args.var_id);
    if (!varId || seen.has(varId)) continue;
    seen.add(varId);
    const y = t.result?.years;
    const period = Array.isArray(y) && y.length === 2 && typeof y[0] === "number" && typeof y[1] === "number" ? `${y[0]}–${y[1]}` : null;
    const source = vars.get(varId)?.source ?? null;
    out.push({
      varId, label: str(t.result?.label) ?? vars.get(varId)?.label ?? varId,
      dataset: Object.hasOwn(VAR_DATASETS, varId) ? VAR_DATASETS[varId] : null,
      instrument: instrumentOf(varId, vars),
      provider: source && Object.hasOwn(PROVIDERS, source) ? PROVIDERS[source] : null,
      resolution: res.get(varId) ?? null, period,
    });
  }
  return out;
}

/** Arguments as one short line, the way the model wrote them. */
export function argsLine(args: Record<string, unknown>): string {
  const parts = Object.entries(args).map(([k, v]) => {
    const s = typeof v === "string" ? JSON.stringify(v.length > 60 ? `${v.slice(0, 57)}…` : v) : JSON.stringify(v);
    return `${k}: ${s}`;
  });
  return parts.join(", ");
}

/** Every tool call of the run, in the order the model made them, with its state from the events. */
export function toolCalls(events: readonly DetEvent[]): ToolCall[] {
  const out: ToolCall[] = [];
  const at = new Map<string, number>();
  for (const ev of events) {
    if (ev.kind === "tool_start") {
      at.set(ev.data.id, out.length);
      out.push({ key: `${ev.data.id}:${out.length}`, tool: ev.data.tool, args: argsLine(ev.data.args), state: "running" });
    } else if (ev.kind === "tool_done" || ev.kind === "tool_failed") {
      const i = ev.data.id ? at.get(ev.data.id) : undefined;
      if (i !== undefined) out[i] = { ...out[i], state: ev.kind === "tool_done" ? "done" : "failed" };
    }
  }
  return out;
}

export function techGuide(view: MapView, inv: Investigation | null, events: readonly DetEvent[]): TechGuide {
  const layers: TechLayer[] = [];
  if (view.curtain) {
    layers.push(techLayer(view.curtain.left, "curtain-left", "Curtain, left"));
    layers.push(techLayer(view.curtain.right, "curtain-right", "Curtain, right"));
  } else if (view.evidence) layers.push(techLayer(view.evidence, "evidence", "Colored layer"));
  if (view.context && contextDrawn(view)) layers.push(techLayer(view.context, "context", "Underneath"));
  for (const fp of view.footprints) {
    layers.push({ key: `cell:${fp.source}`, role: "Data cell outline", title: fp.label, source: "",
      provider: Object.hasOwn(PROVIDERS, fp.source) ? PROVIDERS[fp.source] : providerOfSource(fp.source), resolution: fp.size, when: null });
  }
  const ran = new Set((inv?.scenes ?? []).filter((s) => s.tool?.state === "done").map((s) => s.tool!.tool));
  const methods: TechMethod[] = CORE_METHODS.map((m) => ({ ...m, used: ran.has(m.tool) }));
  return { layers, records: inv ? records(inv) : [], methods, calls: toolCalls(events) };
}
