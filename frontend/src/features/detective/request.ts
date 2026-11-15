import type { Bbox } from "./events.ts";

export type Target =
  | { kind: "point"; lat: number; lon: number }
  | { kind: "box"; bbox: Bbox }
  | { kind: "case"; siteId: string; name: string; bbox: Bbox };

export type DetectiveBody = { question: string; thread_id?: string; checkpoint_id?: string } & (
  | { lat: number; lon: number }
  | { bbox: Bbox }
  | { site_id: string }
);

const MAX_LAT = 85;
const MIN_SIDE = 0.01;
const GENERIC = "This place or question could not be investigated. Pick another point and try again.";
const SERVER = "The investigation failed on the server. Try again in a moment.";

export function wrapLon(lon: number): number {
  return ((((lon + 180) % 360) + 360) % 360) - 180;
}

const clampLat = (lat: number): number => Math.max(-MAX_LAT, Math.min(MAX_LAT, lat));

/** Like `wrapLon`, but an east edge on the 180° line stays at +180 (a box from 170 to 180 is not a crossing). */
function cornerLon(lon: number): number {
  const w = wrapLon(lon);
  return w === -180 && lon > 0 ? 180 : w;
}

export function boxFromCorners(
  a: { lat: number; lon: number },
  b: { lat: number; lon: number },
): { ok: true; bbox: Bbox } | { ok: false; message: string } {
  const lonA = cornerLon(a.lon);
  const lonB = cornerLon(b.lon);
  if (Math.abs(lonA - lonB) > 180) {
    return { ok: false, message: "Boxes can't cross the 180° line yet. Draw the box on one side of it." };
  }
  const south = clampLat(Math.min(a.lat, b.lat));
  const north = clampLat(Math.max(a.lat, b.lat));
  const west = Math.min(lonA, lonB);
  const east = Math.max(lonA, lonB);
  if (north - south < MIN_SIDE || east - west < MIN_SIDE) {
    return { ok: false, message: "That box is too small. Pick two corners farther apart." };
  }
  return { ok: true, bbox: [west, south, east, north] };
}

export function requestBody(
  target: Target,
  question: string,
  opts: { threadId?: string | null; checkpointId?: string | null } = {},
): DetectiveBody {
  const q = question.trim();
  const base =
    target.kind === "point"
      ? { question: q, lat: target.lat, lon: wrapLon(target.lon) }
      : target.kind === "box"
        ? { question: q, bbox: target.bbox }
        : { question: q, site_id: target.siteId };
  return {
    ...base,
    ...(opts.threadId ? { thread_id: opts.threadId } : {}),
    ...(opts.checkpointId ? { checkpoint_id: opts.checkpointId } : {}),
  };
}

// Words that mean the text is a server internal, not a sentence for the person: stack traces, exceptions, paths,
// URLs, OS errors and raw HTTP codes. A multi-line or long text is treated the same way.
// A path is "/word/" (two slashes around a name), so "km/h" or "lat/lon" in a sentence survive.
const UNSAFE = /traceback|exception|error \d{3}|http \d{3}|errno|:\/\/|\/[a-z0-9_.-]+\/|\n|\r/i;
const MAX_MESSAGE = 200;

const safe = (text: string): boolean => text.trim().length > 0 && text.length <= MAX_MESSAGE && !UNSAFE.test(text);

export function messageForResponse(status: number, body: unknown): string {
  const fallback = status >= 500 ? SERVER : GENERIC;
  const detail = body && typeof body === "object" ? (body as { detail?: unknown }).detail : undefined;
  let text: string | null = null;
  if (typeof detail === "string") text = detail;
  else if (status === 422 && Array.isArray(detail)) {
    // Only our own validators speak to the person ("Value error, …"); Pydantic's structural messages
    // ("Field required", "Input should be a valid number") describe the request, not the place.
    const msg = (detail[0] as { msg?: unknown } | undefined)?.msg;
    if (typeof msg === "string" && msg.startsWith("Value error, ")) text = msg.slice("Value error, ".length);
  }
  return text !== null && safe(text) ? text.trim() : fallback;
}

const num = (n: number, d = 2): string => {
  const t = n.toFixed(d);
  // -0.001 rounds to "-0.00": a sign on zero is noise.
  return (Number(t) === 0 ? t.replace("-", "") : t).replace("-", "−");
};

export function targetLabel(target: Target): string {
  if (target.kind === "case") return target.name;
  if (target.kind === "point") return `Point ${num(target.lat)}, ${num(target.lon)}`;
  const [w, s, e, n] = target.bbox;
  return `Box ${num(s)}–${num(n)} N, ${num(w)}–${num(e)} E`;
}
