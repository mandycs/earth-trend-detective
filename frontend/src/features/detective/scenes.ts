// Groups the detective event stream into scenes (spec §5.5b): a question line from `thinking`, one tool,
// its result, the map ops and board stamps that followed. Pure: fresh output, input never mutated.
import type { AnswerEvent, BoardEvent, DetEvent, DoneEvent, MapOp, PlaceEvent } from "./events.ts";
import type { StampBeat } from "./board.ts";
import { stampsBetween } from "./board.ts";

export type SceneKind = "opening" | "evidence" | "context" | "note" | "ending" | "error";
export type ToolState = "running" | "done" | "failed" | "unfinished";
export interface SceneTool {
  id: string; tool: string; args: Record<string, unknown>; state: ToolState; summary: string | null;
  result: Record<string, unknown> | null; evidenceId: string | null; reason: string | null;
}
export interface Scene {
  key: string; kind: SceneKind; question: string | null; tool: SceneTool | null; mapOps: MapOp[];
  stamps: StampBeat[]; note: string | null; complete: boolean;
}
export interface Investigation {
  place: PlaceEvent | null; scenes: Scene[]; board: BoardEvent | null; answer: AnswerEvent | null;
  done: DoneEvent | null; error: string | null; finished: boolean;
}

/** Tools that only move the map or the board: they never get a scene of their own. */
export const MAP_TOOLS: ReadonlySet<string> = new Set([
  "show_layer", "set_year", "show_before_after", "fly_to", "show_footprint", "update_board",
]);
/** Tools that describe the place rather than test a variable. */
export const CONTEXT_TOOLS: ReadonlySet<string> = new Set([
  "profile_place", "list_variables", "land_cover_change", "satellite_picture", "solved_case",
]);

const scene = (key: string, kind: SceneKind, extra: Partial<Scene> = {}): Scene => ({
  key, kind, question: null, tool: null, mapOps: [], stamps: [], note: null, complete: true, ...extra,
});

export function groupScenes(events: readonly DetEvent[], opts: { ended?: boolean } = {}): Investigation {
  // Local, freshly built state; nothing from `events` is written to.
  const scenes: Scene[] = [];
  let place: PlaceEvent | null = null;
  let board: BoardEvent | null = null;
  let answer: AnswerEvent | null = null;
  let done: DoneEvent | null = null;
  let error: string | null = null;
  let pending: string | null = null;
  let notes = 0;

  const last = (): Scene | undefined => scenes[scenes.length - 1];
  const findTool = (id: string): Scene | undefined => {
    for (let i = scenes.length - 1; i >= 0; i--) if (scenes[i].tool?.id === id) return scenes[i];
    return undefined;
  };
  const note = (extra: Partial<Scene>): void => {
    notes += 1;
    scenes.push(scene(`note-${notes}`, "note", extra));
  };

  for (const ev of events) {
    switch (ev.kind) {
      case "place":
        place = ev.data;
        scenes.push(scene("opening", "opening"));
        break;
      case "thinking":
        pending = ev.data.text;
        break;
      case "tool_start": {
        const { id, tool, args } = ev.data;
        if (MAP_TOOLS.has(tool)) {
          if (pending !== null) note({ question: pending });
        } else {
          scenes.push(scene(id, CONTEXT_TOOLS.has(tool) ? "context" : "evidence", {
            question: pending,
            tool: { id, tool, args, state: "running", summary: null, result: null, evidenceId: null, reason: null },
          }));
        }
        pending = null;
        break;
      }
      case "tool_done": {
        const s = findTool(ev.data.id);
        if (s?.tool) {
          s.tool = { ...s.tool, state: "done", summary: ev.data.summary, result: ev.data.result, evidenceId: ev.data.evidence_id };
        }
        break;
      }
      case "tool_failed": {
        if (ev.data.id === null) {
          note({ note: ev.data.reason });
          break;
        }
        const s = findTool(ev.data.id);
        if (s?.tool) s.tool = { ...s.tool, state: "failed", reason: ev.data.reason };
        break;
      }
      case "map": {
        const s = last();
        if (s) s.mapOps = [...s.mapOps, ev.data];
        break;
      }
      case "board": {
        const s = last();
        if (s) s.stamps = [...s.stamps, ...stampsBetween(board, ev.data)];
        board = ev.data;
        break;
      }
      case "answer":
        answer = ev.data;
        pending = null;
        scenes.push(scene("ending", "ending"));
        break;
      case "done":
        done = ev.data;
        break;
      case "error":
        error = ev.data.message;
        scenes.push(scene("error", "error", { note: ev.data.message }));
        break;
    }
  }

  const finished = done !== null || error !== null;
  const stopped = finished || opts.ended === true;
  const out = scenes.map((s): Scene => {
    if (!s.tool || s.tool.state !== "running") return { ...s, complete: true };
    if (stopped) return { ...s, tool: { ...s.tool, state: "unfinished" }, complete: true };
    return { ...s, complete: false };
  });
  return { place, scenes: out, board, answer, done, error, finished };
}
