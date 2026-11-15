import { test } from "node:test";
import assert from "node:assert/strict";
import { parseEvent, parseSseMessage } from "../events.ts";

const bbox = [-4.6, 36.9, -4.4, 37.1];
const place = {
  thread_id: "9f", follow_up: false, forked_from: null, id: "point", name: "Point 37.000, -4.500",
  lat: 37.0, lon: -4.5, bbox, tags: [], site_id: null, years: [2003, 2024],
};
const fixtures: Record<string, unknown> = {
  place,
  thinking: { text: "Now the t2m series." },
  tool_start: { id: "toolu_1", tool: "get_series", args: { var_id: "t2m" } },
  tool_done: { id: "toolu_1", tool: "get_series", summary: "Air temperature.", result: { q: 0.01 }, evidence_id: "e1" },
  tool_failed: { id: null, tool: "agent", reason: "The model did not answer." },
  board: {
    suspects: [{ id: "warming", label: "warming", status: "supported", evidence: ["e2"], note: "n", downgraded: null, claimed: "supported", dropped: [] }],
    n_tests: 1,
  },
  answer: { text: "Went up.", checked: true, figures: ["2003"], source: "llm" },
  done: { thread_id: "9f", n_tests: 1, n_tool_calls: 2 },
  error: { message: "The investigator needs a language model key on the server." },
};
const ops = [
  { op: "show_layer", layer_id: "land_cover", year: 2023 },
  { op: "set_year", year: 2010 },
  { op: "show_before_after", layer_id: "l", year_a: 2003, year_b: 2023 },
  { op: "fly_to", bbox },
  { op: "show_footprint", source: "s", label: "l", size: "1 km", bbox },
];

test("parses each documented shape", () => {
  for (const [kind, f] of Object.entries(fixtures)) assert.equal(parseEvent(kind, f)?.kind, kind, kind);
  for (const o of ops) {
    const e = parseEvent("map", o);
    assert.equal(e?.kind, "map");
    assert.equal(e?.kind === "map" && e.data.op, o.op);
  }
});

test("tolerates old and new payloads", () => {
  const b = (extra: object) => parseEvent("board", { ...(fixtures.board as object), ...extra });
  const verd = (e: ReturnType<typeof b>) => (e?.kind === "board" ? e.data.verdicts : null);
  assert.deepEqual(verd(b({})), {});
  assert.deepEqual(verd(b({ verdicts: { t1: { verdict: "real", direction: "up" } } })), { t1: { verdict: "real", direction: "up" } });
  const a = (extra: object) => {
    const e = parseEvent("answer", { ...(fixtures.answer as object), ...extra });
    return e?.kind === "answer" ? e.data.not_measured : null;
  };
  assert.deepEqual(a({}), []);
  assert.deepEqual(a({ not_measured: ["ndvi"] }), [{ label: "ndvi", reason: null }]);
  assert.deepEqual(a({ not_measured: [{ var_id: "ndvi", label: "Greenness", reason: "not here" }] }), [{ label: "Greenness", reason: "not here" }]);
  const d = parseEvent("done", fixtures.done);
  assert.equal(d?.kind === "done" && d.data.n_tests_branch, null);
  const d2 = parseEvent("done", { ...(fixtures.done as object), n_tests_branch: 3 });
  assert.equal(d2?.kind === "done" && d2.data.n_tests_branch, 3);
  const p = parseEvent("place", { ...place, extra: 1 });
  assert.ok(p && p.kind === "place" && !("extra" in p.data));
});

test("unknown things are null, not throws", () => {
  assert.equal(parseEvent("plan", {}), null);
  assert.equal(parseEvent("map", { op: "spin" }), null);
  const e = parseEvent("board", { suspects: [{ id: "x", label: "x", status: "weird" }], n_tests: 0 });
  assert.equal(e?.kind === "board" && e.data.suspects[0].status, "open");
  const t = parseEvent("tool_done", { id: "a", tool: "t", summary: "s", evidence_id: null });
  assert.deepEqual(t?.kind === "tool_done" && t.data.result, {});
  const { bbox: _b, ...noBbox } = place;
  assert.equal(parseEvent("place", noBbox), null);
  assert.equal(parseEvent("thinking", null), null);
});

test("map defaults", () => {
  const sl = parseEvent("map", { op: "show_layer", layer_id: "l" });
  assert.ok(sl?.kind === "map" && sl.data.op === "show_layer" && sl.data.opacity === 0.8);
  const ft = parseEvent("map", { op: "fly_to", bbox });
  assert.ok(ft?.kind === "map" && ft.data.op === "fly_to" && ft.data.pitch === 55 && ft.data.bearing === 0);
  const ba = parseEvent("map", { op: "show_before_after", layer_id: "l", year_a: 1, year_b: 2 });
  assert.ok(ba?.kind === "map" && ba.data.op === "show_before_after" && ba.data.before_url === null && ba.data.after_url === null && ba.data.bbox === null);
});

test("parseSseMessage on bad JSON is null", () => {
  assert.equal(parseSseMessage({ event: "place", data: "{nope" }), null);
  assert.equal(parseSseMessage({ event: "thinking", data: '{"text":"hi"}' })?.kind, "thinking");
});
