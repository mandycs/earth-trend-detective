// Copy and small decisions for the reading column (Task 13). Pure: no DOM, no React.
// Nothing here derives a figure for printing; numbers are only passed through or formatted.
import type { AnswerEvent, DoneEvent } from "./events.ts";
import type { RunStatus } from "./runState.ts";
import type { Target } from "./request.ts";
import type { Scene, ToolState } from "./scenes.ts";

export const TOOL_LABELS: Readonly<Record<string, string>> = {
  get_series: "Fetching the record",
  trend_test: "Is it real?",
  climate_residual: "Is it the climate?",
  correlate: "Do they move together?",
  compare: "Same thing, two places",
  land_cover_change: "Has the land changed?",
  satellite_picture: "Then and now",
  profile_place: "What kind of place is this?",
  list_variables: "What can be measured here?",
  years_needed: "How many years would it take?",
  years_needed_for: "How many years would it take?", // the backend's real tool name
  solved_case: "A solved case",
};
export const OTHER_TOOL = "Checking the data";

/** A plain label for a tool, never its raw name. */
export function toolLabel(tool: string): string {
  return Object.hasOwn(TOOL_LABELS, tool) ? TOOL_LABELS[tool] : OTHER_TOOL;
}

export const NO_TARGET_HINT = "Click a point or draw a box on the globe, then ask in plain words.";
export const QUESTION_PLACEHOLDER = "Is it getting hotter here? Is the water going down?";
export const QUESTION_MAX = 400;

/** Why the primary button is disabled, or null when it can be pressed. */
export function askBlocker(target: Target | null, question: string): string | null {
  if (!target) return "Pick a place first";
  if (!question.trim()) return "Write a question";
  return null;
}

export const isActiveRun = (s: RunStatus): boolean => s === "connecting" || s === "streaming";

/** "15 Nov 2026" from an ISO timestamp, in UTC; the raw text when it does not parse. */
export function recordedDate(startedAt: string): string {
  const t = Date.parse(startedAt);
  if (!startedAt || Number.isNaN(t)) return startedAt;
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(t);
}

export function replayLine(startedAt: string | null | undefined): string {
  const d = startedAt ? recordedDate(startedAt) : "";
  return d ? `Replay of a recorded run · recorded ${d}` : "Replay of a recorded run";
}

export function forkLine(step: number, summary: string): string {
  return `Re-running from step ${step}: ${summary}`;
}

/** The check line under the answer. Only the tests part goes when `done` is missing. */
export function checkLine(answer: AnswerEvent, done: DoneEvent | null): string {
  const head = answer.checked ? "✓ every figure checked" : "Not every figure could be checked";
  return done ? `${head} · ${done.n_tests} tests run` : head;
}

export const CLUE_LINE = "A clue, not proof.";
export const TEMPLATE_LINE = "The plain summary, written from the results without the language model.";

export function notMeasuredLine(label: string, reason: string | null): string {
  return reason ? `${label} — ${reason}` : label;
}

export type StepIcon = "✓" | "…" | "✕";

const ICON_BY_STATE: Record<ToolState, StepIcon> = { done: "✓", running: "…", failed: "✕", unfinished: "✕" };

/** One row of the step list: icon by state and a plain label. */
export function stepRow(scene: Scene): { icon: StepIcon; label: string; state: string } {
  if (scene.tool) {
    const st = scene.tool.state;
    const label = toolLabel(scene.tool.tool);
    const state = st === "done" ? "done" : st === "running" ? "running" : st === "failed" ? "could not check" : "did not finish";
    return { icon: ICON_BY_STATE[st], label, state };
  }
  switch (scene.kind) {
    case "opening": return { icon: "✓", label: "The place", state: "done" };
    case "ending": return { icon: "✓", label: "The answer", state: "done" };
    case "error": return { icon: "✕", label: "Stopped by an error", state: "failed" };
    default: return { icon: "✓", label: "A note", state: "done" };
  }
}

export function boardToggleLabel(n: number): string {
  return `Case board (${n} ${n === 1 ? "suspect" : "suspects"})`;
}

/** The history can be fetched only for a finished live run on a known thread. */
export function historyEnabled(status: RunStatus, mode: "live" | "replay", threadId: string | null): boolean {
  return status === "finished" && mode === "live" && !!threadId;
}

export interface CompareSide { place: string; years: string | null; testId: string | null; raw: Record<string, unknown> }

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const coord = (n: number): string => n.toFixed(2).replace("-", "−");

/** Both sides of a `compare` result, as place and years lines. Null when the result has no sides. */
export function compareSides(result: Record<string, unknown> | null): [CompareSide, CompareSide] | null {
  if (!result) return null;
  const side = (v: unknown): CompareSide | null => {
    if (!isObj(v)) return null;
    const p = isObj(v.place) ? v.place : null;
    const place = p && isNum(p.lat) && isNum(p.lon) ? `${coord(p.lat)}, ${coord(p.lon)}` : "This place";
    const y = Array.isArray(v.years) && v.years.length === 2 && v.years.every(isNum) ? `${v.years[0]}–${v.years[1]}` : null;
    return { place, years: y, testId: typeof v.test_id === "string" ? v.test_id : null, raw: v };
  };
  const a = side(result.a);
  const b = side(result.b);
  return a && b ? [a, b] : null;
}
