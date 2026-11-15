import { parseEvent } from "./events.ts";
import type { Bbox, DetEvent } from "./events.ts";
import type { Target } from "./request.ts";

export const RECORDING_NAME = /^[a-z0-9][a-z0-9_-]{0,63}$/;

export interface Recording {
  question: string;
  request: Record<string, unknown>;
  started_at: string;
  events: { t_ms: number; event: string; data: unknown }[];
}
export interface RecordingChip { name: string; question: string; started_at: string }

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

export function parseRecording(raw: unknown): Recording | null {
  if (!isObj(raw) || typeof raw.question !== "string" || !Array.isArray(raw.events)) return null;
  const events: Recording["events"] = [];
  for (const e of raw.events) {
    if (!isObj(e) || typeof e.event !== "string") return null;
    events.push({ t_ms: typeof e.t_ms === "number" && Number.isFinite(e.t_ms) ? e.t_ms : 0, event: e.event, data: e.data });
  }
  return {
    question: raw.question,
    request: isObj(raw.request) ? raw.request : {},
    started_at: typeof raw.started_at === "string" ? raw.started_at : "",
    events,
  };
}

/** Real timing, with each gap capped so long tool waits do not stall the demo. */
export function replaySchedule(rec: Recording, maxGapMs = 6000): { atMs: number; event: DetEvent }[] {
  const out: { atMs: number; event: DetEvent }[] = [];
  let prevT: number | null = null;
  let at = 0;
  for (const e of rec.events) {
    const ev = parseEvent(e.event, e.data);
    if (!ev) continue;
    if (prevT !== null) at += Math.min(Math.max(e.t_ms - prevT, 0), maxGapMs);
    prevT = prevT === null ? e.t_ms : Math.max(prevT, e.t_ms);
    out.push({ atMs: at, event: ev });
  }
  return out;
}

const WORLD: Bbox = [-180, -90, 180, 90];
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

export function targetFromRequest(req: Record<string, unknown>): Target | null {
  const bbox = Array.isArray(req.bbox) && req.bbox.length === 4 && req.bbox.every(isNum) ? (req.bbox as Bbox) : null;
  if (typeof req.site_id === "string" && req.site_id) {
    // Name and bbox are not in the request; the place event that follows carries the real ones.
    return { kind: "case", siteId: req.site_id, name: req.site_id, bbox: bbox ?? WORLD };
  }
  if (bbox) return { kind: "box", bbox };
  if (isNum(req.lat) && isNum(req.lon)) return { kind: "point", lat: req.lat, lon: req.lon };
  return null;
}
