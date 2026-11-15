import { test } from "node:test";
import assert from "node:assert/strict";
import { boxFromCorners, messageForResponse, requestBody, targetLabel, wrapLon } from "../request.ts";

const ok = (r: ReturnType<typeof boxFromCorners>) => {
  assert.equal(r.ok, true);
  return (r as { ok: true; bbox: [number, number, number, number] }).bbox;
};

test("wrapLon folds into [-180, 180)", () => {
  assert.equal(wrapLon(190), -170);
  assert.equal(wrapLon(-190), 170);
  assert.equal(wrapLon(-4.5), -4.5);
});

test("box across the antimeridian is refused", () => {
  const r = boxFromCorners({ lat: 10, lon: wrapLon(179) }, { lat: 11, lon: wrapLon(-179) });
  assert.deepEqual(r, { ok: false, message: "Boxes can't cross the 180° line yet. Draw it on one side." });
});

test("tiny box is refused", () => {
  const r = boxFromCorners({ lat: 10, lon: 10 }, { lat: 10.005, lon: 11 });
  assert.deepEqual(r, { ok: false, message: "That box is too small. Drag a little wider." });
});

test("corners in any order give w<e, s<n", () => {
  const a = ok(boxFromCorners({ lat: 37.1, lon: -4.4 }, { lat: 36.9, lon: -4.6 }));
  const b = ok(boxFromCorners({ lat: 36.9, lon: -4.6 }, { lat: 37.1, lon: -4.4 }));
  assert.deepEqual(a, b);
  assert.ok(a[0] < a[2] && a[1] < a[3]);
});

test("poles are clamped", () => {
  const b = ok(boxFromCorners({ lat: 89, lon: 0 }, { lat: -90, lon: 1 }));
  assert.equal(b[1], -85);
  assert.equal(b[3], 85);
});

test("bodies", () => {
  const bbox: [number, number, number, number] = [1, 2, 3, 4];
  assert.deepEqual(requestBody({ kind: "point", lat: 1, lon: 2 }, "  why?  "), { question: "why?", lat: 1, lon: 2 });
  assert.deepEqual(requestBody({ kind: "box", bbox }, "q"), { question: "q", bbox });
  assert.deepEqual(requestBody({ kind: "case", siteId: "s", name: "S", bbox }, "q"), { question: "q", site_id: "s" });
  assert.deepEqual(
    requestBody({ kind: "point", lat: 1, lon: 2 }, "q", { threadId: "t", checkpointId: "c" }),
    { question: "q", lat: 1, lon: 2, thread_id: "t", checkpoint_id: "c" },
  );
  assert.deepEqual(requestBody({ kind: "point", lat: 1, lon: 2 }, "q", { threadId: null, checkpointId: null }), {
    question: "q", lat: 1, lon: 2,
  });
});

test("pydantic prefix is stripped", () => {
  assert.equal(messageForResponse(422, { detail: [{ msg: "Value error, Give a location." }] }), "Give a location.");
  assert.equal(messageForResponse(404, { detail: "Unknown site." }), "Unknown site.");
});

test("server traces never shown", () => {
  assert.equal(
    messageForResponse(503, { detail: "Traceback (most recent call last)" }),
    "The investigation failed on the server. Try again in a moment.",
  );
  assert.equal(
    messageForResponse(404, { detail: "Error 404 from upstream" }),
    "This place or question could not be investigated. Pick another point and try again.",
  );
  assert.equal(messageForResponse(500, null), "The investigation failed on the server. Try again in a moment.");
  assert.equal(messageForResponse(400, "x"), "This place or question could not be investigated. Pick another point and try again.");
});

test("labels", () => {
  assert.equal(targetLabel({ kind: "point", lat: 37, lon: -4.5 }), "Point 37.00, −4.50");
  assert.equal(targetLabel({ kind: "case", siteId: "s", name: "Doñana", bbox: [0, 0, 1, 1] }), "Doñana");
  assert.match(targetLabel({ kind: "box", bbox: [-4.6, 36.9, -4.4, 37.1] }), /^Box 36\.90–37\.10 N, /);
});

test("a point body carries a wrapped longitude", () => {
  assert.deepEqual(requestBody({ kind: "point", lat: 1, lon: 190 }, "q"), { question: "q", lat: 1, lon: -170 });
});

test("a box whose east corner sits on the 180° line is not a crossing", () => {
  const r = boxFromCorners({ lat: 10, lon: 170 }, { lat: 20, lon: 180 });
  assert.deepEqual(r, { ok: true, bbox: [170, 10, 180, 20] });
});

test("internals, structural Pydantic messages and long text never reach the screen", () => {
  const GENERIC = "This place or question could not be investigated. Pick another point and try again.";
  const SERVER = "The investigation failed on the server. Try again in a moment.";
  assert.equal(messageForResponse(404, { detail: "see https://example.org" }), GENERIC);
  assert.equal(messageForResponse(404, { detail: "/srv/app/data missing" }), GENERIC);
  assert.equal(messageForResponse(502, { detail: "[Errno 111] Connection refused" }), SERVER);
  assert.equal(messageForResponse(502, { detail: "upstream said HTTP 503" }), SERVER);
  assert.equal(messageForResponse(400, { detail: "line one\nline two" }), GENERIC);
  assert.equal(messageForResponse(400, { detail: "x".repeat(201) }), GENERIC);
  assert.equal(messageForResponse(422, { detail: [{ msg: "Field required" }] }), GENERIC);
  assert.equal(messageForResponse(422, { detail: [{ msg: "Input should be a valid number" }] }), GENERIC);
  assert.equal(messageForResponse(422, { detail: "Pick a step after a tool finished." }), "Pick a step after a tool finished.");
});

test("a coordinate that rounds to zero has no sign", () => {
  assert.equal(targetLabel({ kind: "point", lat: -0.001, lon: 2 }), "Point 0.00, 2.00");
});
