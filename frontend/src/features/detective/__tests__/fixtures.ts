// Test fixtures for the detective stream. The event structure follows a recorded Lake Mead run
// (parallel tool calls after one `thinking`, a failed call, a map op arriving after its `tool_done`),
// trimmed to the minimum. Values are test data, never shown as measurements.
import type { BoardEvent, DetEvent, PlaceEvent } from "../events.ts";

export const PLACE: PlaceEvent = {
  thread_id: "th1", follow_up: false, forked_from: null, id: "lake_mead", name: "Lake Mead (USA)",
  lat: 36.2, lon: -114.5, bbox: [-114.9, 35.9, -114.0, 36.6], tags: ["water_body"], site_id: "lake_mead",
  years: [2003, 2024],
};

export const BOARD_1: BoardEvent = {
  suspects: [
    { id: "less rain", label: "less rain", status: "ruled_out", evidence: ["e2"], note: "n", downgraded: null },
    { id: "water use", label: "water use", status: "open", evidence: [], note: "", downgraded: null },
  ],
  n_tests: 1,
  verdicts: {},
};

/** A realistic run in the documented order. Scene kinds: opening, context, evidence, evidence, ending. */
export const RUN_EVENTS: readonly DetEvent[] = [
  { kind: "place", data: PLACE },
  { kind: "thinking", data: { text: "What kind of place is this?" } },
  { kind: "tool_start", data: { id: "toolu_a", tool: "profile_place", args: {} } },
  { kind: "tool_done", data: { id: "toolu_a", tool: "profile_place", summary: "Done.", result: { tags: ["water_body"] }, evidence_id: null } },
  { kind: "thinking", data: { text: "Is the water stored falling, and is rain?" } },
  { kind: "tool_start", data: { id: "toolu_b", tool: "get_series", args: { var_id: "grace_tws" } } },
  { kind: "tool_start", data: { id: "toolu_c", tool: "get_series", args: { var_id: "precip_upstream" } } },
  { kind: "tool_start", data: { id: "toolu_d", tool: "show_footprint", args: { source: "grace" } } },
  { kind: "tool_done", data: { id: "toolu_b", tool: "get_series", summary: "Total water stored.", result: { status: "ok" }, evidence_id: "e1" } },
  { kind: "tool_failed", data: { id: "toolu_c", tool: "get_series", reason: "NASA POWER did not answer. Try again in a few minutes." } },
  { kind: "tool_done", data: { id: "toolu_d", tool: "show_footprint", summary: "Done.", result: { status: "shown" }, evidence_id: null } },
  {
    kind: "map",
    data: { op: "show_footprint", source: "grace", label: "GRACE data cell (~300 km)", size: "~300 km", bbox: [-116, 34, -113, 37], approximate: true },
  },
  { kind: "board", data: BOARD_1 },
  {
    kind: "answer",
    data: { text: "Stored water is falling. A clue, not proof.", checked: true, figures: [], source: "llm", not_measured: [] },
  },
  { kind: "done", data: { thread_id: "th1", n_tests: 1, n_tool_calls: 3, n_tests_branch: null } },
];
