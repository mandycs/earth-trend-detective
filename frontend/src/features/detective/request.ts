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

export function boxFromCorners(
  a: { lat: number; lon: number },
  b: { lat: number; lon: number },
): { ok: true; bbox: Bbox } | { ok: false; message: string } {
  const lonA = wrapLon(a.lon);
  const lonB = wrapLon(b.lon);
  if (Math.abs(lonA - lonB) > 180) {
    return { ok: false, message: "Boxes can't cross the 180° line yet. Draw it on one side." };
  }
  const south = clampLat(Math.min(a.lat, b.lat));
  const north = clampLat(Math.max(a.lat, b.lat));
  const west = Math.min(lonA, lonB);
  const east = Math.max(lonA, lonB);
  if (north - south < MIN_SIDE || east - west < MIN_SIDE) {
    return { ok: false, message: "That box is too small. Drag a little wider." };
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
      ? { question: q, lat: target.lat, lon: target.lon }
      : target.kind === "box"
        ? { question: q, bbox: target.bbox }
        : { question: q, site_id: target.siteId };
  return {
    ...base,
    ...(opts.threadId ? { thread_id: opts.threadId } : {}),
    ...(opts.checkpointId ? { checkpoint_id: opts.checkpointId } : {}),
  };
}

const UNSAFE = /traceback|exception|error \d{3}/i;

export function messageForResponse(status: number, body: unknown): string {
  const detail = body && typeof body === "object" ? (body as { detail?: unknown }).detail : undefined;
  let text: string | null = null;
  if (typeof detail === "string") text = detail;
  else if (status === 422 && Array.isArray(detail)) {
    const msg = (detail[0] as { msg?: unknown } | undefined)?.msg;
    if (typeof msg === "string") text = msg.replace(/^Value error, /, "");
  }
  if (text && text.trim().length > 0) {
    if (!UNSAFE.test(text)) return text;
    return status >= 500 ? SERVER : GENERIC;
  }
  return status >= 500 ? SERVER : GENERIC;
}

const num = (n: number, d = 2): string => n.toFixed(d).replace("-", "−");

export function targetLabel(target: Target): string {
  if (target.kind === "case") return target.name;
  if (target.kind === "point") return `Point ${num(target.lat)}, ${num(target.lon)}`;
  const [w, s, e, n] = target.bbox;
  return `Box ${num(s)}–${num(n)} N, ${num(w)}–${num(e)} E`;
}
