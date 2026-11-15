import { z } from "zod";
import type { Verdict, Direction } from "../../story/types";
import type { SseMessage } from "./sse.ts";

export type Bbox = [number, number, number, number]; // west, south, east, north

export interface PlaceEvent {
  thread_id: string; follow_up: boolean; forked_from: string | null; id: string; name: string;
  lat: number; lon: number; bbox: Bbox; tags: string[]; site_id: string | null; years: [number, number] | null;
}
export interface ToolStart { id: string; tool: string; args: Record<string, unknown> }
export interface ToolDone { id: string; tool: string; summary: string; result: Record<string, unknown>; evidence_id: string | null }
export interface ToolFailed { id: string | null; tool: string; reason: string }
export type MapOp =
  | { op: "show_layer"; layer_id: string; date: string | null; year: number | null; opacity: number }
  | { op: "set_year"; year: number }
  | { op: "show_before_after"; layer_id: string; year_a: number; year_b: number; before_url: string | null; after_url: string | null; bbox: Bbox | null }
  | { op: "fly_to"; bbox: Bbox; pitch: number; bearing: number }
  | { op: "show_footprint"; source: string; label: string; size: string; bbox: Bbox; approximate: true };
export type SuspectStatus = "open" | "supported" | "hint" | "ruled_out" | "trend_only";
export interface Suspect { id: string; label: string; status: SuspectStatus; evidence: string[]; note: string; downgraded: string | null }
export interface BoardEvent { suspects: Suspect[]; n_tests: number; verdicts: Record<string, { verdict: Verdict; direction: Direction }> }
export interface NotMeasured { label: string; reason: string | null }
export interface AnswerEvent { text: string; checked: boolean; figures: string[]; source: string; not_measured: NotMeasured[] }
export interface DoneEvent { thread_id: string; n_tests: number; n_tests_branch: number | null; n_tool_calls: number | null }
export type DetEvent =
  | { kind: "place"; data: PlaceEvent } | { kind: "thinking"; data: { text: string } }
  | { kind: "tool_start"; data: ToolStart } | { kind: "tool_done"; data: ToolDone } | { kind: "tool_failed"; data: ToolFailed }
  | { kind: "map"; data: MapOp } | { kind: "board"; data: BoardEvent } | { kind: "answer"; data: AnswerEvent }
  | { kind: "done"; data: DoneEvent } | { kind: "error"; data: { message: string } };

const num = z.number();
const bbox = z.tuple([num, num, num, num]);
const str = z.string();
const strArr = z.array(str);
const rec = z.record(z.string(), z.unknown());
const nullStr = str.nullable().catch(null);
const nullNum = num.nullable().catch(null);

const place = z.object({
  thread_id: str,
  follow_up: z.boolean().catch(false),
  forked_from: nullStr,
  id: str,
  name: str,
  lat: num,
  lon: num,
  bbox,
  tags: strArr.catch([]),
  site_id: nullStr,
  years: z.tuple([num, num]).nullable().catch(null),
});

const toolStart = z.object({ id: str, tool: str, args: rec.catch({}) });
const toolDone = z.object({
  id: str, tool: str, summary: str.catch(""), result: rec.catch({}), evidence_id: nullStr,
});
const toolFailed = z.object({ id: nullStr, tool: str, reason: str.catch("") });

const mapOp = z.discriminatedUnion("op", [
  z.object({
    op: z.literal("show_layer"), layer_id: str, date: nullStr, year: nullNum, opacity: num.catch(0.8),
  }),
  z.object({ op: z.literal("set_year"), year: num }),
  z.object({
    op: z.literal("show_before_after"), layer_id: str, year_a: num, year_b: num,
    before_url: nullStr, after_url: nullStr, bbox: bbox.nullable().catch(null),
  }),
  z.object({ op: z.literal("fly_to"), bbox, pitch: num.catch(55), bearing: num.catch(0) }),
  z.object({
    op: z.literal("show_footprint"), source: str, label: str, size: str, bbox,
    approximate: z.unknown().transform((): true => true),
  }),
]);

const suspect = z.object({
  id: str,
  label: str,
  status: z.enum(["open", "supported", "hint", "ruled_out", "trend_only"]).catch("open"), // unknown → open
  evidence: strArr.catch([]),
  note: str.catch(""),
  downgraded: nullStr,
});
const verdictEntry = z.object({
  verdict: z.enum(["real", "likely", "unknown"]),
  direction: z.enum(["up", "down", "flat"]),
});
const verdicts = z
  .record(z.string(), z.unknown())
  .catch({})
  .transform((r) => {
    const out: Record<string, { verdict: Verdict; direction: Direction }> = {};
    for (const [k, v] of Object.entries(r)) {
      const p = verdictEntry.safeParse(v);
      if (p.success) out[k] = p.data;
    }
    return out;
  });
const board = z.object({ suspects: z.array(suspect), n_tests: num.catch(0), verdicts });

const notMeasuredItem = z.union([
  str.transform((label): NotMeasured => ({ label, reason: null })),
  z
    .object({ label: str.optional(), name: str.optional(), var_id: str.optional(), reason: nullStr })
    .transform((o): NotMeasured | null => {
      const label = o.label ?? o.name ?? o.var_id;
      return label === undefined ? null : { label, reason: o.reason };
    }),
]);
const notMeasured = z
  .array(z.unknown())
  .catch([])
  .transform((items) => {
    const out: NotMeasured[] = [];
    for (const it of items) {
      const p = notMeasuredItem.safeParse(it);
      if (p.success && p.data) out.push(p.data);
    }
    return out;
  });
const answer = z.object({
  text: str, checked: z.boolean().catch(false), figures: strArr.catch([]), source: str.catch(""),
  not_measured: notMeasured,
});
const done = z.object({
  thread_id: str, n_tests: num.catch(0), n_tests_branch: nullNum, n_tool_calls: nullNum,
});

const schemas = {
  place, thinking: z.object({ text: str }), tool_start: toolStart, tool_done: toolDone,
  tool_failed: toolFailed, map: mapOp, board, answer, done, error: z.object({ message: str }),
} as const;

export function parseEvent(name: string, data: unknown): DetEvent | null {
  if (!Object.hasOwn(schemas, name)) return null;
  const r = schemas[name as keyof typeof schemas].safeParse(data);
  if (!r.success) return null;
  return { kind: name, data: r.data } as DetEvent;
}

export function parseSseMessage(m: SseMessage): DetEvent | null {
  let json: unknown;
  try {
    json = JSON.parse(m.data);
  } catch {
    return null;
  }
  return parseEvent(m.event, json);
}
