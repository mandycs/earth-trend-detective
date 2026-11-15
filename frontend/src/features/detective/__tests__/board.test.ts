import { test } from "node:test";
import assert from "node:assert/strict";
import { stampsBetween, verdictFor, STATUS_WORDS } from "../board.ts";
import type { BoardEvent, Suspect } from "../events.ts";

const s = (id: string, status: Suspect["status"], downgraded: string | null = null): Suspect => ({
  id, label: `L-${id}`, status, evidence: [], note: "", downgraded,
});
const b = (suspects: Suspect[], verdicts: BoardEvent["verdicts"] = {}): BoardEvent => ({ suspects, n_tests: 1, verdicts });

test("a new status is a beat", () => {
  const out = stampsBetween(b([s("a", "open")]), b([s("a", "supported")]));
  assert.deepEqual(out, [{ suspectId: "a", label: "L-a", status: "supported", downgraded: null }]);
  assert.equal(stampsBetween(b([s("a", "supported")]), b([s("a", "supported")])).length, 0);
  assert.equal(stampsBetween(null, b([s("n", "hint")])).length, 1);
  assert.equal(stampsBetween(b([s("a", "supported")]), b([s("a", "open")])).length, 0);
  assert.equal(stampsBetween(null, b([s("n", "open")])).length, 0);
});

test("downgrade travels with the beat", () => {
  const out = stampsBetween(b([s("a", "open")]), b([s("a", "hint", "supported")]));
  assert.equal(out[0].downgraded, "supported");
});

test("verdictFor prefers the board's corrected verdict", () => {
  const board = b([], { t1: { verdict: "real", direction: "up" } });
  assert.deepEqual(verdictFor("t1", board, { verdict: "unknown", direction: "flat" }), { verdict: "real", direction: "up" });
  assert.deepEqual(verdictFor("t2", board, { verdict: "likely", direction: "down" }), { verdict: "likely", direction: "down" });
  assert.equal(verdictFor("t2", board, { verdict: "unknown" }), null);
  assert.equal(verdictFor(null, null, { verdict: "bogus", direction: "up" }), null);
  assert.equal(verdictFor("t1", null), null);
});

test("status words carry icon and text", () => {
  for (const k of ["supported", "ruled_out", "hint", "open"] as const) {
    assert.ok(STATUS_WORDS[k].icon && STATUS_WORDS[k].text && STATUS_WORDS[k].meaning);
  }
});
