import { test } from "node:test";
import assert from "node:assert/strict";
import { elapsedLabel, waitingNote } from "../waiting.ts";

test("a short wait says nothing extra", () => {
  assert.equal(waitingNote(0), null);
  assert.equal(waitingNote(14), null);
});

test("a slow step explains the wait, then explains it again", () => {
  assert.match(waitingNote(15) ?? "", /minute or two/);
  assert.match(waitingNote(60) ?? "", /few minutes/);
  assert.ok(!/\d/.test(waitingNote(90) ?? "x"), "no figures in the note");
});

test("elapsed time reads in seconds, then minutes", () => {
  assert.equal(elapsedLabel(0), "0 s");
  assert.equal(elapsedLabel(59.9), "59 s");
  assert.equal(elapsedLabel(65), "1 min 05 s");
  assert.equal(elapsedLabel(-3), "0 s");
});
