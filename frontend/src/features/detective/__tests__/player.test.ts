import { test } from "node:test";
import assert from "node:assert/strict";
import { DWELL_MS, INITIAL_PLAYER, dwellMs, playerReducer } from "../player.ts";
import type { PlayerState } from "../player.ts";
import type { Scene, SceneKind } from "../scenes.ts";
import type { StampBeat } from "../board.ts";

const mk = (kind: SceneKind, extra: Partial<Scene> = {}): Scene => ({
  key: `${kind}-${Math.random()}`, kind, question: null, tool: null, mapOps: [], stamps: [], note: null, complete: true, ...extra,
});
const stamp = {} as StampBeat;
const at = (index: number, enteredAt = 0, extra: Partial<PlayerState> = {}): PlayerState => ({ ...INITIAL_PLAYER, index, enteredAt, ...extra });

test("waits for an incomplete scene", () => {
  const scenes = [mk("evidence", { complete: false }), mk("evidence")];
  const s = playerReducer(INITIAL_PLAYER, { type: "tick", now: 60_000, scenes });
  assert.equal(s.index, 0);
});

test("holds an evidence scene 5000 ms", () => {
  const scenes = [mk("evidence"), mk("evidence")];
  assert.equal(playerReducer(INITIAL_PLAYER, { type: "tick", now: 4999, scenes }).index, 0);
  const s = playerReducer(INITIAL_PLAYER, { type: "tick", now: 5000, scenes });
  assert.equal(s.index, 1);
  assert.equal(s.enteredAt, 5000);
});

test("stamps add 1500 ms each", () => {
  const scenes = [mk("evidence", { stamps: [stamp, stamp] }), mk("evidence")];
  assert.equal(dwellMs(scenes[0], 1), 5000 + 3000);
  assert.equal(playerReducer(INITIAL_PLAYER, { type: "tick", now: 7999, scenes }).index, 0);
  assert.equal(playerReducer(INITIAL_PLAYER, { type: "tick", now: 8000, scenes }).index, 1);
  assert.equal(dwellMs(mk("opening"), 0), DWELL_MS.opening);
});

test("catches up when 3 scenes wait", () => {
  const scenes = [mk("evidence"), mk("evidence"), mk("evidence"), mk("evidence"), mk("evidence")];
  assert.equal(dwellMs(scenes[0], 4), DWELL_MS.catchUp);
  assert.equal(dwellMs(scenes[0], 2), 5000);
  assert.equal(playerReducer(INITIAL_PLAYER, { type: "tick", now: 1200, scenes }).index, 1);
  // backlog 3 (4 scenes, at index 0) also catches up
  assert.equal(playerReducer(INITIAL_PLAYER, { type: "tick", now: 1200, scenes: scenes.slice(0, 4) }).index, 1);
});

test("pause and goto stop ticks; live jumps to the last scene and unpins", () => {
  const scenes = [mk("evidence"), mk("evidence"), mk("evidence")];
  const paused = playerReducer(INITIAL_PLAYER, { type: "pause" });
  assert.equal(playerReducer(paused, { type: "tick", now: 99_999, scenes }).index, 0);
  const resumed = playerReducer(paused, { type: "resume", now: 100_000 });
  assert.equal(resumed.paused, false);
  assert.equal(playerReducer(resumed, { type: "tick", now: 104_999, scenes }).index, 0);
  assert.equal(playerReducer(resumed, { type: "tick", now: 105_000, scenes }).index, 1);

  const back = playerReducer(at(2, 0), { type: "goto", index: 0, now: 10 });
  assert.deepEqual([back.index, back.pinned, back.enteredAt], [0, true, 10]);
  assert.equal(playerReducer(back, { type: "tick", now: 99_999, scenes }).index, 0);
});

test("goto clamps at 0; live unpins", () => {
  const scenes = [mk("evidence"), mk("evidence"), mk("evidence")];
  const pinned = at(0, 0, { pinned: true });
  const live = playerReducer(pinned, { type: "live", now: 50, scenes });
  assert.deepEqual([live.index, live.pinned, live.enteredAt], [2, false, 50]);
  assert.equal(playerReducer(INITIAL_PLAYER, { type: "goto", index: -4, now: 1 }).index, 0);
  assert.equal(playerReducer(INITIAL_PLAYER, { type: "reset", now: 7 }).enteredAt, 7);
});

test("never past the last scene", () => {
  const scenes = [mk("evidence"), mk("ending")];
  const s = playerReducer(at(1, 0), { type: "tick", now: 1e9, scenes });
  assert.equal(s.index, 1);
  assert.equal(playerReducer(at(5, 0), { type: "tick", now: 1e9, scenes }).index, 5); // stale index: no advance
  assert.equal(playerReducer(INITIAL_PLAYER, { type: "tick", now: 1e9, scenes: [] }).index, 0);
});
