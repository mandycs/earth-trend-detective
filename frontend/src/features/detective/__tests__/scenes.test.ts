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
  assert.equal(inv.scenes[0].key, "opening-0");
  assert.equal(inv.scenes[4].key, "ending-0");
  assert.deepEqual(inv.place, PLACE);
  assert.equal(inv.finished, true);
  assert.ok(inv.done);
  assert.ok(inv.answer);
  assert.equal(inv.error, null);

  const [, ctx, ev1, ev2] = inv.scenes;
  assert.equal(ctx.key, "toolu_a-0");
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
  const evs = [
    place, think("Let me look closer."), start("f", "fly_to"), start("g", "show_layer"), flyTo,
    think("And the board."), start("u", "update_board"), doneTool("u", "update_board"),
  ];
  const inv = groupScenes(evs);
  assert.deepEqual(inv.scenes.map((s) => [s.key, s.kind]), [
    ["opening-0", "opening"], ["note-1-0", "note"], ["note-2-0", "note"],
  ]);
  assert.equal(inv.scenes[1].question, "Let me look closer.");
  assert.equal(inv.scenes[1].tool, null);
  assert.equal(inv.scenes[1].complete, true);
  assert.deepEqual(inv.scenes[1].mapOps, [flyTo.data]);
  assert.equal(inv.scenes[2].question, "And the board.");
  // While the batch is still open the note is not made yet; the end of the stream closes it.
  const open = evs.slice(0, 4);
  assert.equal(groupScenes(open).scenes.length, 1);
  assert.deepEqual(groupScenes(open, { ended: true }).scenes.map((s) => s.key), ["opening-0", "note-1-0"]);
});

test("a mixed batch gives the question to the real tool, with no note", () => {
  // Lake Mead: "I'll record the two suspects on the board and read the solved case" ->
  // update_board, update_board, solved_case.
  const inv = groupScenes([
    place, think("Record the suspects and read the solved case."),
    start("u1", "update_board"), start("u2", "update_board"), start("s", "solved_case"),
    doneTool("u1", "update_board"), doneTool("u2", "update_board"), doneTool("s", "solved_case"),
  ]);
  assert.deepEqual(inv.scenes.map((s) => [s.key, s.kind]), [["opening-0", "opening"], ["s-0", "context"]]);
  assert.equal(inv.scenes[1].question, "Record the suspects and read the solved case.");
  assert.equal(inv.scenes[1].tool?.state, "done");
});

test("two turns in one array", () => {
  const followUp: DetEvent = { kind: "place", data: { ...PLACE, follow_up: true } };
  const evs: DetEvent[] = [
    ...RUN_EVENTS,
    followUp, think("And the rain upstream?"), start("toolu_a", "get_series"), doneTool("toolu_a", "get_series"),
    { kind: "answer", data: { text: "No clear trend.", checked: true, figures: [], source: "llm", not_measured: [] } },
  ];
  const inv = groupScenes(evs);
  const keys = inv.scenes.map((s) => s.key);
  assert.equal(new Set(keys).size, keys.length);
  assert.deepEqual(keys.slice(5), ["opening-1", "toolu_a-1", "ending-1"]);
  assert.deepEqual(keys.slice(0, 5), groupScenes(RUN_EVENTS).scenes.map((s) => s.key));
  // The second turn has an answer but no done yet: it is not finished.
  assert.equal(inv.finished, false);
  assert.equal(inv.answer?.text, "No clear trend.");
  // A tool left running in an earlier turn did not finish.
  const cut = groupScenes([place, start("x", "get_series"), followUp]);
  assert.equal(cut.scenes[1].tool?.state, "unfinished");
});

test("complete means the tool stopped; only the last scene can still change", () => {
  const full = groupScenes(RUN_EVENTS).scenes;
  for (let n = 1; n <= RUN_EVENTS.length; n++) {
    const pre = groupScenes(RUN_EVENTS.slice(0, n)).scenes;
    pre.forEach((s, i) => {
      assert.equal(s.key, full[i].key, `prefix ${n} scene ${i} key`);
      if (s.complete && i < pre.length - 1) assert.deepEqual(s, full[i], `prefix ${n} scene ${s.key}`);
    });
  }
  // The last scene is complete once its tool is done, yet still gains the footprint op that follows.
  const beforeOp = groupScenes(RUN_EVENTS.slice(0, 11)).scenes;
  const lastBefore = beforeOp[beforeOp.length - 1];
  assert.equal(lastBefore.complete, true);
  assert.deepEqual(lastBefore.mapOps, []);
  assert.equal(full[3].mapOps.length, 1);
});

test("agent failure becomes a note", () => {
  const inv = groupScenes([place, { kind: "tool_failed", data: { id: null, tool: "agent", reason: "The model did not answer." } }]);
  assert.equal(inv.scenes[1].kind, "note");
  assert.equal(inv.scenes[1].key, "note-1-0");
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
  assert.deepEqual([last.key, last.kind, last.note], ["error-0", "error", "Lost the line."]);
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
