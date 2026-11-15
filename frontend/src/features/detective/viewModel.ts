// Small decisions for the /detective screen (Task 14). Pure: no DOM, no React.
// Nothing here derives a figure for printing; the coordinates typed by the user are passed through.
import type { AnswerEvent, Bbox, DetEvent, DoneEvent } from "./events.ts";
import type { RunStatus } from "./runState.ts";
import type { Target } from "./request.ts";
import { wrapLon } from "./request.ts";

export const COORDS_HINT = "Or type a place as lat, lon";
export const COORDS_PLACEHOLDER = "36.87, -4.17";
const COORDS_BAD = "Type two numbers: latitude, then longitude. For example 36.87, -4.17.";
const LAT_BAD = "Latitude goes from -90 to 90.";
const LON_BAD = "Longitude goes from -180 to 180.";

const NUM = String.raw`[-+]?(?:\d+(?:\.\d*)?|\.\d+)`;
const PAIR = new RegExp(String.raw`^\s*(${NUM})\s*(?:[,;]\s*|\s+)(${NUM})\s*$`);

/** "36.87, -4.17" (comma, semicolon or space; a real minus sign is accepted) → a point target. */
export function parseLatLon(text: string): { ok: true; target: Target } | { ok: false; message: string } {
  const m = PAIR.exec(text.replace(/[−–]/g, "-"));
  if (!m) return { ok: false, message: COORDS_BAD };
  const lat = Number(m[1]);
  const lon = Number(m[2]);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return { ok: false, message: COORDS_BAD };
  if (lat < -90 || lat > 90) return { ok: false, message: LAT_BAD };
  if (lon < -180 || lon > 180) return { ok: false, message: LON_BAD };
  return { ok: true, target: { kind: "point", lat, lon: wrapped(lon) } };
}

/** `wrapLon` only when needed: the modulo arithmetic adds float noise (-4.17 → -4.169999…) to in-range values. */
const wrapped = (lon: number): number => (lon >= -180 && lon < 180 ? lon : wrapLon(lon));

/** The target as sent: a point's longitude wrapped into [-180, 180). */
export function wrapTarget(target: Target): Target {
  return target.kind === "point" ? { ...target, lon: wrapped(target.lon) } : target;
}

export interface TurnOutcome { answer: AnswerEvent | null; done: DoneEvent | null }

/**
 * The answer and `done` of every turn, keyed by the ending scene key (`ending-<turn>`), because an ending scene
 * does not carry its answer and `groupScenes` keeps only the newest turn's. Turns are counted from `place`
 * events the same way `groupScenes` counts them (first turn = 0).
 */
export function turnOutcomes(events: readonly DetEvent[]): Record<string, TurnOutcome> {
  const out: Record<string, TurnOutcome> = {};
  let places = 0;
  let turn = 0;
  for (const ev of events) {
    if (ev.kind === "place") {
      turn = places;
      places += 1;
    } else if (ev.kind === "answer") {
      out[`ending-${turn}`] = { answer: ev.data, done: out[`ending-${turn}`]?.done ?? null };
    } else if (ev.kind === "done") {
      const key = `ending-${turn}`;
      out[key] = { answer: out[key]?.answer ?? null, done: ev.data };
    }
  }
  return out;
}

/** The number of turns so far (place events), used to give each turn's question box a fresh key. */
export function turnCount(events: readonly DetEvent[]): number {
  return events.reduce((n, e) => (e.kind === "place" ? n + 1 : n), 0);
}

/** Today in the viewer's own time zone, as YYYY-MM-DD. */
export function localDate(d: Date): string {
  const p = (n: number): string => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

// ---- focus (fix round 1) ----

export type FocusTarget = "stop" | "answer" | "scene";

const ACTIVE: readonly RunStatus[] = ["connecting", "streaming"];
const OVER: readonly RunStatus[] = ["finished", "stopped", "cut", "failed"];

/**
 * Where keyboard focus goes on a run status change: to Stop when a live run starts, and to the answer (or the
 * current scene when there is none) when a run ends. Null: focus stays where it is.
 */
export function focusTargetFor(
  prev: RunStatus, next: RunStatus, mode: "live" | "replay", hasAnswer: boolean,
): FocusTarget | null {
  const was = ACTIVE.includes(prev);
  if (!was && ACTIVE.includes(next)) return mode === "live" ? "stop" : null;
  if (was && OVER.includes(next)) return hasAnswer ? "answer" : "scene";
  return null;
}

export const ANSWER_READY = "The answer is ready.";

// ---- forks (fix round 1) ----

/**
 * The turn a history step belongs to: the number of answers given before it on the thread (steps grow along a
 * branch; an answer step closes its turn). Forks of forks share the list, so this is a best reading, never
 * printed.
 */
export function forkTurn(steps: readonly HistoryStepLike[], step: HistoryStepLike): number {
  return steps.filter((s) => s.kind === "answer" && s.step < step.step).length;
}
export interface HistoryStepLike { step: number; kind: string }

/** The events of turns 0..`turn` (inclusive): everything before the place event that opens turn `turn + 1`. */
export function trimToTurn(events: readonly DetEvent[], turn: number): DetEvent[] {
  let places = 0;
  const out: DetEvent[] = [];
  for (const e of events) {
    if (e.kind === "place") {
      if (places > turn) break;
      places += 1;
    }
    out.push(e);
  }
  return out;
}

// ---- camera before a run (fix round 1) ----

const POINT_HALF = 0.25;

/**
 * Where the map looks before a run, so a preselected, typed or chosen place is visible. Seqs are negative so they
 * never collide with a run's own camera seqs (which start at 1).
 */
export function previewCamera(target: Target, seq: number): { bbox: Bbox; pitch: number; bearing: number; seq: number } {
  const bbox: Bbox =
    target.kind === "point"
      ? [target.lon - POINT_HALF, target.lat - POINT_HALF, target.lon + POINT_HALF, target.lat + POINT_HALF]
      : [...target.bbox] as Bbox;
  return { bbox, pitch: 0, bearing: 0, seq: -Math.abs(seq) };
}
