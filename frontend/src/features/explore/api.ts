import { sitesSchema, sweepSchema } from "./schema";
import type { Site, SweepResponse } from "./types";

// The API's documented port (README). The old :8000 default reached another service on the demo machine
// and every call (the explore examples first) came back empty with no visible reason.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8765").replace(/\/$/, "");

const TIMEOUT_MS = 90_000;

/** Error whose message is safe to show to the user as-is. */
export class FriendlyError extends Error {}

const UNREACHABLE =
  "We couldn't reach the analysis service. Check your connection (or that the backend is running) and try again.";

function messageForStatus(status: number): string {
  if (status === 504) return "NASA took too long to answer. Wait a minute and try again.";
  if (status >= 500) return "Something went wrong while analysing this place. Try again, or pick a different point.";
  return "We couldn't analyse this place. Pick a different point on the map and try again.";
}

async function readDetail(res: Response): Promise<string | null> {
  try {
    const body: unknown = await res.json();
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      // Backend sends plain-English strings; anything else (validation arrays) is not shown.
      if (typeof detail === "string" && detail.length > 0 && !/traceback/i.test(detail)) return detail;
    }
  } catch {
    /* not JSON */
  }
  return null;
}

export async function fetchSweep(lat: number, lon: number, signal: AbortSignal): Promise<SweepResponse> {
  const params = new URLSearchParams({
    lat: lat.toFixed(4),
    lon: lon.toFixed(4),
    include_series: "true",
  });
  const timeout = AbortSignal.timeout(TIMEOUT_MS);
  const combined = AbortSignal.any([signal, timeout]);
  let res: Response;
  try {
    res = await fetch(`${API_URL}/sweep?${params}`, { signal: combined });
  } catch (err) {
    if (signal.aborted) throw err;
    if (timeout.aborted) throw new FriendlyError("The analysis took too long. Wait a minute and try again.");
    throw new FriendlyError(UNREACHABLE);
  }
  if (!res.ok) {
    throw new FriendlyError((await readDetail(res)) ?? messageForStatus(res.status));
  }
  const parsed = sweepSchema.safeParse(await res.json().catch(() => null));
  if (!parsed.success) {
    throw new FriendlyError("The analysis came back incomplete. Try again in a moment.");
  }
  return parsed.data;
}

/**
 * The known cases for the example buttons. No list means no buttons, never an error on screen, but the
 * reason goes to the console: a blocked origin (CORS) or a wrong NEXT_PUBLIC_API_URL looks exactly like
 * an empty list otherwise.
 */
export async function fetchSites(signal: AbortSignal): Promise<Site[]> {
  const url = `${API_URL}/sites`;
  try {
    const res = await fetch(url, { signal });
    if (!res.ok) {
      console.warn(`Example cases not loaded: ${url} answered ${res.status}.`);
      return [];
    }
    const parsed = sitesSchema.safeParse(await res.json());
    if (!parsed.success) console.warn(`Example cases not loaded: ${url} sent an unexpected list.`);
    return parsed.success ? parsed.data : [];
  } catch (err) {
    if (!signal.aborted) {
      console.warn(`Example cases not loaded: ${url} could not be reached (check NEXT_PUBLIC_API_URL and the API's CORS origins).`, err);
    }
    return [];
  }
}
