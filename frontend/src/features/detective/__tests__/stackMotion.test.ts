import { test } from "node:test";
import assert from "node:assert/strict";
import { atRest, collapseReport, springStep } from "../stack/motion.ts";
import type { CollapseState } from "../stack/motion.ts";

test("collapsed is never reported before the stack has exploded", () => {
  let s: CollapseState = { wasExploded: false, reported: false };
  // On mount: not exploded, nothing moving (one slab, or reduced motion). Frames go by: no report.
  for (let i = 0; i < 5; i++) {
    const r = collapseReport(s, false, false);
    assert.equal(r.report, false);
    s = r.state;
  }
  // Exploded, then collapsed: reported once, when nothing moves any more.
  s = collapseReport(s, true, true).state;
  s = collapseReport(s, true, false).state;
  let r = collapseReport(s, false, true);
  assert.equal(r.report, false);
  r = collapseReport(r.state, false, false);
  assert.equal(r.report, true);
  r = collapseReport(r.state, false, false);
  assert.equal(r.report, false);
  // Exploded again: a new collapse is reported again.
  r = collapseReport(collapseReport(r.state, true, false).state, false, false);
  assert.equal(r.report, true);
});

test("the spring settles exactly on its target without overshoot", () => {
  let m = { y: 0, v: 0 };
  let max = 0;
  for (let i = 0; i < 600 && !atRest(m, 1); i++) {
    m = springStep(m, 1, 1 / 60);
    max = Math.max(max, m.y);
  }
  assert.ok(atRest(m, 1));
  assert.ok(max <= 1.0005);
  const before = { y: 0.5, v: 0 };
  springStep(before, 1, 1 / 60);
  assert.deepEqual(before, { y: 0.5, v: 0 }); // input untouched
});
