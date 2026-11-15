import type { BoardEvent, SuspectStatus } from "./events.ts";
import type { Verdict, Direction } from "../../story/types";

export interface StampBeat {
  suspectId: string;
  label: string;
  status: Exclude<SuspectStatus, "open">;
  downgraded: string | null;
}

export const STATUS_WORDS: Record<SuspectStatus, { icon: string; text: string; meaning: string }> = {
  supported: { icon: "✓", text: "SUPPORTED", meaning: "Its evidence still holds after allowing for all the tests we ran." },
  ruled_out: { icon: "✕", text: "RULED OUT", meaning: "Tested with enough years and no clear change." },
  hint: { icon: "~", text: "HINT", meaning: "Points this way, but not strong enough yet." },
  trend_only: { icon: "◐", text: "TREND REAL · NOT LINKED", meaning: "Its own trend is real, but no test links it to the change." },
  open: { icon: "○", text: "OPEN", meaning: "Not tested yet." },
};

/** Suspects whose stamped status is new or changed between two boards (never "open"). */
export function stampsBetween(prev: BoardEvent | null, next: BoardEvent): StampBeat[] {
  const before = new Map((prev?.suspects ?? []).map((x) => [x.id, x.status]));
  const out: StampBeat[] = [];
  for (const sp of next.suspects) {
    if (sp.status === "open") continue;
    if (before.get(sp.id) === sp.status) continue;
    out.push({ suspectId: sp.id, label: sp.label, status: sp.status, downgraded: sp.downgraded });
  }
  return out;
}

const VERDICTS: readonly string[] = ["real", "likely", "unknown"];
const DIRECTIONS: readonly string[] = ["up", "down", "flat"];

export function verdictFor(
  testId: string | null | undefined,
  board: BoardEvent | null,
  fallback?: { verdict?: unknown; direction?: unknown },
): { verdict: Verdict; direction: Direction } | null {
  if (testId && board && Object.hasOwn(board.verdicts, testId)) return board.verdicts[testId];
  const v = fallback?.verdict;
  const d = fallback?.direction;
  if (typeof v === "string" && typeof d === "string" && VERDICTS.includes(v) && DIRECTIONS.includes(d)) {
    return { verdict: v as Verdict, direction: d as Direction };
  }
  return null;
}
