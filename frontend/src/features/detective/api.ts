// Browser-only fetch wrappers for the detective. Not unit-tested (they need fetch and a backend).
import { API_URL, FriendlyError } from "../explore/api";
import { parseSseMessage } from "./events.ts";
import type { DetEvent } from "./events.ts";
import { createSseParser } from "./sse.ts";
import { messageForResponse } from "./request.ts";
import type { DetectiveBody } from "./request.ts";
import type { CaseLayerRow } from "./map/types.ts";
import { caseRowsFrom } from "./map/mapView.ts";
import type { Recording } from "./replay.ts";

const UNREACHABLE =
  "We couldn't reach the detective. Check your internet connection and try again.";

export interface HistoryStep {
  checkpoint_id: string;
  step: number;
  kind: string;
  tool: string | null;
  summary: string;
  n_tests: number;
  created_at: string;
}

async function readBody(res: Response): Promise<unknown> {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

/** A body that is not the JSON it should be is a failure in words, never a raw SyntaxError. */
async function json<T>(res: Response, failure: string): Promise<T> {
  try {
    return (await res.json()) as T;
  } catch {
    throw new FriendlyError(failure);
  }
}

async function send(url: string, init: RequestInit, signal: AbortSignal): Promise<Response> {
  try {
    return await fetch(url, { ...init, signal });
  } catch (e) {
    if (signal.aborted || (e instanceof DOMException && e.name === "AbortError")) throw e;
    throw new FriendlyError(UNREACHABLE);
  }
}

export async function streamDetective(
  body: DetectiveBody,
  onEvent: (e: DetEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const res = await send(
    `${API_URL}/detective`,
    {
      method: "POST",
      headers: { "content-type": "application/json", accept: "text/event-stream" },
      body: JSON.stringify(body),
    },
    signal,
  );
  if (!res.ok) throw new FriendlyError(messageForResponse(res.status, await readBody(res)));
  if (!res.body) throw new FriendlyError(UNREACHABLE);

  const parser = createSseParser((m) => {
    const e = parseSseMessage(m);
    if (e) onEvent(e);
  });
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      parser.push(decoder.decode(value, { stream: true }));
    }
    parser.push(decoder.decode());
    parser.end();
  } catch (e) {
    if (signal.aborted || (e instanceof DOMException && e.name === "AbortError")) throw e;
    // The stream broke mid-way: the reducer turns an end without `done` into "cut".
    parser.end();
  }
}

export async function fetchHistory(threadId: string, signal: AbortSignal): Promise<HistoryStep[]> {
  const res = await send(`${API_URL}/detective/${encodeURIComponent(threadId)}/history`, {}, signal);
  if (!res.ok) throw new FriendlyError(messageForResponse(res.status, await readBody(res)));
  return json<HistoryStep[]>(res, "The steps of this investigation could not be read. Try again in a moment.");
}

export async function fetchRecording(name: string, signal: AbortSignal): Promise<Recording> {
  const res = await send(`/recordings/${encodeURIComponent(name)}.json`, {}, signal);
  if (!res.ok) throw new FriendlyError("This recording is not available.");
  return json<Recording>(res, "This recording is not available.");
}

export async function fetchCaseLayers(siteId: string, signal: AbortSignal): Promise<Record<string, CaseLayerRow>> {
  const res = await send(`/sites/${encodeURIComponent(siteId)}/layers.json`, {}, signal);
  if (!res.ok) throw new FriendlyError("This case has no layers.");
  return caseRowsFrom(await json<unknown>(res, "This case has no layers."));
}
