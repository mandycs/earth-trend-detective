# Earth Trend Detective — the detective agent (design)

> Internal, in Spanish where it matters to the team; product text in English.
> Date: 2026-11-15 (night). Owner: Mandy + Claude (+ subagents). Freeze: Sun 15 Nov 16:00 Málaga.

## 1. Intent — why

The pitch sells: *a journalist or a high-school student asks in everyday language, an LLM turns it into
real calls to NASA data tools, runs them, reads the results, decides what to check next and concludes in
plain English with every figure checked.* Today that is not true: `backend/app/investigate/` is a one-shot
planner (the LLM picks 3–6 step ids from a closed menu, the code runs them in fixed order, the LLM never sees
a result). This design makes the claim true.

It is also the challenge itself ("Be an Earth System Trend Detective"): the same variable rises in one region
and falls in another, so the variables to examine **depend on the place**, and the job is to separate
signals, not to chart one variable.

## 2. Goals

1. **Real tool calling** with LangGraph: the model calls a tool, sees its result, decides the next call,
   loops until it can conclude. Multi-turn (follow-up questions keep context).
2. **Variables depend on the place**: the agent profiles the place (land cover, elevation, snow, water),
   gets the catalog variables that apply there (`backend/catalog/variables.yaml`, `applies_to`), and
   examines them, not only the one the user suspects.
3. **Detective behaviour**: a visible *case board* of suspects (open / supported / ruled out), each with the
   evidence that moved it.
4. **Draws on the map**: the agent puts layers on a MapLibre 3D map (terrain + GIBS layers + our analysed
   layers for the three cases) and flies to the area.
5. **Honest statistics across the whole investigation** (see §6): every trend test the agent runs is logged
   and FDR-corrected over the session; resolution of each source is stated.
6. **Demo**: real investigations recorded (their SSE stream) and replayed in the pitch; live run as a bonus.

## 3. Non-goals (tonight)

- Geocoding / place names. **The user gives the location** by clicking a point or drawing a box on the map.
- Any GIBS layer by free id. Only a curated catalog (§5.3).
- New AppEEARS / LP DAAC pipelines. Live tools use POWER, GRACE, GLDAS and GIBS only.
- Rewriting the 3D story mode (three.js diorama). It stays as the documentary mode; only honesty fixes.
- RAG.

## 4. Anti-goals (failure even if it "works")

- A figure on screen that did not come out of a tool result.
- Causal language ("proof", "caused by", "the part that is us"). The climate residual is a **clue**.
- "Real" verdicts that only survive because the agent tested many things and reported the lucky one.
- Answering about "my town" without saying the data are regional (GRACE ~300 km, POWER ~50 km, GIBS LST 5.6 km).
- A chatbot with tools and no case board: then it is Earth Copilot with less budget.

## 5. Design

### 5.1 Approaches considered

| Approach | Trade-off | Decision |
|---|---|---|
| **LangGraph agent with tool calling** | Real loop, memory (checkpointer) and streaming built in; new dependency; LLM quality needs tuning | **Chosen** (Mandy) |
| Own loop on the Anthropic/OpenRouter SDK | ~100 lines, fewer deps; no checkpointer/streaming for free, can't say "LangGraph" | Fallback only |
| Current planner in two rounds | Cheapest; still not tool calling | Rejected: it is what we stop selling |

### 5.2 Backend: `backend/app/detective/`

- **Graph** (LangGraph `StateGraph`): `agent` node (chat model with tools bound) ⇄ `tools` node (`ToolNode`),
  conditional edge on tool calls; then `conclude` node: narrator + existing validator
  (`app/explain/validator.py`) checking every number against the **tool-result ledger**; one retry, then
  template. Checkpointer `MemorySaver` keyed by `thread_id` for follow-ups.
- **State**: messages; `place` (lat/lon/bbox, tags); `ledger` (every tool result with its numbers, source,
  resolution); `tests` (every trend/correlation test run: variable, period, p); `board` (suspects with status
  and evidence ids); `layers` (what is on the map).
- **Limits**: configurable, generous in the product (`DETECTIVE_MAX_TOOL_CALLS`, default 40;
  `DETECTIVE_MAX_SECONDS`, default none); the user can stop the run from the UI. Per-tool timeout and cache.
- **Model**: `claude-sonnet-5-5` for the agent loop. Via `langchain-anthropic` when `LLM_API_KEY` is set,
  else `langchain-openai` `ChatOpenAI` against OpenRouter (`~/.secrets/openkey`, `anthropic/claude-sonnet-5.5`).
  Same key rules as `app/explain/llm.py`; keys never logged or sent to the browser.
- **Endpoint**: `POST /detective` (SSE), body `{question, lat, lon | bbox | site_id, thread_id?}`.
  Keep `/investigate` working until the front switches.

### 5.3 Tools (all wrap existing code unless marked NEW)

| Tool | Does | Backed by |
|---|---|---|
| `profile_place(lat, lon, bbox?)` | Land-cover shares + tags, elevation, snow/water hints | `investigate/landcover.py`, NASADEM |
| `list_variables(tags)` | Catalog variables that apply here, with source and resolution | `catalog.py` (`applies_to`) |
| `get_series(var, place, start?, end?)` | Monthly/annual series of any catalog variable | `gather.py` fetchers (POWER, GRACE, GLDAS); GIBS yearly values at any point — **NEW** (generalise `assets/gibs_layers.py` from per-site to on-demand bbox) |
| `trend_test(var, period?)` | MK Hamed-Rao + Sen + CI on the series, whole period or a window | `stats/trend.py`; logs to `tests` |
| `climate_residual(target, drivers)` | Share not explained by the chosen climate drivers, with range across models | `stats/residual.py` |
| `correlate(a, b, lags?)` | Year-on-year change correlation with lags 0–2, out-of-sample skill | `stats/lineup.py` |
| `compare(var, place_a/period_a, place_b/period_b)` | Same variable, two places or two periods | trend + series — small NEW glue |
| `land_cover_change(place, years)` | Share change of cropland, urban, water, forest… | `landcover.py` (GIBS MCD12Q1) |
| `years_needed(var)` | Years of data needed to tell | `stats/years.py` |
| `satellite_picture(bbox, year)` | Clearest-day true-colour picture URL | `investigate/thennow.py` |
| `solved_case(site_id)` | Precomputed facts for Lake Mead / Aletsch / Doñana | `sites/<id>/site.json` |
| `show_layer(layer_id, date?, opacity?)` / `fly_to(bbox, pitch?)` | Map instructions, streamed to the front | curated catalog — **NEW** `catalog/gibs_layers.yaml` (~20 GIBS layers: true colour, NDVI, LST, snow, land cover, night lights, fires, precipitation…, each with legend, unit, valid dates, source) + the cases' `layers.json` |
| `update_board(suspect, status, evidence_ids, note)` | Writes the case board | graph state |
| `sea_series(var, place)` — **NEW** | Sea surface temperature (NASA JPL MUR, ~1 km, 2002–), chlorophyll-a (NASA MODIS Aqua), degree heating weeks / bleaching alerts (NOAA Coral Reef Watch, labelled non-NASA) for points on water or coast | NOAA ERDDAP griddap (no auth); tags `ocean`, `coast`, `reef` added to the catalog so `list_variables` offers them |
| `water_extent(bbox, years)` — **NEW** | Yearly open-water area of a reservoir or lake from NDWI on HLS 30 m (2013–) | `assets/composite.py` HLS access; validation where an official series exists (USBR, MITECO) |

Tool descriptions are written for the model (when to use, what it returns, resolution caveat). Tool results
are compact JSON (no raw series to the model; series stay server-side, the model gets stats + ids).

### 5.4 SSE contract (front ↔ back)

Events: `place` · `thinking` (one short line, why the next call) · `tool_start {id, tool, args}` ·
`tool_done {id, summary, result, layer?}` · `tool_failed {id, reason}` · `map {show_layer|fly_to}` ·
`board {suspects[]}` · `answer {text, checked: true|false, figures[]}` · `done {thread_id, tests, stats}`.
Superset of today's `/investigate` events so the front can reuse its step list.

### 5.5 Front: detective screen (Instrument mode)

- MapLibre 5.24 (already installed): globe + **3D terrain** (`setTerrain`, `raster-dem` from AWS Terrain
  Tiles — public, no key, labelled non-NASA; NASADEM for the three cases), layer stack with opacity and
  legend + source per layer, applying `map` events.
- Left panel: question box (location must be picked first), live step list, case board, answer with
  "every figure checked" mark, follow-up box, stop button.
- Story mode (three.js) untouched.

### 5.5b The web is a story in three acts (Mandy, decided)

The tool is judged later; the pitch has to make people want to try it. So the web is storytelling, like the
hero video (`video/hero`), and **the investigation itself is told as a story**.

1. **Act 1 · Hook** — the hero (Lake Mead → Aletsch → Doñana, one figure per shot, "Is it the climate?",
   "A clue, not proof.").
2. **Act 2 · Three solved cases** — current 3D story mode (What is changing? → Is it real? → Is it the
   climate?), closing on "Three places, three answers. Now pick yours."
3. **Act 3 · Your case (climax)** — click the globe, ask in plain words, the investigation plays as scenes.

**Scenes**: the agent's stream is grouped into scenes = {question line (from `thinking`), tool, result
summary, layer, camera move (`fly_to` with pitch/bearing)}. The front plays scenes at its own pace (a few
seconds each, even if the tool was faster or slower). Board stamps (`RULED OUT` / `SUPPORTED` / `HINT`) are
the emotional beats; the before/after curtain plays when land cover changes; the ending pulls the camera
out and closes on the answer + "A clue, not proof." + "every figure checked · N tests run".
Live and replayed runs use the same scene player, so the recorded demo feels identical to a live run.

### 5.5c Fourth solved case: a coral reef (Mandy, decided; data scout running)

Great Barrier Reef (proposed). Steps: sea temperature (MUR) + heat stress (DHW) → is it real → is it the
climate (bleaching = heat; inshore chlorophyll as a water-quality clue, never attribution). Assets via ERDDAP
bbox grids (`trend_sst.png`, `year_sst_<YYYY>.png`), MODIS true-colour base, GEBCO bathymetry (non-NASA,
labelled). Framing: reefs are the "rainforest of the sea"; the ocean as the planet's other lung only with a
cited figure.

Local test points for the detective: La Viñuela (Axarquía; data end 2024, the reservoir refilled in 2026 —
the answer must say "data end in 2024"; MODIS land cover may class orchards as savanna, so the land-cover tool
states that limit) and the Alborán Sea off Málaga (MUR SST: +0.10 °C/decade, p = 0.25, single test → "can't
tell yet").

### 5.5d What the map shows, and why (map = evidence, 3D = context)

Every layer on screen is the evidence of the current scene: what the tool measured, where, at what
resolution, from which source. Nothing is decoration.

- **Context** (opens every investigation): true colour of the clearest day, relief in 3D, land cover.
  The 3D relief is there to explain: basins and upstream areas (Lake Mead's rain falls upstream), glacier
  slopes, reservoir shape, reef shelf (bathymetry).
- **Evidence** (one per scene): the variable the tool just tested, for the scene's year or period, with
  legend + source + resolution; the **footprint of the data cell** (GRACE ~300 km, POWER ~50 km) drawn when the
  cell is bigger than the place.
- **Comparison**: before/after curtain (two years), year slider over yearly layers, per-pixel trend map where
  it exists (the cases, ERDDAP grids for the sea).

Three ways a layer reaches the map:
1. **GIBS tiles** straight into MapLibre by layer id + date (instant, anywhere).
2. **Overlays we compute** from a tool result (water extent from HLS NDWI, per-pixel trend from an ERDDAP grid,
   cases' `trend_*`/`year_*` PNGs) as image sources.
3. **Vectors**: the picked point/box, data-cell footprints, suspect markers.

Map tools for the agent: `show_layer(id, date|year, opacity)`, `set_year(year)`, `compare(id, year_a, year_b)`
(curtain), `fly_to(bbox, pitch, bearing)`, `show_footprint(source)`.

Curated layer catalog by zone (ids checked against GIBS capabilities by the builder):

| Zone | Layers |
|---|---|
| Any | true colour (MODIS/VIIRS), relief, land cover (MCD12Q1), precipitation (IMERG) |
| Farmland / vegetation | NDVI, ground temperature (LST), soil moisture (SMAP) |
| Water / reservoir | true colour then/now, water extent (ours, HLS), GRACE footprint |
| Snow / glacier | snow cover, ground temperature |
| City | night lights (Black Marble), ground temperature (heat island), urban share |
| Fire-prone | active fires / thermal anomalies |
| Sea / coast / reef | sea surface temperature (MUR), chlorophyll-a, heat stress (DHW, ours from ERDDAP) |

### 5.6 Demo

Record 3–4 real runs (SSE to JSON) — e.g. Doñana, Lake Mead, a surprise point, one that ends
"can't tell yet" — and a replay mode (`?replay=<id>`) that plays them with real timing. Live run as bonus.

## 6. Statistical honesty (mandatory)

- **Session-wide FDR**: every `trend_test`/`correlate` is logged; the final verdicts shown in the answer and
  the board use Benjamini-Hochberg over **all** tests of the investigation, not per call. The answer says how
  many tests were run.
- **Resolution stated**: each tool result carries its source resolution; the conclude node must mention it
  when the place is smaller than the source cell.
- **Residual = clue**: existing policies stay (no residual for GLDAS, none for GRACE on snow/glacier).
- **Validator** rejects figures not in the ledger, causal words, "proof", jargon.

### 6.1 Calls settled after the builder check (Claude's calls, Mandy to check)

- **FDR family = the whole `thread_id`** (follow-ups included). Counted as tests: `trend_test`, `correlate`
  (each lag), the trend test inside `climate_residual`, and each side of `compare`. BH recomputed after every
  test and sent on each `board` event.
- **The code overrides the board**: `supported` needs at least one evidence id whose BH-corrected q < 0.05;
  if not, the code downgrades it to `hint` and flags it (`downgraded: "fails correction over N tests"`).
  `ruled_out` needs a test with "no trend"/"can't tell yet" plus enough years, otherwise `open`.
- **GIBS yearly values are trend-testable on an annual path**: plain MK + Sen on annual seasonal means
  (one value a year, ≥ 10 years), status `observed · seasonal mean decoded from GIBS colours · step ≈ <palette step>`.
  Never mixed with monthly-anomaly tests in one verdict.
- **AppEEARS-only variables off-case**: `list_variables` swaps in the GIBS version where one exists (NDVI,
  LST, snow) and lists the rest as `not_available_here` with the reason. Inside the three cases the
  precomputed AppEEARS results are used via `solved_case`.
- **Residual drivers stay catalog-fixed**: the model chooses the target only; drivers and candidate designs
  come from `residual.py` as today. One residual per target per thread (repeat calls return the cached result).
- **Ledger-native validator**: reuse the checks of `app/explain/validator.py` (numbers, direction, certainty
  words, causal words, jargon), but against the ledger and BH-corrected verdicts. **No figures derived by the
  model**: rates, differences and ratios are computed by tools (`compare` returns the difference).

## 7. Constraints

- Frontend versions frozen (Next 16.4, React 19.3, MapLibre 5.24, three 0.187). Backend may add
  `langgraph`, `langchain-core`, `langchain-openai`, `langchain-anthropic` (uv).
- Secrets: env / `~/.secrets/`; never in code, never `NEXT_PUBLIC_*`.
- Tests: TDD for the non-trivial pieces (session FDR, ledger/validator, tool wrappers' contracts, graph with a
  fake chat model). 80 % on `app/detective/`.
- Internal docs in Spanish; UI and deliverables in English.

## 8. Order and cut lines

1. Backend tools + graph + `/detective` SSE, fake-model tests (tonight).
2. Prompt tuning on 5 test questions (tonight / early morning).
3. Front detective screen with MapLibre 3D + board (morning).
4. Recording + replay (by 13:00). **After 13:00 no new features.**
Cut if late, in order: `compare` → `satellite_picture` → GIBS yearly at any point (keep POWER/GRACE/GLDAS) →
3D terrain (flat MapLibre). Never cut: real tool loop, session FDR, validator, case board.

## 9. Left to the builder

Exact prompt wording; tool JSON shapes beyond §5.3; which ~20 GIBS layers (from GIBS capabilities, checked to
render); caching details; UI layout details within §5.5.
