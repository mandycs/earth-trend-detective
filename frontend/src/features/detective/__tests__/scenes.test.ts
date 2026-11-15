import { test } from "node:test";
import assert from "node:assert/strict";
import { groupScenes, MAP_TOOLS, CONTEXT_TOOLS } from "../scenes.ts";
import type { DetEvent } from "../events.ts";
import { PLACE, RUN_EVENTS, BOARD_1 } from "./fixtures.ts";

const place: DetEvent = { kind: "place", data: PLACE };
const think = (text: string): DetEvent => ({ kind: "thinking", data: { text } });
const start = (id: string, tool: string, args: Record<string, unknown> = {}): DetEvent => ({
  kind: "tool_start", data: { id, tool, args },
});
const doneTool = (id: string, tool: string): DetEvent => ({
  kind: "tool_done", data: { id, tool, summary: `${tool} done`, result: { ok: true }, evidence_id: "e1" },
});
const flyTo: DetEvent = { kind: "map", data: { op: "fly_to", bbox: [0, 0, 1, 1], pitch: 55, bearing: 10 } };

test("tool sets", () => {
  for (const t of ["show_layer", "set_year", "show_before_after", "fly_to", "show_footprint", "update_board"]) {
    assert.ok(MAP_TOOLS.has(t), t);
  }
  for (const t of ["profile_place", "list_variables", "land_cover_change", "satellite_picture", "solved_case"]) {
    assert.ok(CONTEXT_TOOLS.has(t), t);
  }
  assert.equal(MAP_TOOLS.size, 6);
  assert.equal(CONTEXT_TOOLS.size, 5);
});

test("opening then one scene per non-map tool", () => {
  const inv = groupScenes(RUN_EVENTS);
  assert.deepEqual(inv.scenes.map((s) => s.kind), ["opening", "context", "evidence", "evidence", "ending"]);
  assert.equal(inv.scenes[0].key, "opening");
  assert.equal(inv.scenes[4].key, "ending");
  assert.deepEqual(inv.place, PLACE);
  assert.equal(inv.finished, true);
  assert.ok(inv.done);
  assert.ok(inv.answer);
  assert.equal(inv.error, null);

  const [, ctx, ev1, ev2] = inv.scenes;
  assert.equal(ctx.key, "toolu_a");
  assert.equal(ctx.question, "What kind of place is this?");
  assert.equal(ctx.tool?.state, "done");
  assert.equal(ctx.tool?.summary, "Done.");
  assert.equal(ev1.tool?.evidenceId, "e1");
  assert.deepEqual(ev1.tool?.args, { var_id: "grace_tws" });
  assert.equal(ev2.tool?.state, "failed");
  assert.equal(ev2.tool?.reason, "NASA POWER did not answer. Try again in a few minutes.");
  assert.equal(ev2.tool?.summary, null);
  assert.equal(ev2.tool?.result, null);
  // The footprint op arrives after its tool_done and lands on the last scene at that moment.
  assert.deepEqual(ev2.mapOps.map((o) => o.op), ["show_footprint"]);
  assert.ok(inv.scenes.every((s) => s.complete));
});

test("board sets the board and stamps the last scene", () => {
  const inv = groupScenes(RUN_EVENTS);
  assert.deepEqual(inv.board, BOARD_1);
  assert.deepEqual(inv.scenes[3].stamps, [{ suspectId: "less rain", label: "less rain", status: "ruled_out", downgraded: null }]);
  // A second identical board adds no new beats.
  const again = groupScenes([...RUN_EVENTS.slice(0, 13), { kind: "board", data: BOARD_1 }]);
  assert.equal(again.scenes[3].stamps.length, 1);
});

test("thinking attaches to the first parallel call only", () => {
  const inv = groupScenes([place, think("Q?"), start("a", "get_series"), start("b", "trend_test")]);
  assert.equal(inv.scenes[1].question, "Q?");
  assert.equal(inv.scenes[2].question, null);
  assert.equal(inv.scenes[0].question, null);
});

test("map ops go to the last scene", () => {
  const inv = groupScenes([place, think("Q?"), start("a", "get_series"), doneTool("a", "get_series"), start("f", "fly_to"), flyTo]);
  assert.equal(inv.scenes.length, 2);
  assert.deepEqual(inv.scenes[1].mapOps, [flyTo.data]);
  assert.deepEqual(inv.scenes[0].mapOps, []);
});

test("map tool results are not shown", () => {
  const inv = groupScenes([place, start("f", "show_layer"), doneTool("f", "show_layer")]);
  assert.equal(inv.scenes.length, 1);
  assert.equal(inv.scenes[0].tool, null);
});

test("map-only step with a question becomes a note scene", () => {
  const inv = groupScenes([
    place, think("Let me look closer."), start("f", "fly_to"), flyTo,
    think("And the board."), start("u", "update_board"), start("s", "solved_case"),
  ]);
  assert.deepEqual(inv.scenes.map((s) => [s.key, s.kind]), [
    ["opening", "opening"], ["note-1", "note"], ["note-2", "note"], ["s", "context"],
  ]);
  assert.equal(inv.scenes[1].question, "Let me look closer.");
  assert.equal(inv.scenes[1].tool, null);
  assert.equal(inv.scenes[1].complete, true);
  assert.deepEqual(inv.scenes[1].mapOps, [flyTo.data]);
  assert.equal(inv.scenes[2].question, "And the board.");
  assert.equal(inv.scenes[3].question, null);
});

test("agent failure becomes a note", () => {
  const inv = groupScenes([place, { kind: "tool_failed", data: { id: null, tool: "agent", reason: "The model did not answer." } }]);
  assert.equal(inv.scenes[1].kind, "note");
  assert.equal(inv.scenes[1].key, "note-1");
  assert.equal(inv.scenes[1].note, "The model did not answer.");
  assert.equal(inv.scenes[1].complete, true);
});

test("ended stream marks running tools unfinished", () => {
  const evs = [place, start("a", "get_series")];
  const ended = groupScenes(evs, { ended: true });
  assert.equal(ended.scenes[1].tool?.state, "unfinished");
  assert.equal(ended.scenes[1].complete, true);
  assert.equal(ended.finished, false);
  const live = groupScenes(evs);
  assert.equal(live.scenes[1].tool?.state, "running");
  assert.equal(live.scenes[1].complete, false);
});

test("error ends the investigation", () => {
  const inv = groupScenes([place, start("a", "get_series"), { kind: "error", data: { message: "Lost the line." } }]);
  const last = inv.scenes[inv.scenes.length - 1];
  assert.deepEqual([last.key, last.kind, last.note], ["error", "error", "Lost the line."]);
  assert.equal(inv.error, "Lost the line.");
  assert.equal(inv.finished, true);
  assert.equal(inv.scenes[1].tool?.state, "unfinished");
  assert.ok(inv.scenes.every((s) => s.complete));
});

test("empty stream", () => {
  const inv = groupScenes([]);
  assert.deepEqual(inv, { place: null, scenes: [], board: null, answer: null, done: null, error: null, finished: false });
  // Map ops and boards before any scene are kept off the scenes without crashing.
  const early = groupScenes([flyTo, { kind: "board", data: BOARD_1 }]);
  assert.equal(early.scenes.length, 0);
  assert.deepEqual(early.board, BOARD_1);
});

const deepFreeze = <T>(o: T): T => {
  if (o && typeof o === "object") {
    for (const v of Object.values(o)) deepFreeze(v);
    Object.freeze(o);
  }
  return o;
};

test("does not mutate its input and is deterministic", () => {
  const evs = deepFreeze(structuredClone([...RUN_EVENTS]));
  const a = groupScenes(evs);
  const b = groupScenes(evs);
  assert.deepEqual(a, b);
  assert.deepEqual(evs, RUN_EVENTS);
  assert.deepEqual(groupScenes(deepFreeze(structuredClone([place, start("a", "get_series")])), { ended: true }).scenes[1].tool?.state, "unfinished");
});
