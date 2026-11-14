# Detective agent — backend core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A real tool-calling investigator (`POST /detective`, SSE) built on LangGraph over the tools the backend already has, with a session-wide FDR ledger, a code-enforced case board, map instructions, and a final answer checked figure by figure.

**Architecture:** New package `backend/app/detective/`. Tools are thin wrappers over existing code (`gather.py` fetchers, `stats/*`, `investigate/landcover.py`, `investigate/thennow.py`, `sites/<id>/site.json`). Every tool writes to a per-thread `Ledger` (results, tests, board, map) held server-side; the model only sees compact JSON. A LangGraph `StateGraph` loops `agent ⇄ tools`, then `conclude` writes the answer and validates it against a report built from the ledger with the existing `validate_narrative`.

**Tech Stack:** Python 3.12, FastAPI, uv, `langgraph`, `langchain-core`, `langchain-openai` (OpenRouter), `langchain-anthropic`, pytest.

**Spec:** `docs/superpowers/specs/2026-11-15-detective-agent-design.md` (sections 5.2, 5.3, 5.4, 5.7, 6, 6.1). Read it before Task 1.

**Scope of this plan:** backend core only. Separate plans follow for: (2) new data tools — `sea_series` (ERDDAP), `water_extent` (HLS), atmosphere (OMI/AIRS), GIBS yearly values at any point, per-pixel "where" maps; (3) front detective screen (MapLibre 3D, scene player, board, chart per scene, replay); (4) the reef case assets; (5) honesty fixes in project page / pitch / deck. This plan leaves extension points for (2): a tool registry and a `sources` map in `list_variables`.

## Global Constraints

- Work on branch `mandy/detective`; push every commit to origin; never push to `main`.
- Activate the venv before running anything: `cd backend && source .venv/bin/activate`. Tests: `python -m pytest -q`.
- Add deps only with `uv add langgraph langchain-core langchain-openai langchain-anthropic` (in `backend/`). No frontend changes in this plan.
- Secrets: `LLM_API_KEY` env (Anthropic) or the OpenRouter key file read the same way as `app/explain/openrouter.py:get_openrouter_key`. Never log keys or prompts; never hardcode. `tests/conftest.py` already blocks real keys — keep every test offline (no network: monkeypatch fetchers).
- "No figure on screen that did not come out of a tool result." Model never computes figures; tools return them.
- Never causal words, "proof", or "this part is human". Residual wording: "not explained by the climate we measured — a clue, not proof".
- Session FDR family = whole `thread_id`. Counted tests: `trend_test`, each lag of `correlate`, the residual trend inside `climate_residual`, each side of `compare`.
- `supported` on the board needs ≥1 evidence id with BH-corrected q < 0.05, else downgraded to `hint` with `downgraded: "fails correction over N tests"`. `ruled_out` needs an evidence test whose corrected verdict is `unknown` and `too_short is False`, else `open`.
- Residual drivers come from the catalog (`Variable.drivers` via `residual_for`); one residual per target per thread (cached).
- Limits from env: `DETECTIVE_MAX_TOOL_CALLS` (default 40), `DETECTIVE_MAX_SECONDS` (default unset = no limit).
- Agent model: `claude-sonnet-5-5` (Anthropic) / `anthropic/claude-sonnet-5.5` (OpenRouter), overridable with `DETECTIVE_MODEL`.
- Tool results to the model: compact JSON, no raw monthly series; annual values (for the front chart) go in the SSE `result`, not to the model.
- English for all strings the user sees; commit style `<type>: <description>` + the two attribution lines from the session.
- Do not break `/investigate` or any existing test (345 currently pass).

## Review Focus

1. **A point over open ocean or where a source has no data** → the tool returns `{"status": "not_available", "reason": ...}` and the run continues; the answer says what could not be measured. Test in Task 4 (`test_get_series_no_data_is_not_available`).
2. **A source fails or times out mid-run** → SSE `tool_failed {id, reason}` and the loop continues; never a 500 or a stack trace in the stream. Test in Task 9 (`test_stream_tool_failure_becomes_event`).
3. **No LLM key configured** → `POST /detective` streams one `error` event with "The investigator needs a language model key on the server." and closes; status 200. Test in Task 9 (`test_no_model_streams_error`).
4. **The model repeats the same call or never stops** → identical tool calls in a thread return the cached result (no new test logged); the loop stops at `DETECTIVE_MAX_TOOL_CALLS` and still runs `conclude`. Tests in Task 3 (`test_ledger_dedupes_identical_calls`) and Task 8 (`test_graph_stops_at_tool_budget`).
5. **Request without a location** (no lat/lon, bbox or site_id) → 422 with "Pick a point or draw a box on the map first." Test in Task 9 (`test_requires_location`).

---

### Task 1: Variable definitions in the catalog

**Files:**
- Modify: `backend/catalog/variables.yaml` (add `definition:` to all 15 variables)
- Modify: `backend/app/catalog.py` (`Variable.definition: str = ""`, parsed in `_parse_variable`)
- Test: `backend/tests/test_catalog.py`

**Interfaces:**
- Produces: `Variable.definition: str` — one plain-English sentence, ≤ 160 chars, no jargon.

- [ ] **Step 1: Write the failing test**

```python
def test_every_variable_has_a_plain_definition():
    for var in load_catalog():
        assert var.definition, var.id
        assert len(var.definition) <= 160, var.id
        assert "Mann" not in var.definition and "anomal" not in var.definition.lower()
```

- [ ] **Step 2: Run it to verify it fails** — `python -m pytest tests/test_catalog.py -q -k definition` → FAIL (`AttributeError` or empty).
- [ ] **Step 3: Add the field and write 15 definitions** (e.g. `grace_tws`: "All the water stored in a region — underground, in the soil, in snow and in lakes — weighed from space by the GRACE satellites.").
- [ ] **Step 4: Run the full suite** — `python -m pytest -q` → all pass.
- [ ] **Step 5: Commit** — `feat: a plain definition for every catalog variable`.

### Task 2: Dependencies and the chat-model factory

**Files:**
- Modify: `backend/pyproject.toml`, `backend/uv.lock` (via `uv add`)
- Create: `backend/app/detective/__init__.py`, `backend/app/detective/model.py`
- Test: `backend/tests/detective/test_model.py`

**Interfaces:**
- Produces: `make_chat_model() -> BaseChatModel | None` — `ChatAnthropic(model=DETECTIVE_MODEL or "claude-sonnet-5-5")` when `LLM_API_KEY` is set; else `ChatOpenAI(model=DETECTIVE_MODEL or "anthropic/claude-sonnet-5.5", base_url="https://openrouter.ai/api/v1", api_key=<openrouter key>)` when the key file/env exists; else `None`.

- [ ] **Step 1: Failing tests** — `test_no_key_gives_none` (conftest removes keys → `make_chat_model() is None`); `test_anthropic_key_gives_anthropic(monkeypatch)` (set `LLM_API_KEY=x` → `isinstance(m, ChatAnthropic)`); `test_openrouter_key_file(monkeypatch, tmp_path)` (key file with `x` via `OPENROUTER_KEY_FILE` → `isinstance(m, ChatOpenAI)` and `m.openai_api_base` ends with `/api/v1`).
- [ ] **Step 2: Run** → FAIL (module missing).
- [ ] **Step 3: `uv add langgraph langchain-core langchain-openai langchain-anthropic`; implement `model.py`** reusing `get_openrouter_key` from `app/explain/openrouter.py`.
- [ ] **Step 4: Run** `python -m pytest tests/detective -q` → PASS; full suite still passes.
- [ ] **Step 5: Commit** — `feat: chat-model factory for the detective (Anthropic or OpenRouter)`.

### Task 3: Ledger with session-wide FDR

**Files:**
- Create: `backend/app/detective/ledger.py`
- Test: `backend/tests/detective/test_ledger.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class TestRecord: id: str; var_id: str; label: str; kind: str  # "trend"|"correlate"|"residual"|"compare"; p_value: float; slope: float | None; too_short: bool; result: TrendResult | None`
  - `class Ledger:` (one per thread)
    - `call_key(tool: str, args: Mapping) -> str` (stable JSON of sorted args)
    - `cached(key: str) -> dict | None`, `remember(key: str, result: dict) -> str` (returns evidence id `"e<N>"`)
    - `add_test(record: TestRecord) -> None`
    - `corrected() -> dict[str, tuple[float, Verdict, Direction]]` — BH (`stats/fdr.benjamini_hochberg`) over all tests, then `stats/verdict.classify(q, p, slope)`
    - `figures() -> list[float]` — every number a tool returned that the answer may quote
    - `n_tests: int` property
- Uses: `benjamini_hochberg`, `classify`, `TrendResult`.

- [ ] **Step 1: Failing tests**

```python
def test_correction_runs_over_all_tests_of_the_thread():
    led = Ledger()
    led.add_test(TestRecord("t1", "t2m", "Air temperature", "trend", 0.01, 0.8, False, None))
    for i in range(19):
        led.add_test(TestRecord(f"x{i}", f"v{i}", "v", "trend", 0.5, 0.1, False, None))
    q, verdict, _ = led.corrected()["t1"]
    assert q == pytest.approx(0.2)          # 0.01 * 20 / 1
    assert verdict != Verdict.REAL           # alone it would be real; across 20 tests it is not

def test_ledger_dedupes_identical_calls():
    led = Ledger()
    key = led.call_key("trend_test", {"series_id": "s1"})
    assert led.cached(key) is None
    eid = led.remember(key, {"ok": 1})
    assert led.cached(led.call_key("trend_test", {"series_id": "s1"})) == {"ok": 1, "evidence_id": eid}
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `feat: detective ledger with FDR over the whole investigation`.

### Task 4: Place, variables, series and trend tools

**Files:**
- Create: `backend/app/detective/place.py` (`Place`), `backend/app/detective/tools/__init__.py` (registry), `backend/app/detective/tools/data.py`
- Test: `backend/tests/detective/test_tools_data.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Place: lat: float; lon: float; bbox: tuple[float,float,float,float]; tags: tuple[str, ...] = (); site_id: str | None = None` and `Place.as_site() -> Site` (reuse `investigate/runner.point_site` logic; for `site_id` use `load_sites()`).
  - `class Session: ledger: Ledger; place: Place; series: dict[str, pd.Series]; catalog: tuple[Variable, ...]; start: int = 2003; end: int = 2024` (lives in `app/detective/session.py`; `SESSIONS: dict[str, Session]` keyed by `thread_id`).
  - Tool functions, each `(session: Session, **args) -> dict` returning compact JSON with `evidence_id`:
    - `profile_place()` → `{"tags", "land_cover": {class: share}, "dominant", "data_cells": {"grace": "~300 km", "power": "~50 km"}}` (from `landcover.fetch_land_cover`; tags via `landcover.tags_for`; updates `session.place.tags`).
    - `list_variables()` → `[{"id","label","definition","source","resolution","available": bool, "reason"?}]` via `variables_for_site`; `available=False, reason="not_available_here: only precomputed for the solved cases"` for `appeears*` sources when `site_id is None`.
    - `get_series(var_id: str, start: int | None = None, end: int | None = None)` → fetch via `gather.FETCHERS[source]` on `session.place.as_site()`; store in `session.series[series_id]`; return `{"series_id", "var_id", "label", "unit", "n_months", "years": [start,end], "status": "ok"}` or `{"status": "not_available", "reason"}`. Annual means go into `result["chart"]` (list of `{year, value}`), stripped before the model sees it (Task 8).
    - `trend_test(series_id: str, start: int | None = None, end: int | None = None)` → `monthly_anomalies` → `stats/trend.trend_test` → `years_needed`; logs `TestRecord(kind="trend")`; returns `{"slope_per_decade","ci_low","ci_high","unit","p_value","q_session","verdict","direction","years_needed","n_tests_so_far"}` with verdict from `ledger.corrected()`.
  - `TOOLS: dict[str, ToolSpec]` registry where `ToolSpec = (fn, description: str, args_schema: type[BaseModel])` — later plans add entries here.

- [ ] **Step 1: Failing tests** (monkeypatch `gather.FETCHERS["power"]` to return a synthetic monthly series with a known trend; monkeypatch `landcover.fetch_land_cover`):
  - `test_get_series_then_trend_test_logs_a_test` — after both calls `session.ledger.n_tests == 1` and result has `verdict` in `{"real","likely","unknown"}`.
  - `test_get_series_no_data_is_not_available` — fetcher returns `{}` → `{"status": "not_available", ...}`; no exception.
  - `test_appeears_variables_not_available_off_case` — `Place` without `site_id`, tags `("vegetated",)` → `ndvi` row has `available is False`.
  - `test_trend_window` — `trend_test(series_id, start=2013)` uses only 2013–2024 (`n_months == 144`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `feat: detective tools for place, variables, series and trend tests`.

### Task 5: Analysis tools — residual, correlate, compare, years

**Files:**
- Create: `backend/app/detective/tools/analysis.py`
- Test: `backend/tests/detective/test_tools_analysis.py`

**Interfaces:**
- Consumes: `Session`, `get_series`, `Ledger.add_test`.
- Produces:
  - `climate_residual(var_id: str)` → fetches the target and its catalog drivers through `get_series` (reusing cached series), runs `residual_for(var, impact, driver_anoms)`, applies `site_report.residual_withheld_reason`; logs the residual trend as `TestRecord(kind="residual")`; returns `{"pct_not_explained", "pct_range", "drivers", "withheld"?: reason, "wording": "not explained by the climate we measured — a clue, not proof"}`. Second call for the same `var_id` returns the cached result.
  - `correlate(series_a: str, series_b: str, max_lag: int = 2)` → annualise (`lineup.annualize`), year-on-year changes (`lineup.year_changes`), Pearson r and p per lag 0..max_lag (scipy); one `TestRecord(kind="correlate")` per lag; returns `{"lags": [{"lag","r","p","q_session"}]}`.
  - `compare(var_id: str, a: dict, b: dict)` where each side is `{"lat","lon"}` or `{"start","end"}` → two `trend_test`s (two records, `kind="compare"`), returns both results and `"difference_per_decade"` computed in code.
  - `years_needed_for(series_id: str)` → `{"years_needed"}` (no test logged).

- [ ] **Step 1: Failing tests:** `test_residual_is_cached_per_target` (two calls → one residual `TestRecord`); `test_residual_withheld_on_glacier` (tags `("glacier",)`, `grace_tws` → `"withheld"` present, no `pct_not_explained`); `test_correlate_logs_one_test_per_lag` (`max_lag=2` → 3 records); `test_compare_two_places_returns_difference` (synthetic +1 and −1 trends → `difference_per_decade` ≈ 2 and opposite `direction`s).
- [ ] **Step 2–4:** run → FAIL, implement, run → PASS.
- [ ] **Step 5: Commit** — `feat: detective analysis tools (residual, correlate, compare)`.

### Task 6: Context tools — land cover, pictures, solved cases

**Files:**
- Create: `backend/app/detective/tools/context.py`
- Test: `backend/tests/detective/test_tools_context.py`

**Interfaces:**
- Produces:
  - `land_cover_change(year_a: int = 2003, year_b: int = 2023)` → `landcover.land_cover_pair` + `share_changes`; always includes `"caveat": "At 500 m, orchards and tree crops may be classed as savanna or woody vegetation, not cropland."`; returns `layer` for the map.
  - `satellite_picture(year_a: int = 2003, year_b: int = 2024)` → `thennow.then_and_now(lat, lon, (year_a, year_b), tags)`; status `visual_only`; adds a `map` instruction `show_before_after`.
  - `solved_case(site_id: str)` → reads `sites/<id>/site.json`: per variable `{id,label,verdict,direction,sen_slope_per_decade,ci_low,ci_high,residual_pct_non_climate,residual_pct_range}` + `note` + `caveats`. Does **not** log tests (they were corrected within the case); marks `"precomputed": True`.

- [ ] **Step 1: Failing tests:** `test_land_cover_always_carries_orchard_caveat`; `test_solved_case_reads_site_json` (Lake Mead → `grace_tws` row present, `precomputed is True`, `ledger.n_tests == 0`); `test_unknown_case_is_not_available`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** — `feat: detective context tools (land cover, pictures, solved cases)`.

### Task 7: Map and board tools

**Files:**
- Create: `backend/catalog/map_layers.yaml`, `backend/app/detective/tools/mapping.py`, `backend/app/detective/board.py`
- Test: `backend/tests/detective/test_map_board.py`

**Interfaces:**
- Produces:
  - `map_layers.yaml`: entries `{id, title, gibs_layer, kind: wmts|wms, legend: {unit, min, max, colormap?}, dates: {start, end, step: daily|8day|monthly|annual}, zones: [...], source, resolution}`. Start with the 7 zone rows of spec §5.5d using GIBS ids for: true colour (MODIS Terra), land cover (MCD12Q1 annual), NDVI, LST day, snow cover, IMERG precipitation, night lights (Black Marble), active fires, MUR SST, MODIS Aqua chlorophyll. Builder checks each id renders via a GetCapabilities fetch **once, manually**, and records it in a comment; tests stay offline.
  - `show_layer(layer_id: str, date: str | None = None, year: int | None = None, opacity: float = 0.8)` → validates id against `map_layers.yaml` ∪ the case's `layers.json`; unknown id → `{"status":"rejected","reason":"unknown layer"}`; else appends `{"op":"show_layer",...}` to `session.map`.
  - `set_year(year: int)`, `show_before_after(layer_id: str, year_a: int, year_b: int)`, `fly_to(bbox: list[float], pitch: float = 55, bearing: float = 0)`, `show_footprint(source: Literal["grace","power","gldas"])` → map ops.
  - `board.Suspect: {id, label, status: "open"|"supported"|"hint"|"ruled_out", evidence: list[str], note: str, downgraded: str | None}`; `apply_update(board: dict[str, Suspect], update: dict, ledger: Ledger) -> dict[str, Suspect]` (returns a new dict) enforcing the Global Constraints rules; tool `update_board(suspect: str, status: str, evidence_ids: list[str], note: str)`.

- [ ] **Step 1: Failing tests:**

```python
def test_supported_without_corrected_evidence_becomes_hint(ledger_with_one_weak_test):
    board = apply_update({}, {"suspect": "irrigation", "status": "supported",
                              "evidence_ids": ["t_weak"], "note": "x"}, ledger_with_one_weak_test)
    assert board["irrigation"].status == "hint"
    assert board["irrigation"].downgraded.startswith("fails correction over")

def test_ruled_out_needs_a_long_enough_flat_test(...): ...   # too_short=True → status "open"
def test_show_layer_rejects_unknown_ids(): ...
def test_every_map_layer_has_legend_source_and_dates(): ...
```

- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** — `feat: map instructions and a case board the code keeps honest`.

### Task 8: Conclude node and the graph

**Files:**
- Modify: `backend/app/explain/numbers.py` (`allowed_numbers` also accepts `report["figures"]`: list of numbers, origin `"figure[i]"`)
- Create: `backend/app/detective/report.py`, `backend/app/detective/prompt.py`, `backend/app/detective/graph.py`
- Test: `backend/tests/detective/test_graph.py`, `backend/tests/test_numbers.py` (add one case)

**Interfaces:**
- Produces:
  - `ledger_report(session: Session) -> dict` — `{"variables": [rows with id,label,verdict,direction,sen_slope_per_decade,ci_low,ci_high,years_needed,residual_pct_non_climate,residual_pct_range using session-corrected verdicts], "start": int, "end": int, "figures": ledger.figures()}` — the shape `validate_narrative` already reads.
  - `SYSTEM_PROMPT: str` in `prompt.py` — rules: investigate like a detective (profile → list variables → test the relevant ones → open suspects → test them → compare regions when useful → conclude); one short `thinking` sentence before every tool call (plain English, no figures); never compute figures; state data-cell size when the place is smaller; use the wording rule for residuals; put layers on the map for each piece of evidence; stop when the board explains the question or nothing more can be tested.
  - `build_graph(model: BaseChatModel, session_for: Callable[[str], Session], max_tool_calls: int, max_seconds: float | None) -> CompiledGraph` — nodes `agent` (model with `bind_tools` from `TOOLS`), `tools` (executes registry functions with the session, dedupes via `Ledger`, strips `chart` before returning `ToolMessage` content), `conclude` (model writes ≤ 3 sentences from `ledger_report`; `validate_narrative`; one retry with the rejections; else `app/explain/template.py` text); conditional edge `agent → tools` while tool calls and budget remain, else `→ conclude`; checkpointer `MemorySaver()`.
- Testing a fake model: subclass `langchain_core.language_models.fake_chat_models.GenericFakeChatModel` with `bind_tools(self, tools, **kw): return self`, fed `AIMessage(content="Checking rain.", tool_calls=[{"name":"get_series","args":{"var_id":"precip"},"id":"c1"}])` etc.

- [ ] **Step 1: Failing tests:** `test_graph_runs_tools_and_concludes` (fake model: profile_place → get_series → trend_test → final text; asserts the 3 tools ran in order and the answer validated); `test_graph_stops_at_tool_budget` (fake model always calls a tool; `max_tool_calls=3` → exactly 3 tool runs, then conclude); `test_conclude_rejects_invented_figure` (fake answer with "42 %" not in ledger → retry, then template; `checked is True` only for the validated text); `test_allowed_numbers_reads_figures` in `test_numbers.py`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** — `feat: the detective graph — real tool loop, then a checked answer`.

### Task 9: SSE events and `POST /detective`

**Files:**
- Create: `backend/app/detective/events.py`, `backend/app/detective/router.py`
- Modify: `backend/app/main.py` (include router, after `investigate_router`)
- Test: `backend/tests/detective/test_router.py`

**Interfaces:**
- Consumes: `build_graph`, `make_chat_model`, `SESSIONS`.
- Produces:
  - `class DetectiveRequest(BaseModel): question: str (1..500 chars); lat: float | None; lon: float | None; bbox: list[float] | None (4); site_id: str | None; thread_id: str | None` — validator: at least one location, else 422 "Pick a point or draw a box on the map first."
  - Event stream (spec §5.4), each `{"event": kind, "data": {...}}`: `place` · `thinking {text}` · `tool_start {id, tool, args}` · `tool_done {id, tool, summary, result, evidence_id}` (result keeps `chart`) · `tool_failed {id, tool, reason}` · `map {op, ...}` · `board {suspects, n_tests}` · `answer {text, checked, figures}` · `done {thread_id, n_tests, n_tool_calls}` · `error {message}`.
  - `stream_investigation(req, model) -> Iterator[dict]` using `graph.stream(..., stream_mode="updates")`; exceptions inside a tool become `tool_failed`; exceptions outside become one `error` event with a plain message (no trace).
  - `POST /detective` → `StreamingResponse(sse(...), media_type="text/event-stream")`, reusing `investigate/router.sse`. A follow-up with an existing `thread_id` keeps the ledger (FDR family) and board.

- [ ] **Step 1: Failing tests** (FastAPI `TestClient`, fake model injected via dependency override, fetchers monkeypatched): `test_requires_location`; `test_no_model_streams_error`; `test_event_order` (first `place`, then per tool `thinking`→`tool_start`→`tool_done`, then `board`, `answer`, `done` last); `test_stream_tool_failure_becomes_event` (fetcher raises `TimeoutError` → `tool_failed` and run reaches `done`); `test_follow_up_keeps_the_fdr_family` (second request with same `thread_id` → `done.n_tests` includes the first run's tests).
- [ ] **Step 2–4:** FAIL → implement → PASS; full suite `python -m pytest -q` green.
- [ ] **Step 5: Commit** — `feat: POST /detective streams the investigation as events`.

### Task 10: Live run and recordings (manual, needs the key)

**Files:**
- Create: `backend/scripts/detective_run.py`, `backend/data/recordings/.gitkeep`

**Interfaces:**
- Produces: `python scripts/detective_run.py --question "..." --lat .. --lon .. [--site-id ..] --out data/recordings/<name>.json` — POSTs to a running backend, saves the full event list with a `t_ms` offset per event (the front replay plan consumes this file).

- [ ] **Step 1:** Implement the script (httpx streaming, parses `event:`/`data:` lines).
- [ ] **Step 2:** Restart the backend on `100.70.153.87:8765` with the key available, run the five questions of spec §5.5c/§6 (Doñana by `site_id`; Lake Mead by `site_id`; La Viñuela `36.87,-4.17`; Alborán off Málaga `36.6,-4.4` — expect `not_available` for land variables until the sea tools plan lands; Málaga city `36.72,-4.42`). Expected: each run reaches `done`, `answer.checked is true`, no causal words.
- [ ] **Step 3:** Note in `docs/superpowers/plans/2026-11-15-detective-core.md` (bottom, "Run notes") what each run did badly; tune `prompt.py` and tool descriptions; re-run.
- [ ] **Step 4: Commit** — `feat: a script that records real detective runs for the demo` (recordings committed only if they contain no keys or personal data).
