# Detective screen (front end) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `/detective` route in Instrument mode where the user picks a point or draws a box on a MapLibre globe with 3D relief, asks in plain words, and watches the `POST /detective` stream play as scenes (question line, tool, result, chart, map layer, camera, board stamps), ending on the checked answer. Live runs and recorded runs (`?replay=<name>`) go through the same scene player.

**Architecture:** Pure TypeScript modules come first, each with `node:test` tests: SSE parser, event normaliser, scene grouping, board stamps, scene player reducer, layer catalog, map-view reducer, chart model, request building, run reducer and replay schedule. React components and the route are thin shells over those modules. The map is a function of `(investigation, scene index)`, so scrubbing back to a scene shows that scene's map. The recordings are copied into `public/recordings` by a sync script that works like `sync-sites.mjs`, so replay needs no backend.

**Tech Stack:** Next 16.4.6 (app router), React 19.3.0, maplibre-gl 5.24.1 (globe + `raster-dem` terrain), zod 3.25.76 (already a dependency), TypeScript 5, Node ≥ 23.6 built-in test runner with type stripping (Node 24.13 is installed). No new dependency.

**Spec:** `docs/superpowers/specs/2026-11-15-detective-agent-design.md`. The binding sections are §5.4, §5.5, §5.5b, §5.5d, §5.6 and §5.7 items 3–4. Also read `DESIGN.md` (Instrument mode), `docs/UX-CHECKLIST.md`, `frontend/README.md` and `.superpowers/sdd/2026-11-15-detective-core/task-9-report.md` (event payload shapes as emitted).

## Global Constraints

- Branch `mandy/detective`. Push every commit to origin and never push to `main`. Commit style: `<type>: <description>` plus the session attribution lines.
- Frontend versions are frozen. Do not change any version in `package.json`, and add no dependency: "Next 16.4 · React 19.3 · @react-three/fiber 9.8 · three 0.187", maplibre-gl 5.24.1. `npm ci` only.
- Tests: `cd frontend && npm test`, which runs `node --test 'src/features/detective/**/*.test.ts'`. Pure modules use only erasable TS syntax: no `enum`, no `namespace`, no parameter properties. Their runtime relative imports carry the `.ts` extension, and type-only imports use `import type`. They use no `@/` alias, no JSX and no DOM.
- Every task ends with `npm run typecheck` clean, plus `npm test` green for any task that touches tests.
- "Ninguna cifra inventada": every figure on screen comes from an event payload, `layerCatalog.generated.ts` (legend ranges copied from GIBS) or `sites/<id>/`. The front never computes a figure it prints. Chart lines may be drawn from tool values (Task 8), but no number derived on the front is ever printed.
- No causal words in UI copy: no "proof", "cause" or "caused by". The ending always says "A clue, not proof." (spec §5.5b).
- Stamps and verdicts use icon + words, never colour alone, in ink only (DESIGN.md: "No accent colour in the interface").
- UI copy in English. Internal comments may be English. Body text ≥ 16 px, every target ≥ 44 px, buttons 48 px, square corners.
- `prefers-reduced-motion` means camera moves jump (`duration: 0`), the curtain does not animate and there is no drift. Scenes still advance, because a live run is a process display, and Pause is always available.
- `allowedDevOrigins` stays as it is. Static assets reach Next only through `public/`, via the sync scripts.
- The non-NASA relief is labelled on screen: "Relief: AWS Terrain Tiles (Mapzen), not a NASA product".
- `/investigate` keeps working (spec §5.2). Only the links change.

## Review Focus

1. **The stream closes without `done` or `error`** (server restart, Wi-Fi drop). The received scenes are kept and still play, running tools show "Did not finish", and a plain message says the connection closed. The screen never stays on "Checking…". Tests: Task 4 `ended stream marks running tools unfinished` and Task 10 `end without done is cut`.
2. **SSE chunks split anywhere** (mid-line, between `\r` and `\n`, `:` keep-alive comments, several `data:` lines). These give exactly the same events as one whole chunk. Test: Task 1 `every split position yields the same messages`.
3. **Payload fields the front has never seen, or missing ones** (the fix wave adds `verdicts`, `not_measured` and `n_tests_branch`, and there may be unknown map ops, unknown tools, an unknown `layer_id`, or an unknown event name). These are ignored or defaulted and never crash. Tests: Task 2 `tolerates old and new payloads` and Task 7 `unknown layer is skipped with a note`.
4. **A box drawn across the 180° line, a box with no area, or a box at the poles.** The user gets a plain message saying what to do. The request is never sent. Test: Task 9 `box across the antimeridian is refused`.
5. **A replay name with a path or junk in it** (`?replay=../../x`, an empty name, an uppercase name) or a recording file that does not parse. The user sees "This recording is not available." and a link to a live run, and nothing is fetched outside `/recordings/`. Test: Task 11 `rejects names outside the pattern`.

---

## File structure

```
frontend/
  package.json                         modify: "test", "sync-recordings", predev/prebuild chain
  tsconfig.json                        modify: "allowImportingTsExtensions": true
  .gitignore                           modify: /public/recordings
  scripts/sync-recordings.mjs          new: backend/data/recordings/*.json -> public/recordings (+ index.json)
  src/app/detective/page.tsx           new: server route, reads cases + recordings index
  src/app/page.tsx                     modify: cover hook -> /detective
  src/app/landing/CoverReel.tsx        modify: quiet link -> /detective
  src/story/StoryApp.tsx               modify: "Ask the detective" -> /detective?site=<id>
  src/features/explore/ExploreView.tsx modify: link -> /detective
  src/features/detective/
    sse.ts            pure SSE parser
    events.ts         event types + tolerant normaliser (zod)
    scenes.ts         events -> Investigation { scenes }
    board.ts          stamps, status words, verdict lookup
    player.ts         scene player reducer + dwell times
    request.ts        targets, box validation, request body, HTTP error text
    runState.ts       run reducer (live / replay status)
    replay.ts         recording schema, name check, schedule
    chart.ts          chart model per scene
    api.ts            fetch wrappers (stream, history, recording, case layers): not unit-tested
    map/types.ts      CatalogLayer, CaseLayerRow, MapView types
    map/layerCatalog.generated.ts   generated from backend/catalog/map_layers.yaml
    map/catalog.ts    lookup, date rules, tile URLs, terrain constants
    map/mapView.ts    map op reducer, mapViewAt
    useDetectiveRun.ts  hook: live stream + replay timers -> RunState
    useScenePlayer.ts   hook: ticks playerReducer
    DetectiveView.tsx   client root
    DetectiveMap.tsx    MapLibre globe, terrain, picking, layers, footprints, camera
    CurtainMap.tsx      second synced map clipped by a range input
    LayerLegend.tsx  QuestionBox.tsx  ScenePanel.tsx  SceneChart.tsx
    CaseBoard.tsx  AnswerPanel.tsx  StepList.tsx  HistoryList.tsx
    detective.module.css
    __tests__/*.test.ts
```

---

### Task 1: Test runner and the SSE parser

**Files:**
- Modify: `frontend/package.json` (scripts only), `frontend/tsconfig.json`
- Create: `frontend/src/features/detective/sse.ts`
- Test: `frontend/src/features/detective/__tests__/sse.test.ts`

**Interfaces:**
- Produces: `interface SseMessage { event: string; data: string }` and `createSseParser(onMessage: (m: SseMessage) => void): { push(chunk: string): void; end(): void }`

- [ ] **Step 1: Add the runner.** In `package.json` scripts add `"test": "node --test 'src/features/detective/**/*.test.ts'"`. Add `"allowImportingTsExtensions": true` to `tsconfig.json` `compilerOptions` (this is allowed because `noEmit` is already true). Run `cd frontend && npm ci`.

- [ ] **Step 2: Write the failing tests** (`node:test` + `node:assert/strict`):
  - `parses event and data`: `'event: place\ndata: {"a":1}\n\n'` gives `[{event:'place', data:'{"a":1}'}]`.
  - `joins several data lines with \n`: `'data: a\ndata: b\n\n'` gives `[{event:'message', data:'a\nb'}]`.
  - `ignores comments and blocks without data`: `': ping\n\nevent: x\n\n'` gives `[]`.
  - `CRLF and CR line ends`: `'event: a\r\ndata: 1\r\n\r\n'` and `'event: a\rdata: 1\r\r'` both give `[{event:'a', data:'1'}]`.
  - `strips one leading space only`: `'data:  x\n\n'` gives data `' x'`.
  - `every split position yields the same messages`: take a 3-event stream that includes `\r\n` and a comment, split it at every index i into `[s.slice(0,i), s.slice(i)]`, push both parts, and the result deep-equals the whole-chunk result.
  - `end flushes a last block without blank line`: `push('event: done\ndata: {}')` then `end()` gives one message.

- [ ] **Step 3: Run** `npm test`. Expected: FAIL (module not found).

- [ ] **Step 4: Implement `createSseParser` in `sse.ts`.** Field parsing follows the SSE spec, the same as `backend/scripts/detective_run.py:parse_sse`. To handle a `\r` at the end of a chunk, hold the trailing `\r` until the next chunk (or `end()`), so `\r\n` split across chunks counts as one line end.

- [ ] **Step 5: Run** `npm test` and `npm run typecheck`. Expected: PASS, clean.

- [ ] **Step 6: Commit** `test: node test runner and an SSE parser for the detective stream`.

---

### Task 2: Event types and the tolerant normaliser

**Files:**
- Create: `frontend/src/features/detective/events.ts`
- Test: `frontend/src/features/detective/__tests__/events.test.ts`

**Interfaces:**
- Consumes: `Verdict`, `Direction` (`import type` from `../../story/types`).
- Produces:
```ts
export type Bbox = [number, number, number, number]                 // west, south, east, north
export interface PlaceEvent { thread_id: string; follow_up: boolean; forked_from: string | null; id: string; name: string;
  lat: number; lon: number; bbox: Bbox; tags: string[]; site_id: string | null; years: [number, number] | null }
export interface ToolStart { id: string; tool: string; args: Record<string, unknown> }
export interface ToolDone { id: string; tool: string; summary: string; result: Record<string, unknown>; evidence_id: string | null }
export interface ToolFailed { id: string | null; tool: string; reason: string }
export type MapOp =
  | { op: 'show_layer'; layer_id: string; date: string | null; year: number | null; opacity: number }
  | { op: 'set_year'; year: number }
  | { op: 'show_before_after'; layer_id: string; year_a: number; year_b: number; before_url: string | null; after_url: string | null; bbox: Bbox | null }
  | { op: 'fly_to'; bbox: Bbox; pitch: number; bearing: number }
  | { op: 'show_footprint'; source: string; label: string; size: string; bbox: Bbox; approximate: true }
export type SuspectStatus = 'open' | 'supported' | 'hint' | 'ruled_out'
export interface Suspect { id: string; label: string; status: SuspectStatus; evidence: string[]; note: string; downgraded: string | null }
export interface BoardEvent { suspects: Suspect[]; n_tests: number; verdicts: Record<string, { verdict: Verdict; direction: Direction }> }
export interface NotMeasured { label: string; reason: string | null }
export interface AnswerEvent { text: string; checked: boolean; figures: string[]; source: string; not_measured: NotMeasured[] }
export interface DoneEvent { thread_id: string; n_tests: number; n_tests_branch: number | null; n_tool_calls: number | null }
export type DetEvent =
  | { kind: 'place'; data: PlaceEvent } | { kind: 'thinking'; data: { text: string } }
  | { kind: 'tool_start'; data: ToolStart } | { kind: 'tool_done'; data: ToolDone } | { kind: 'tool_failed'; data: ToolFailed }
  | { kind: 'map'; data: MapOp } | { kind: 'board'; data: BoardEvent } | { kind: 'answer'; data: AnswerEvent }
  | { kind: 'done'; data: DoneEvent } | { kind: 'error'; data: { message: string } }
export function parseEvent(name: string, data: unknown): DetEvent | null
export function parseSseMessage(m: SseMessage): DetEvent | null   // JSON.parse + parseEvent; bad JSON -> null
```

- [ ] **Step 1: Write the failing tests:**
  - `parses each documented shape`: one fixture per event kind, copied from the task-9 report (`place`, `thinking`, `tool_start`, `tool_done` with `evidence_id: "e1"`, `tool_failed` with `id: null, tool: "agent"`, the five map ops, `board`, `answer`, `done`, `error`). For each, `parseEvent(kind, fixture)?.kind === kind`.
  - `tolerates old and new payloads`:
    - `board` without `verdicts` gives `verdicts: {}`.
    - `board` with `verdicts: {t1: {verdict: 'real', direction: 'up'}}` keeps it.
    - `answer` without `not_measured` gives `[]`.
    - `not_measured: ['ndvi']` gives `[{label:'ndvi', reason:null}]`.
    - `not_measured: [{var_id:'ndvi', label:'Greenness', reason:'not here'}]` gives `[{label:'Greenness', reason:'not here'}]`.
    - `done` without `n_tests_branch` gives `null`.
    - Extra unknown keys are dropped without error.
  - `unknown things are null, not throws`: event name `'plan'` gives `null`, map `{op:'spin'}` gives `null`, `board` with `status: 'weird'` gives that suspect's status `'open'`, `tool_done` without `result` gives `result: {}`, and `place` without `bbox` gives `null`.
  - `map defaults`: `show_layer` without opacity gives `0.8`, `fly_to` without pitch/bearing gives `55`/`0`, and `show_before_after` without urls gives `before_url: null, after_url: null, bbox: null`.
  - `parseSseMessage on bad JSON is null`.

- [ ] **Step 2: Run** `npm test`. Expected: FAIL.

- [ ] **Step 3: Implement with zod in `events.ts`.** Use one schema per kind with `.catch()` / `.default()` for the defaults above, and `safeParse`. Any failure returns `null`. `not_measured` items: a string becomes `{label: s}`, an object becomes `label ?? name ?? var_id`.

- [ ] **Step 4: Run** `npm test`. Expected: PASS. **Step 5: Commit** `feat: typed and tolerant detective events`.

---

### Task 3: Board stamps and verdict lookup

**Files:**
- Create: `frontend/src/features/detective/board.ts`
- Test: `frontend/src/features/detective/__tests__/board.test.ts`

**Interfaces:**
- Produces:
```ts
export interface StampBeat { suspectId: string; label: string; status: 'supported' | 'ruled_out' | 'hint'; downgraded: string | null }
export const STATUS_WORDS: Record<SuspectStatus, { icon: string; text: string; meaning: string }>
export function stampsBetween(prev: BoardEvent | null, next: BoardEvent): StampBeat[]
export function verdictFor(testId: string | null | undefined, board: BoardEvent | null,
  fallback?: { verdict?: unknown; direction?: unknown }): { verdict: Verdict; direction: Direction } | null
```
Exact copy for `STATUS_WORDS`: supported `{icon:'✓', text:'SUPPORTED', meaning:'Its evidence holds after correcting for every test run.'}`, ruled_out `{icon:'✕', text:'RULED OUT', meaning:'Tested with enough years and no clear change.'}`, hint `{icon:'~', text:'HINT', meaning:'Points this way, but not strong enough yet.'}`, open `{icon:'○', text:'OPEN', meaning:'Not tested yet.'}`.

- [ ] **Step 1: Write the failing tests:**
  - `a new status is a beat`: open→supported gives one beat. Supported→supported gives none. A suspect that is new with `hint` gives a beat. A change to `open` gives no beat.
  - `downgrade travels with the beat`.
  - `verdictFor prefers the board's corrected verdict`: `board.verdicts.t1 = {verdict:'real',direction:'up'}` with fallback `{verdict:'unknown'}` gives real/up. Without a board entry it uses the fallback. An invalid fallback gives `null`.

- [ ] **Step 2–4:** Run (FAIL), implement, run (PASS). **Step 5: Commit** `feat: case board stamps in words and icons`.

---

### Task 4: Scene grouping

**Files:**
- Create: `frontend/src/features/detective/scenes.ts`
- Test: `frontend/src/features/detective/__tests__/scenes.test.ts` (fixtures in `__tests__/fixtures.ts`: `RUN_EVENTS`, a realistic run in the documented order, reused by later tasks)

**Interfaces:**
- Consumes: Task 2 types.
- Produces:
```ts
export type SceneKind = 'opening' | 'evidence' | 'context' | 'note' | 'ending' | 'error'
export type ToolState = 'running' | 'done' | 'failed' | 'unfinished'
export interface SceneTool { id: string; tool: string; args: Record<string, unknown>; state: ToolState; summary: string | null;
  result: Record<string, unknown> | null; evidenceId: string | null; reason: string | null }
export interface Scene { key: string; kind: SceneKind; question: string | null; tool: SceneTool | null; mapOps: MapOp[];
  stamps: StampBeat[]; note: string | null; complete: boolean }
export interface Investigation { place: PlaceEvent | null; scenes: Scene[]; board: BoardEvent | null; answer: AnswerEvent | null;
  done: DoneEvent | null; error: string | null; finished: boolean }
export const MAP_TOOLS: ReadonlySet<string>      // show_layer, set_year, show_before_after, fly_to, show_footprint, update_board
export const CONTEXT_TOOLS: ReadonlySet<string>  // profile_place, list_variables, land_cover_change, satellite_picture, solved_case
export function groupScenes(events: readonly DetEvent[], opts?: { ended?: boolean }): Investigation
```
- Consumes also: `StampBeat`, `stampsBetween` (Task 3).

Rules (these are the decisions; the tests pin them):
1. `place` creates scene `{key:'opening', kind:'opening'}`.
2. `thinking` holds its text as the pending question.
3. `tool_start` of a tool not in `MAP_TOOLS` creates a new scene (`context` if the tool is in `CONTEXT_TOOLS`, else `evidence`), with key = tool id and `question` = the pending text, which it then consumes. Parallel calls each get a scene, and only the first gets the question.
4. `tool_start` of a `MAP_TOOLS` tool creates no scene, unless a question is pending. In that case it creates a `note` scene (`key: 'note-<n>'`) that carries the question.
5. `tool_done` / `tool_failed` update the matching `SceneTool` by id (map-tool results are not shown). `tool_failed` with `id: null` creates a `note` scene with `note = reason`.
6. `map` appends the op to the **last** scene.
7. `board` sets `investigation.board` and appends `stampsBetween(previousBoard, board)` to the last scene.
8. `answer` creates `{key:'ending', kind:'ending'}`. `done` sets `done` and `finished`. `error` creates `{key:'error', kind:'error', note: message}` and sets `finished`.
9. `complete` = no tool, or tool state ≠ `running`. When `opts.ended` or `finished`, every `running` tool becomes `unfinished` (and so complete).
10. The function is pure: the same input gives a deep-equal output, and the input array is never mutated.

- [ ] **Step 1: Write the failing tests:**
  - `opening then one scene per non-map tool`: `RUN_EVENTS` gives scene kinds `['opening','context','evidence','evidence','ending']` (the fixture is written to give exactly that).
  - `thinking attaches to the first parallel call only`.
  - `map ops go to the last scene`: a `fly_to` after `get_series` lands in that scene's `mapOps`.
  - `map-only step with a question becomes a note scene`.
  - `agent failure becomes a note`: `tool_failed {id:null, tool:'agent', reason:'The model did not answer.'}` gives a note scene with that text.
  - `ended stream marks running tools unfinished`: `[place, tool_start]` with `{ended:true}` gives tool state `unfinished` and `complete: true`. Without `ended` it gives `running` and `complete: false`.
  - `error ends the investigation`.
  - `does not mutate its input` (deep-freeze the array).

- [ ] **Step 2: Run**: FAIL. **Step 3: Implement.** **Step 4: Run**: PASS. **Step 5: Commit** `feat: group the detective stream into scenes`.

---

### Task 5: Scene player reducer

**Files:**
- Create: `frontend/src/features/detective/player.ts`
- Test: `frontend/src/features/detective/__tests__/player.test.ts`

**Interfaces:**
- Consumes: `Scene` (Task 4).
- Produces:
```ts
export const DWELL_MS = { opening: 2500, note: 2500, context: 3500, evidence: 5000, ending: 0, error: 0, perStamp: 1500, catchUp: 1200 } as const
export interface PlayerState { index: number; enteredAt: number; paused: boolean; pinned: boolean }
export type PlayerAction =
  | { type: 'tick'; now: number; scenes: readonly Scene[] }
  | { type: 'pause' } | { type: 'resume'; now: number }
  | { type: 'goto'; index: number; now: number }            // the user looks back: pins
  | { type: 'live'; now: number; scenes: readonly Scene[] }  // back to the newest scene, unpins
  | { type: 'reset'; now: number }
export const INITIAL_PLAYER: PlayerState                   // {index:0, enteredAt:0, paused:false, pinned:false}
export function dwellMs(scene: Scene, backlog: number): number
export function playerReducer(s: PlayerState, a: PlayerAction): PlayerState
```
Rules:
- `dwellMs` = base by kind + `perStamp` × number of stamps. When `backlog ≥ 3` it returns `catchUp` (live runs catch up and never fall minutes behind).
- `tick` advances by one scene only when all of these hold: the player is not paused or pinned, the current scene is complete, a next scene exists, and `now − enteredAt ≥ dwellMs(current, scenes.length − 1 − index)`.
- `goto` clamps the index.

- [ ] **Step 1: Write the failing tests:**
  - `waits for an incomplete scene`: a running tool scene does not advance after 60 s.
  - `holds an evidence scene 5000 ms`: no move at 4999 ms, moves at 5000 ms.
  - `stamps add 1500 ms each`.
  - `catches up when 3 scenes wait`.
  - `pause and goto stop ticks; live jumps to the last scene and unpins`.
  - `never past the last scene`.

- [ ] **Step 2–4:** FAIL, implement, PASS. **Step 5: Commit** `feat: scene player paces the investigation`.

---

### Task 6: Map layer catalog, dates and tile URLs

**Files:**
- Create: `frontend/src/features/detective/map/types.ts`, `map/layerCatalog.generated.ts`, `map/catalog.ts`
- Test: `frontend/src/features/detective/__tests__/catalog.test.ts`

**Interfaces:**
- Produces:
```ts
// map/types.ts
export interface CatalogLayer { id: string; title: string; gibs_layer: string; kind: 'wmts'; format: string; tile_matrix_set: string;
  legend: { unit: string; min: number | null; max: number | null; colormap?: string };
  dates: { start: string; end: string; step: string; ongoing: boolean; years?: number[] };
  zones: string[]; source: string; resolution: string }
export interface CaseLayerRow { id: string; kind: string; title?: string; file?: string; file_pattern?: string; years?: number[];
  source?: { name?: string } | string; before?: { file: string; year: number }; after?: { file: string; year: number }; pixel_m?: number }
// map/catalog.ts
export function catalogLayer(id: string): CatalogLayer | null
export function dateFor(layer: CatalogLayer, when: { date?: string | null; year?: number | null }): string
export function tileUrl(layer: CatalogLayer, date: string): string
export function maxZoomOf(layer: CatalogLayer): number         // "GoogleMapsCompatible_Level9" -> 9
export const TERRAIN: { url: string; encoding: 'terrarium'; maxzoom: 15; exaggeration: 1.5; attribution: string }
export const GIBS_ATTRIBUTION = 'NASA GIBS'
```

- [ ] **Step 1: Generate the catalog** (it is committed, so the front build needs no Python):
```bash
cd backend && source .venv/bin/activate && python -c "import yaml,json;rows=yaml.safe_load(open('catalog/map_layers.yaml'))['layers'];print('// GENERATED from backend/catalog/map_layers.yaml. Do not edit: regenerate (see docs/superpowers/plans/2026-11-15-detective-front.md, Task 6).\nimport type { CatalogLayer } from \'./types.ts\'\n\nexport const LAYER_CATALOG: CatalogLayer[] = '+json.dumps(rows,indent=2,ensure_ascii=False))" > ../frontend/src/features/detective/map/layerCatalog.generated.ts
```

- [ ] **Step 2: Write the failing tests:**
  - `catalog matches the yaml`: read `../../../../../backend/catalog/map_layers.yaml` relative to the test (via `fs` and `import.meta.dirname`). Collect `id:` and `gibs_layer:` with the regexes `/^  - id: (\S+)/m` and `/^    gibs_layer: (\S+)/m`. The id → gibs_layer pairs deep-equal those of `LAYER_CATALOG` (12 layers today). This catches a drift after a YAML edit.
  - `dateFor`: true_colour `{year:2003}` gives `'2003-07-01'`; land_cover `{year:2023}` gives `'2023-01-01'`; night_lights `{year:2012}` gives `'2012-01-01'`; ndvi `{}` gives `'2026-10-01'` (dates.end); true_colour `{date:'2010-05-04'}` gives `'2010-05-04'`; any result later than `dates.end` is clamped to `dates.end`.
  - `tileUrl wmts`: true_colour on `'2003-07-01'` gives exactly `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/2003-07-01/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg`. A png layer ends in `.png`.
  - `tileUrl vector falls back to WMS png`: active_fires gives a URL starting `https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi?` that contains `LAYERS=MODIS_Combined_Thermal_Anomalies_All`, `FORMAT=image%2Fpng`, `TIME=` and the literal `{bbox-epsg-3857}` (same pattern as `investigate/InvestigateMap.tsx:wmsTiles`).
  - `maxZoomOf` gives 9 for true_colour and 6 for precipitation.

- [ ] **Step 3: Run**: FAIL. **Step 4: Implement.**
  - `dateFor`: a date is used as given. With a year, `annual` steps or a `years` list give `YYYY-01-01`, and every other step gives `YYYY-07-01` (GIBS snaps periodic layers to the period that holds the date). With nothing, use `dates.end`. Clamp to `[start, end]`.
  - `TERRAIN.url = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'`, `attribution = 'Relief: AWS Terrain Tiles (Mapzen), not a NASA product'`.

- [ ] **Step 5: Run**: PASS. **Step 6: Commit** `feat: map layer catalog for the detective, generated from the backend yaml`.

---

### Task 7: Map view reducer (context / evidence / comparison / vectors)

**Files:**
- Create: `frontend/src/features/detective/map/mapView.ts`
- Test: `frontend/src/features/detective/__tests__/mapView.test.ts`

**Interfaces:**
- Consumes: `MapOp`, `PlaceEvent`, `Investigation` and the Task 6 functions.
- Produces:
```ts
export type LayerRender = { type: 'tiles'; url: string; maxzoom: number } | { type: 'image'; url: string; bbox: Bbox }
export interface LayerView { key: string; layerId: string; title: string; source: string; resolution: string | null;
  legend: CatalogLayer['legend'] | null; render: LayerRender; opacity: number; role: 'context' | 'evidence'; year: number | null; date: string | null }
export interface CurtainView { layerId: string; title: string; source: string; left: LayerView; right: LayerView; yearA: number; yearB: number }
export interface FootprintView { source: string; label: string; size: string; bbox: Bbox; approximate: true }
export interface CameraView { bbox: Bbox; pitch: number; bearing: number; seq: number }
export interface MapView { place: { lat: number; lon: number; bbox: Bbox } | null; context: LayerView | null; evidence: LayerView | null;
  curtain: CurtainView | null; footprints: FootprintView[]; camera: CameraView | null; notes: string[] }
export interface CaseLayers { siteId: string; bbox: Bbox; rows: Record<string, CaseLayerRow> }
export interface MapContext { caseLayers: CaseLayers | null }
export const CONTEXT_LAYER_IDS: ReadonlySet<string>   // true_colour, true_colour_viirs, land_cover, base, base_hq, hillshade
export const EMPTY_VIEW: MapView
export function openingView(place: PlaceEvent): MapView
export function applyMapOp(view: MapView, op: MapOp, ctx: MapContext): MapView
export function mapViewAt(inv: Investigation, index: number, ctx: MapContext): MapView
```
Rules:
- `openingView` starts with context = `land_cover` at its last year (it has no clouds and explains the place; the 3D relief is always on) and camera = `{bbox: place.bbox, pitch: 50, bearing: 0, seq: 1}` (spec §5.5d "Context opens every investigation").
- `show_layer`: the op goes to context if its id is in `CONTEXT_LAYER_IDS`, else to evidence. It replaces that slot (DESIGN: one coloured layer at a time) and clears the curtain. The id is looked up first in the catalog and then in `ctx.caseLayers.rows`:
  - A case row with `file` gives `image` at `/sites/<siteId>/<file>` with the case bbox.
  - A `yearly` row gives `file_pattern` with `{YYYY}` set to the op year, or the last of its `years`.
  - An unknown id leaves the view unchanged and pushes the note `'A layer the map does not know was skipped.'` once.
- `set_year` re-renders evidence (or context when there is no evidence) for that year.
- `show_before_after`:
  - With both urls, the curtain is two `image` renders with `op.bbox ?? place.bbox`.
  - With a case row of kind `before_after`, use its `before.file` / `after.file`.
  - Otherwise the curtain is two tile renders, for `year_a` and `year_b`.
- `fly_to` sets the camera with `seq + 1`, and pitch is clamped to [0, 85].
- `show_footprint` adds the footprint, replacing any with the same `source`.
- `mapViewAt` folds the `mapOps` of `scenes[0..index]` over `openingView(inv.place)`. When `scenes[index].kind === 'ending'`, the camera pulls out to the place bbox grown 4× around its centre (clamped to valid degrees) with pitch 0 (spec §5.5b "the ending pulls the camera out").

- [ ] **Step 1: Write the failing tests:**
  - `opening shows land cover and flies in`.
  - `evidence replaces evidence, context stays`: show `ndvi` then `lst_day` leaves one evidence (`lst_day`) and context still `land_cover`.
  - `satellite pair becomes a curtain of two images` (op with `layer_id:'true_colour'` and both urls).
  - `catalog pair without urls becomes tile curtain`: the left URL contains `/2003-07-01/` and the right `/2023-07-01/`.
  - `case layers resolve to /sites files`: `trend_lst_day` in lake_mead gives `/sites/lake_mead/trend_lst_day.png`; `lst_gibs` with year 2010 gives `/sites/lake_mead/layers/lst_gibs/2010.png`.
  - `unknown layer is skipped with a note`.
  - `footprint replaces same source`.
  - `ending pulls out`: pitch 0, and the bbox width is 4× the place width.
  - `scrubbing back shows that scene's map`: `mapViewAt(inv, 1)` has no evidence even when scene 3 shows one.

- [ ] **Step 2–4:** FAIL, implement, PASS. **Step 5: Commit** `feat: the map is a function of the scene`.

---

### Task 8: Chart model per evidence scene

**Files:**
- Create: `frontend/src/features/detective/chart.ts`
- Test: `frontend/src/features/detective/__tests__/chart.test.ts`

**Interfaces:**
- Produces:
```ts
export interface ChartPoint { year: number; value: number }
export interface TrendLines { line: [ChartPoint, ChartPoint]; low: [ChartPoint, ChartPoint]; high: [ChartPoint, ChartPoint] }
export interface ChartModel { label: string; unit: string | null; points: ChartPoint[]; years: [number, number]; trend: TrendLines | null;
  verdict: { verdict: Verdict; direction: Direction } | null }
export function trendLines(points: ChartPoint[], slopePerDecade: number, ciLow: number | null, ciHigh: number | null): TrendLines
export function chartFor(inv: Investigation, scene: Scene): ChartModel | null
```
Rules:
- The points come from `result.chart` (entries with a non-finite value are dropped). For a scene whose result has `series_id` but no `chart` (`trend_test`, `years_needed`), take the points from the earlier scene whose `result.series_id` matches and which has a `chart`.
- `trend` exists only when `slope_per_decade` is finite and `too_short !== true`.
- The lines pass through the anchor (median year, median value) with slope `/10` per year, drawn from the first to the last year. `low` and `high` use `ci_low` and `ci_high`; when either is missing, both equal `line`.
- `verdict` = `verdictFor(result.test_id, inv.board, result)`.
- `label` = `result.label ?? result.var_id`.
- `compare` results have no chart (`null`). Their scene shows the two sides as text with stamps (Task 13).
- With fewer than 2 points the function returns `null`.

- [ ] **Step 1: Write the failing tests:**
  - `trendLines exact`: points `(2000,1),(2001,2),(2002,3)` with slope 10 and CI 0..20 give line `[(2000,1),(2002,3)]`, low `[(2000,2),(2002,2)]` and high `[(2000,0),(2002,4)]`.
  - `get_series scene charts its own points, no trend`.
  - `trend_test scene borrows the series points and adds the trend`.
  - `too short gives no trend line`.
  - `fewer than 2 points is null`.
  - `compare is null`.

- [ ] **Step 2–4:** FAIL, implement, PASS. **Step 5: Commit** `feat: a chart for every evidence scene`.

---

### Task 9: Targets, box validation, request body, HTTP error text

**Files:**
- Create: `frontend/src/features/detective/request.ts`
- Test: `frontend/src/features/detective/__tests__/request.test.ts`

**Interfaces:**
- Produces:
```ts
export type Target = { kind: 'point'; lat: number; lon: number } | { kind: 'box'; bbox: Bbox } | { kind: 'case'; siteId: string; name: string; bbox: Bbox }
export type DetectiveBody = { question: string; thread_id?: string; checkpoint_id?: string } & ({ lat: number; lon: number } | { bbox: Bbox } | { site_id: string })
export function wrapLon(lon: number): number
export function boxFromCorners(a: { lat: number; lon: number }, b: { lat: number; lon: number }): { ok: true; bbox: Bbox } | { ok: false; message: string }
export function requestBody(target: Target, question: string, opts?: { threadId?: string | null; checkpointId?: string | null }): DetectiveBody
export function messageForResponse(status: number, body: unknown): string
export function targetLabel(target: Target): string       // "Point 37.00, −4.50" | "Box 36.90–37.10 N, …" | case name
```
Exact messages:
- Across 180°: `"Boxes can't cross the 180° line yet. Draw it on one side."`
- No area (side < 0.01°): `"That box is too small. Drag a little wider."`
- Latitude is clamped to ±85.
- `messageForResponse`:
  - 422 with `detail[0].msg` gives that text with a leading `"Value error, "` removed.
  - A `detail` string (404, 422, 503) is shown as is, unless it matches `/traceback|exception|error \d{3}/i`, in which case the generic text is shown.
  - Status ≥ 500 gives `"The investigation failed on the server. Try again in a moment."`.
  - Anything else gives `"This place or question could not be investigated. Pick another point and try again."`.

- [ ] **Step 1: Write the failing tests:**
  - `box across the antimeridian is refused` (corners at lon 179 and −179 after `wrapLon`).
  - `tiny box is refused`.
  - `corners in any order give w<e, s<n`.
  - `poles are clamped`.
  - `bodies`: a point gives `{question, lat, lon}`, a box gives `{question, bbox}`, a case gives `{question, site_id}`. `threadId` and `checkpointId` are added only when set. The question is trimmed.
  - `pydantic prefix is stripped`.
  - `server traces never shown`.

- [ ] **Step 2–4:** FAIL, implement, PASS. **Step 5: Commit** `feat: detective request building and plain error text`.

---

### Task 10: Run reducer and the fetch wrappers

**Files:**
- Create: `frontend/src/features/detective/runState.ts`, `frontend/src/features/detective/api.ts`
- Test: `frontend/src/features/detective/__tests__/runState.test.ts`

**Interfaces:**
- Produces:
```ts
// runState.ts
export type RunStatus = 'idle' | 'connecting' | 'streaming' | 'finished' | 'stopped' | 'cut' | 'failed'
export interface RunState { status: RunStatus; mode: 'live' | 'replay'; events: DetEvent[]; message: string | null; threadId: string | null }
export type RunAction = { type: 'start'; mode: 'live' | 'replay'; keepThread: boolean } | { type: 'event'; event: DetEvent }
  | { type: 'end' } | { type: 'stop' } | { type: 'fail'; message: string } | { type: 'reset' }
export const IDLE_RUN: RunState
export function runReducer(s: RunState, a: RunAction): RunState
export const CUT_MESSAGE = 'The connection closed before the investigation finished. The steps so far are kept. Try again.'
export const STOP_MESSAGE = 'You stopped the investigation. The steps so far are kept.'
// api.ts (browser only, no unit test; API_URL from '../explore/api')
export async function streamDetective(body: DetectiveBody, onEvent: (e: DetEvent) => void, signal: AbortSignal): Promise<void>
export interface HistoryStep { checkpoint_id: string; step: number; kind: string; tool: string | null; summary: string; n_tests: number; created_at: string }
export async function fetchHistory(threadId: string, signal: AbortSignal): Promise<HistoryStep[]>
export async function fetchRecording(name: string, signal: AbortSignal): Promise<Recording>     // GET /recordings/<name>.json
export async function fetchCaseLayers(siteId: string, signal: AbortSignal): Promise<Record<string, CaseLayerRow>>  // /sites/<id>/layers.json
```
Rules:
- `start` clears the events and keeps `threadId` only when `keepThread`.
- The first `event` moves `connecting` to `streaming`. `place` and `done` set `threadId`.
- `end` gives `finished` when the events contain a `done` or `error`, else `cut` with `CUT_MESSAGE`.
- `stop` gives `stopped` with `STOP_MESSAGE` and no effect once finished.
- `fail` gives `failed` with the message.
- `streamDetective` does a POST with `accept: text/event-stream`, uses Task 1's parser and `parseSseMessage`, and throws `FriendlyError(messageForResponse(...))` on a non-OK response. A network failure throws "We couldn't reach the investigator. Check your connection (or that the backend is running) and try again." It rethrows on abort.

- [ ] **Step 1: Write the failing tests:**
  - `end without done is cut`.
  - `end after done is finished`.
  - `stop after finished changes nothing`.
  - `thread id follows the place event`.
  - `follow-up keeps the thread, new case drops it`.

- [ ] **Step 2–4:** FAIL, implement `runState.ts`, PASS. Then write `api.ts`. **Step 5:** `npm run typecheck` clean. **Step 6: Commit** `feat: detective run state and API calls`.

---

### Task 11: Recordings reach the front, and the replay schedule

**Decision:** recordings are copied by a sync script into `frontend/public/recordings/` (gitignored, like `public/sites`). There is no backend static route. Replay is the demo's safety net (spec §5.6), so it must work with the backend down or unreachable from the venue Wi-Fi, and from a static deploy. It also follows the pattern the repo already has (`sync-sites.mjs`), and `backend/data/recordings/` stays the source of truth (it is committed, only `backend/data/detective/` is ignored).

**Files:**
- Create: `frontend/scripts/sync-recordings.mjs`, `frontend/src/features/detective/replay.ts`
- Modify: `frontend/package.json` (`"sync-recordings": "node scripts/sync-recordings.mjs"`, `"predev": "npm run sync-sites && npm run sync-recordings"`, the same for `prebuild`), `frontend/.gitignore` (`/public/recordings`)
- Test: `frontend/src/features/detective/__tests__/replay.test.ts`

**Interfaces:**
- Produces:
```ts
export const RECORDING_NAME: RegExp            // /^[a-z0-9][a-z0-9_-]{0,63}$/
export interface Recording { question: string; request: Record<string, unknown>; started_at: string; events: { t_ms: number; event: string; data: unknown }[] }
export interface RecordingChip { name: string; question: string; started_at: string }
export function parseRecording(raw: unknown): Recording | null
export function replaySchedule(rec: Recording, maxGapMs?: number): { atMs: number; event: DetEvent }[]   // default 6000
export function targetFromRequest(req: Record<string, unknown>): Target | null
```
Rules:
- The gaps between consecutive `t_ms` are capped at `maxGapMs`. A negative gap counts as 0, so the result is never decreasing. Events whose `parseEvent` is null are dropped. The recording keeps real timing up to the cap: long tool waits are shortened so the demo does not stall. The scene player still sets the reading pace.
- `targetFromRequest` maps `site_id` to a case, `bbox` to a box and `lat`/`lon` to a point (it drives the map pick in replay).
- `sync-recordings.mjs` copies `../../backend/data/recordings/*.json` and writes `index.json` = `RecordingChip[]` sorted by name. Only files whose name matches `RECORDING_NAME` and whose JSON has `question` and `events` are copied (others get a `console.warn`). A missing folder exits 0 with a warning, like `sync-sites.mjs`.

- [ ] **Step 1: Write the failing tests:**
  - `rejects names outside the pattern`: `'../x'`, `''`, `'Vinuela'`, `'a/b'` and `'a.json'` fail; `'vinuela'` and `'lake-mead_2'` pass.
  - `caps gaps`: t_ms `[0,100,20000,20100]` gives atMs `[0,100,6100,6200]`.
  - `never goes back in time` (t_ms `[0,500,300]` gives `[0,500,500]`).
  - `drops unknown events`.
  - `bad recording is null` (no `events` array).
  - `target from request` (all three kinds).

- [ ] **Step 2–4:** FAIL, implement `replay.ts`, PASS.

- [ ] **Step 5: Write the sync script.** Run `npm run sync-recordings`. Expected: `[sync-recordings] N recordings -> public/recordings` (N may be 0 until Task 10 of the core plan records runs).

- [ ] **Step 6: Commit** `feat: recorded runs are synced into public and scheduled for replay`.

---

### Task 12: The map component (globe, terrain, picking, layers, curtain)

**Files:**
- Create: `frontend/src/features/detective/DetectiveMap.tsx`, `CurtainMap.tsx`, `LayerLegend.tsx`
- Create: the map part of `frontend/src/features/detective/detective.module.css`

**Interfaces:**
- Consumes: `MapView` (Task 7), `TERRAIN` and the catalog (Task 6), `Target` and `boxFromCorners` (Task 9), `STYLE` (`../explore/mapStyle`).
- Produces:
```ts
export type PickMode = 'point' | 'box'
export interface DetectiveMapProps { view: MapView; target: Target | null; pickMode: PickMode; pickEnabled: boolean;
  onPick: (result: { target: Target } | { error: string }) => void; reducedMotion: boolean }
export default function DetectiveMap(props: DetectiveMapProps): JSX.Element
export function CurtainMap(props: { curtain: CurtainView; camera: { center: [number, number]; zoom: number; pitch: number; bearing: number } }): JSX.Element
export function LayerLegend(props: { view: MapView }): JSX.Element | null
```
What each piece must do (follow `features/investigate/InvestigateMap.tsx` for the lifecycle: dynamic `import('maplibre-gl')`, a `ready` flag, a prefix registry, signature-diffing of layers):
- Style: `{...STYLE, projection: {type: 'globe'}}`.
- On `load`, add the `raster-dem` source `det-dem` from `TERRAIN` and call `map.setTerrain({source: 'det-dem', exaggeration: 1.5})`. If the DEM errors, call `setTerrain(null)` and show the line "Relief could not load; the map is flat." Add `NavigationControl({visualizePitch: true})` and `maxPitch: 85`.
- Layers, below `'borders'`:
  - context and evidence as `raster` layers (`tiles` + `maxzoom` + `attribution: GIBS_ATTRIBUTION`, or an `image` source);
  - footprints as a `geojson` bbox polygon with a dashed outline and a symbol label `"<label> · approximate"`;
  - the picked target as a marker (point) or an outline (box).
  Raster paint uses `raster-resampling: 'linear'` (DESIGN: smooth at the data's own resolution).
- Camera: when `view.camera.seq` changes, call `fitBounds(bbox, {pitch, bearing, padding, duration: reducedMotion ? 0 : 2200})`. The left padding is 40% of the width at ≥ 1100 px, as in `InvestigateMap`.
- Picking:
  - In point mode one click/tap calls `onPick({target:{kind:'point', lat, lon}})` with `wrapLon`.
  - In box mode the first tap shows "Tap the opposite corner" and the second tap calls `boxFromCorners`. Escape cancels.
  - When `pickEnabled` is false (a run is streaming), clicks are ignored and the cursor is `default`.
- Curtain: when `view.curtain` is set, render `<CurtainMap>`, a second `maplibregl.Map` (`interactive: false`, same style without terrain) absolutely positioned over the first. It is clipped with `clip-path: inset(0 0 0 <split>%)`, and the main map's camera syncs it on `move`. A full-height `<input type="range">` (≥ 44 px wide thumb, `aria-label="Slide between <yearA> and <yearB>"`) drives the split. Year labels sit in the two corners.
- `LayerLegend`: the evidence (or context) title; the unit with `min`–`max` when both are present; `source`; `"<resolution> pixels, smoothed for display"`; the line `TERRAIN.attribution + " · Heights ×1.5"`; the curtain's two years. It is folded by default (DESIGN: "Panels start folded") behind a 48 px "Layer and source" text button.
- Failure: the style or tiles fail → `role="alert"` "The map could not load. Check your connection and reload. You can still watch a recorded case."

- [ ] **Step 1: Implement the three components.**
- [ ] **Step 2:** `npm run typecheck` clean. `npm run build` succeeds (the route that mounts the map comes in Task 14, so build only proves it compiles).
- [ ] **Step 3: Commit** `feat: detective map with globe, 3D relief, picking and a curtain`.

---

### Task 13: Reading-column components

**Files:**
- Create: `frontend/src/features/detective/QuestionBox.tsx`, `ScenePanel.tsx`, `SceneChart.tsx`, `CaseBoard.tsx`, `AnswerPanel.tsx`, `StepList.tsx`, `HistoryList.tsx`
- Modify: `frontend/src/features/detective/detective.module.css`

**Interfaces:**
- Consumes: Tasks 3, 4, 8, 9 and 10 (stamps, scenes, chart, request, run state). `Stamp` comes from `../../lib/Stamp` (verdict stamps), and `fmt` from `../../lib/cases` (formatting only, no derivation).
- Produces:
```ts
QuestionBox(props: { target: Target | null; status: RunStatus; mode: 'live' | 'replay'; followUp: boolean; forkFrom: HistoryStep | null;
  initialQuestion: string; onAsk: (question: string) => void; onStop: () => void; onCancelFork: () => void; onPickMode: (m: PickMode) => void; pickMode: PickMode })
ScenePanel(props: { inv: Investigation; scene: Scene; chart: ChartModel | null })
SceneChart(props: { model: ChartModel })
CaseBoard(props: { board: BoardEvent | null; beats: StampBeat[] })
AnswerPanel(props: { answer: AnswerEvent; done: DoneEvent | null })
StepList(props: { inv: Investigation; index: number; pinned: boolean; onGoto: (i: number) => void; onLive: () => void })
HistoryList(props: { threadId: string | null; enabled: boolean; onFork: (step: HistoryStep) => void })
```
Exact copy and behaviour:
- **QuestionBox**
  - With no target: "Click a point or draw a box on the globe, then ask in plain words." Two 48 px toggles, "Point" and "Box" (`aria-pressed`).
  - The textarea placeholder is "Is it getting hotter here? Is the water going down?" with `maxLength` 400.
  - The primary button is "Investigate" ("Ask" when `followUp`). It is disabled with a visible reason ("Pick a place first" / "Write a question") rather than silently.
  - While `connecting` it reads "Opening the case…". While `connecting`/`streaming` a "Stop" button replaces it.
  - With `forkFrom`: "Re-running from step <step>: <summary>" and a "Cancel" text button.
  - In replay mode the question is read-only, with the line "Replay of a recorded run · recorded <date from started_at>" and a "Run it live" link to `/detective`.
- **ScenePanel**
  - Shows the question line (`scene.question`).
  - Then a plain tool label, never the raw tool name. The map is `get_series` → "Fetching the record", `trend_test` → "Is it real?", `climate_residual` → "Is it the climate?", `correlate` → "Do they move together?", `compare` → "Same thing, two places", `land_cover_change` → "Has the land changed?", `satellite_picture` → "Then and now", `profile_place` → "What kind of place is this?", `list_variables` → "What can be measured here?", `years_needed` → "How many years would it take?", `solved_case` → "A solved case". Any other tool → "Checking the data".
  - Then `summary`, then `<SceneChart>` when `chart` is set, then a verdict `Stamp` when `chart.verdict`. Compare scenes show both sides' place/years lines with their stamps.
  - States: running → "Checking…" with `aria-live="polite"`; failed → "✕ Could not check: <reason>"; unfinished → "Did not finish".
  - Note scenes show `note`. The error scene shows the message and a "Try again" button.
- **SceneChart**: an SVG with `role="img"` and an `aria-label` of `<label>, <first year>–<last year>`. It draws the annual points and line in `--ink`, the CI band as a polygon between `low` and `high` at 18% ink, and the trend `line` dashed. It labels only the first and last years, and the min and max point values with `unit` via `fmt`. The legend line reads "Yearly values · dashed: trend line · band: its likely range".
- **CaseBoard**
  - One row per suspect: `STATUS_WORDS[status]` as `icon + text` in a stamp-style box (solid for supported, outline for hint, dashed for ruled out, tertiary for open), the label, the note, and the `downgraded` text in tertiary.
  - New beats (`beats`) get the CSS class `.stampIn`, a 400 ms scale-in that `prefers-reduced-motion` turns off.
  - It is folded on mobile behind a "Case board (N suspects)" button.
  - Empty: "No suspects yet. They appear as the detective tests them."
- **AnswerPanel**
  - Shows `answer.text`.
  - Then "A clue, not proof." (always).
  - Then the check line. If `checked` is true: "✓ every figure checked · <done.n_tests> tests run". Otherwise: "Not every figure could be checked · <n> tests run". Only the n_tests part is dropped when `done` is null.
  - Then, if `not_measured.length`, a heading "Not measured here" with one item per entry (`label — reason`).
  - When `answer.source === 'template'`: "The plain summary, written from the results without the language model."
- **StepList**
  - One 44 px row per scene (icon by state ✓ / … / ✕ and the tool label). The current scene is `aria-current="step"`.
  - Clicking a row calls `onGoto`. When `pinned`, a "Back to live" button calls `onLive`.
- **HistoryList**
  - It is enabled only when the run is finished, live, and `threadId` is set. It fetches with `fetchHistory`.
  - Rows show "Step <step> · <summary>" with a 44 px "Re-run from this step" button that calls `onFork`.
  - States: loading "Loading the steps…", error = the friendly message, and empty "No steps to re-run yet."

- [ ] **Step 1: Implement.** CSS tokens only from `globals.css`. Square corners, no accent colour, ≥ 44 px targets.
- [ ] **Step 2:** `npm run typecheck` clean.
- [ ] **Step 3: Commit** `feat: detective reading column: scene, chart, board, answer, steps, history`.

---

### Task 14: Hooks, `/detective` route and wiring

**Files:**
- Create: `frontend/src/features/detective/useDetectiveRun.ts`, `useScenePlayer.ts`, `DetectiveView.tsx`, `frontend/src/app/detective/page.tsx`
- Modify: `frontend/src/features/detective/detective.module.css` (layout)

**Interfaces:**
- Consumes: everything above. `readCases` comes from `../../lib/readSites` (server only).
- Produces:
```ts
export function useDetectiveRun(): { run: RunState; inv: Investigation;
  start: (target: Target, question: string, opts?: { followUp?: boolean; checkpointId?: string }) => void;
  stop: () => void; replay: (name: string) => void; reset: () => void }
export function useScenePlayer(inv: Investigation): { state: PlayerState; scene: Scene | null; goto: (i: number) => void;
  live: () => void; pause: () => void; resume: () => void }
export interface CaseChip { id: string; name: string; bbox: Bbox }
export default function DetectiveView(props: { cases: CaseChip[]; recordings: RecordingChip[]; initialSite?: string; replay?: string }): JSX.Element
// page.tsx: export const metadata = { title: 'Your case · Earth Trend Detective', description: 'Pick any place on Earth, ask in plain words, and watch the detective test it with NASA data, scene by scene.' }
// export default async function DetectivePage({ searchParams }: { searchParams: Promise<{ replay?: string; site?: string }> })
```
Wiring rules:
- `useDetectiveRun`:
  - It holds `useReducer(runReducer)` and computes `inv = useMemo(() => groupScenes(run.events, {ended: status in ['stopped','cut','failed']}))`.
  - `start` aborts any previous run and builds the body with `requestBody(target, q, {threadId: followUp ? run.threadId : null, checkpointId})`. It calls `streamDetective`, dispatches `end` on resolve, `fail` on a `FriendlyError`, and nothing on abort, because `stop` already dispatched.
  - `replay` validates `RECORDING_NAME`, runs `fetchRecording` and `replaySchedule`, then one `setTimeout` per event; `stop`/unmount clears them. A bad name or a 404 gives `fail('This recording is not available.')`.
- `useScenePlayer` dispatches `tick` every 250 ms while not finished-and-at-the-end. It resets when a new run starts (the opening scene key changes).
- `DetectiveView` layout (DESIGN Instrument):
  - The map is full bleed. The reading column is on the left over the scrim at ~38% on ≥ 1100 px. Below 1100 px the map is on top (`55svh`) and the column follows.
  - Top bar: wordmark link to `/`, and the quiet text link "Watch a recorded case" (a menu of `recordings`, hidden when there are none).
  - Column order: QuestionBox → ScenePanel (current scene) → CaseBoard → AnswerPanel (when the current scene is `ending`) → StepList → HistoryList (after finish).
  - The map gets `mapViewAt(inv, player.index, {caseLayers})`. `caseLayers` is fetched with `fetchCaseLayers` when `place.site_id` is set.
  - Picking a new target while finished resets the run (a new case). A follow-up uses the same target.
  - The beats passed to `CaseBoard` are the current scene's `stamps`.
- URL params:
  - `?site=<id>` preselects that case target (from `cases`). If the id is unknown, nothing is preselected and nothing is shown.
  - `?replay=<name>` starts the replay on mount.
- Mount the map with `next/dynamic` and `ssr: false`, using the loading text "Loading the globe…".
- `page.tsx` reads `cases` via `readCases()` and maps them to `CaseChip`. It reads `public/recordings/index.json` with `fs` in a try/catch (missing gives `[]`). It passes `replay` / `site` through (awaiting `searchParams` already makes the route dynamic).
- Case chips: under the question box when there is no target, "Or open a solved case:" with three 44 px chips.

- [ ] **Step 1: Implement.**
- [ ] **Step 2:** `npm run typecheck` and `npm run build`. Expected: clean, with `/detective` in the route list.
- [ ] **Step 3: Smoke run with the backend.** Run `cd backend && source .venv/bin/activate && uvicorn app.main:app --port 8766` (8000 is taken), then `cd frontend && NEXT_PUBLIC_API_URL=http://127.0.0.1:8766 npm run dev`. Open `http://127.0.0.1:5180/detective`, click near La Viñuela (36.87, −4.17) and ask "Is the reservoir going down?". Expected: the opening fly-in, scenes advancing, stamps, the ending with the check line. With no LLM key, expect the error scene with "The investigator needs a language model key on the server." and no stack trace.
- [ ] **Step 4: Commit** `feat: /detective route plays live and recorded investigations`.

---

### Task 15: Landing hooks consistent with the three acts

**Files:**
- Modify: `frontend/src/app/page.tsx:47-66`, `frontend/src/app/landing/CoverReel.tsx:107-110`, `frontend/src/story/StoryApp.tsx:464`, `frontend/src/features/explore/ExploreView.tsx:107`

Exact changes:
- Cover "own" section (the end of Act 2, the hook into Act 3):
  - Title: "Three places, three answers. Now pick yours."
  - Paragraph: "Click anywhere on the globe and ask in plain words. The detective picks the NASA records that fit the place, tests each one, and shows you what it found, scene by scene."
  - Primary `Link href="/detective"`: "Investigate anywhere".
  - Keep the quiet "Or browse the map" link.
- CoverReel quiet link: `href="/detective"`, text "Investigate anywhere".
- StoryApp: `href={`/detective?site=${caseId}`}`, label unchanged. This touches one href only; the story mode is otherwise untouched (spec §5.5).
- ExploreView: the link goes to `/detective`.

- [ ] **Step 1: Edit.**
- [ ] **Step 2:** `npm run typecheck`, `npm run build`. `grep -rn '"/investigate' src | grep -v features/investigate` prints nothing.
- [ ] **Step 3: Commit** `feat: the cover and the cases lead into your own case`.

---

### Task 16: Visual check against DESIGN.md and the UX checklist

**Files:** none new. Fix whatever this pass finds, in the files of Tasks 12–14.

- [ ] **Step 1: Render and inspect** with a browser (chrome-devtools MCP or claude-in-chrome), dev server on `127.0.0.1:5180`. For remote viewing, bind to the Tailscale IP and avoid ports 3000/8000/8010. Check:
  - Desktop 1440×900 and mobile 390×844.
  - The empty state.
  - Box mode.
  - A live run (or a replay) at the opening, an evidence scene with a chart, a stamp beat, the curtain, a footprint and the ending.
  - The error states: backend down → "We couldn't reach the investigator…"; `?replay=nope` → "This recording is not available."; a stopped run; and the map offline (block `gibs.earthdata.nasa.gov`).
- [ ] **Step 2: Walk `docs/UX-CHECKLIST.md`** item by item:
  - one primary action per screen;
  - text ≥ 16 px;
  - no "Mann-Kendall", "p-value" or "FDR" in the main UI;
  - stamps readable in greyscale (DevTools "emulate achromatopsia");
  - every tap target ≥ 44 px, measured;
  - every action has a visible response;
  - no "undefined", "null", "NaN" or "Error 500" on screen in any state;
  - no `_example` figures.
- [ ] **Step 3: Check reduced motion** (DevTools emulation): the camera jumps, stamps do not scale, and scenes still advance.
- [ ] **Step 4:** `npm test`, `npm run typecheck`, `npm run build`, all green. Record in the commit body what was checked and anything that was not.
- [ ] **Step 5: Commit** `fix: detective screen passes the visual and UX checks`.

---

## Notes for the executor

- `done.n_tests` is the size of the thread-wide correction family (fix wave) and is the number shown. `n_tests_branch` is parsed but not shown (YAGNI).
- The cases use the AWS relief too. NASADEM ships per case as a single `heightmap_rgb.png`, not as tiles, and `raster-dem` needs tiles. Do not add a per-case DEM after 13:00 (spec §8 freeze). The legend says which relief is shown.
- Cut order if late (spec §8): Task 12's curtain → plain toggle between the two years; terrain → flat globe (`setTerrain(null)`). Never cut: the scene player, board stamps, the answer check line, replay.
