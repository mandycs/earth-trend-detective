// Scene player (spec §5.5b): paces the investigation so each scene is readable, and catches up on live runs.
// Pure reducer: the caller owns the clock and passes `now` in.
import type { Scene } from "./scenes.ts";

export const DWELL_MS = {
  opening: 2500, note: 2500, context: 3500, evidence: 5000, ending: 0, error: 0, perStamp: 1500, catchUp: 1200,
} as const;

export interface PlayerState { index: number; enteredAt: number; paused: boolean; pinned: boolean }
export type PlayerAction =
  | { type: "tick"; now: number; scenes: readonly Scene[] }
  | { type: "pause" } | { type: "resume"; now: number }
  | { type: "goto"; index: number; now: number } // the user looks back: pins
  | { type: "live"; now: number; scenes: readonly Scene[] } // back to the newest scene, unpins
  | { type: "reset"; now: number };

export const INITIAL_PLAYER: PlayerState = { index: 0, enteredAt: 0, paused: false, pinned: false };

/** Backlog = scenes waiting after this one. From 3 on, hold only `catchUp` so live runs never fall behind. */
export function dwellMs(scene: Scene, backlog: number): number {
  if (backlog >= 3) return DWELL_MS.catchUp;
  return DWELL_MS[scene.kind] + DWELL_MS.perStamp * scene.stamps.length;
}

export function playerReducer(s: PlayerState, a: PlayerAction): PlayerState {
  switch (a.type) {
    case "tick": {
      if (s.paused || s.pinned) return s;
      const cur = a.scenes[s.index];
      if (!cur || !cur.complete || s.index + 1 >= a.scenes.length) return s;
      if (a.now - s.enteredAt < dwellMs(cur, a.scenes.length - 1 - s.index)) return s;
      return { ...s, index: s.index + 1, enteredAt: a.now };
    }
    case "pause":
      return s.paused ? s : { ...s, paused: true };
    case "resume":
      return { ...s, paused: false, enteredAt: a.now };
    case "goto": {
      // No upper clamp: the action carries no `scenes`. Consumers must clamp to `scenes.length - 1`;
      // a pinned index past the end holds until `live` or `reset`.
      const i = Number.isFinite(a.index) ? Math.max(0, Math.trunc(a.index)) : 0;
      return { ...s, index: i, enteredAt: a.now, pinned: true };
    }
    case "live":
      return { ...s, index: Math.max(0, a.scenes.length - 1), enteredAt: a.now, pinned: false };
    case "reset":
      return { ...INITIAL_PLAYER, enteredAt: a.now };
  }
}
