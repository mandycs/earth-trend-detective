import type { DetEvent } from "./events.ts";

export type RunStatus = "idle" | "connecting" | "streaming" | "finished" | "stopped" | "cut" | "failed";

export interface RunState {
  status: RunStatus;
  mode: "live" | "replay";
  events: DetEvent[];
  message: string | null;
  threadId: string | null;
}

export type RunAction =
  | { type: "start"; mode: "live" | "replay"; keepThread: boolean }
  | { type: "event"; event: DetEvent }
  | { type: "end" }
  | { type: "stop" }
  | { type: "fail"; message: string }
  | { type: "reset" };

export const CUT_MESSAGE = "The connection closed before the investigation finished. The steps so far are kept. Try again.";
export const STOP_MESSAGE = "You stopped the investigation. The steps so far are kept.";

export const IDLE_RUN: RunState = { status: "idle", mode: "live", events: [], message: null, threadId: null };

const isActive = (s: RunState): boolean => s.status === "connecting" || s.status === "streaming";

export function runReducer(s: RunState, a: RunAction): RunState {
  switch (a.type) {
    case "start":
      return {
        status: "connecting",
        mode: a.mode,
        events: [],
        message: null,
        threadId: a.keepThread ? s.threadId : null,
      };
    case "event": {
      if (!isActive(s)) return s;
      const e = a.event;
      const threadId = e.kind === "place" || e.kind === "done" ? e.data.thread_id : s.threadId;
      return { ...s, status: "streaming", events: [...s.events, e], threadId };
    }
    case "end": {
      if (!isActive(s)) return s;
      const closed = s.events.some((e) => e.kind === "done" || e.kind === "error");
      return closed ? { ...s, status: "finished", message: null } : { ...s, status: "cut", message: CUT_MESSAGE };
    }
    case "stop":
      return isActive(s) ? { ...s, status: "stopped", message: STOP_MESSAGE } : s;
    case "fail":
      return { ...s, status: "failed", message: a.message };
    case "reset":
      return IDLE_RUN;
  }
}
