# Detective backend: deploy notes

`POST /detective` streams one investigation as Server-Sent Events. `GET /detective/{thread_id}` and
`GET /detective/{thread_id}/history` re-open a thread and list the steps a run can be forked from.

## Environment

| Variable | Default | Notes |
|---|---|---|
| `LLM_API_KEY` | unset | Anthropic key. Takes priority over OpenRouter. |
| OpenRouter key file | see `app/explain/openrouter.py` | Used when `LLM_API_KEY` is unset. |
| `DETECTIVE_MODEL` | `claude-sonnet-5-5` (Anthropic) / `anthropic/claude-sonnet-5.5` (OpenRouter) | **Must use the id format of the provider that is active.** An Anthropic id sent to OpenRouter, or the other way round, fails every model call. The run then ends with the template answer and an agent `tool_failed`. |
| `DETECTIVE_DB` | `backend/data/detective/detective.sqlite` | SQLite file for the checkpointer and the store (WAL). If it cannot be opened, the rest of the API still starts and `/detective` answers 503. |
| `DETECTIVE_MAX_TOOL_CALLS` | `40` | Tool calls per run. |
| `DETECTIVE_MAX_SECONDS` | unset (no limit) | Wall clock per run. |
| `SSE_KEEPALIVE_SECONDS` | `15` | Seconds of silence on an open `/detective` or `/investigate` stream before an SSE comment line (`: keepalive`) is sent, so proxies (Traefik, Cloudflare ~100 s idle cut) do not drop a run while a slow source is fetching. Clients ignore comments. Non-positive or invalid values fall back to 15. |
| `CORS_ORIGINS` | `localhost` and `127.0.0.1` on ports 3000 and 5180 | Comma-separated origins allowed to call the API (`main.py`). **Set it for any other front origin** (demo host, Tailscale address, deploy domain); otherwise the browser blocks every call with no visible reason. |
| `LANGSMITH_TRACING` / `LANGCHAIN_TRACING_V2` | unset | **Keep tracing off in production.** Traces would send prompts, tool results and place coordinates to a third party. |

Model calls time out after 60 s and are retried twice (`model.py`).

## What is stored

- Checkpointer: the conversation and the JSON-safe case (ledger, board, map ops) at every step.
- Store `("detective", thread_id, "series")`: the monthly series, one item per series id.
- Store `("detective", thread_id, "tests")`: every test the thread ever logged, in any branch. It is
  append-only and keyed by tool call plus the test's position in it. The correction (Benjamini-Hochberg)
  runs over all of these tests, so a fork never drops earlier tests from the family.

## Event shapes

The full payloads are in `.superpowers/sdd/2026-11-15-detective-core/task-9-report.md`. Changes since then
are listed in `final-fix-report.md` next to it. In short:

- `board {suspects, n_tests, verdicts}`. `verdicts` is `{test_id: {verdict, direction}}`, corrected over the
  whole family. A board event is also sent after every tools step that changed a verdict or added a test.
- Each suspect in `board.suspects` is `{id, label, status, claimed, evidence, dropped, note, downgraded,
  target_var, kind, suspect_var, expects}`. `status` is one of `open`, `supported`, `hint`, `ruled_out` or
  **`trend_only`** (shown as "TREND REAL · NOT LINKED"). The model can only ask for the first four; the
  code decides what is shown (`board.py`). `supported` needs an evidence test that links the suspect to the
  variable under investigation and survives the correction: a `correlate` test between the target and the
  suspect's own variable `suspect_var` (any lag), or, for a non-climate suspect only, the target's
  residual with a real verdict. With no `suspect_var`, no correlate counts as a link. When only the trend of
  `suspect_var` is real, the status is `trend_only` and `downgraded` is
  `"its own trend is real, but no test links it to <target label>"`. Other `hint` reasons:
  `"fails correction over N tests"`, `"no test links it to <target label>"`, and
  `"no test links its own data to <target label>"` (when `suspect_var` is unknown).
- `update_board` refuses a `suspect_var` equal to `target_var` (a suspect is a possible reason for the
  change, never the changing variable). A note that fails the screen comes back as `note_removed` (asking
  for a retry) and `note_problems` (fixed sentences per reason, never the note's own words).
- **Opposite direction rules out.** `expects` (`up` / `down`, or `null`) is the way `suspect_var` must go
  for the suspect to hold; when the model gives none it is read from the name ("less", "lower"... -> down;
  "more", "warming"... -> up). A `trend` test of `suspect_var` in the evidence that is `real` (corrected,
  enough years) and goes the other way shows the suspect as `ruled_out` whatever was claimed, with
  `downgraded = "its own data went up, not down"`, but only when the model gave both `expects` and
  `suspect_var`. A name-derived direction or an inferred `suspect_var` only keeps a claimed `ruled_out`
  (also on a `likely` opposite trend). When another real/likely test of `suspect_var` goes the expected
  way, no direction rule applies.
- `target_var`, `kind` (`climate` / `non_climate`) and `suspect_var` are what the model gave, or `null` on
  older calls and boards. When they are `null`, the code infers them:
  - the target from the residual test, else the first trend-tested series, else `series_a` of the
    first correlate;
  - `suspect_var` from the first non-target variable of the suspect's non-correlate evidence;
  - the kind from whether `suspect_var` (else the evidence variables, else the suspect's name matched
    against the catalog driver labels) is a climate driver.
- `done {thread_id, n_tests, n_tests_branch, n_tool_calls}`. `n_tests` counts the thread's whole family;
  `n_tests_branch` counts the tests on this branch.
- `answer {text, checked, figures, source, rejected}`. `rejected` is `[{try, kind, reason}]`: why each
  narrator try was turned down (`kind` from the validator — `number`, `direction`, `certainty`, `causal`,
  `proof`, `jargon`, `length` — or the detective's rules — `cause`, `human`, `lead`, `residual_wording`,
  `nothing_measured`, `cell`, `not_measured`). `reason` is a fixed sentence per kind
  (`wording.REASONS`), never a piece of the model's text, so no unchecked figure travels in it; it is for
  diagnosis, not for display. The cell counts as said only as a length in km ("about 50 km", "a 50-km
  cell"), never as a bare number or a percent. A "why" question gets a
  third try. The template (`source: "template"`) states what changed, the share not explained by the
  climate (else whether the change is real), and one sentence with what could not be measured, the data
  cell and the board statuses (suspect names with a figure or a cause word are left out).
- The answer must state the data cell when the place is smaller than it (`report.data_cells`, from the
  sources of the tested variables), and must say "could not be measured" when the question names a
  variable that is in `report.not_measured` (`report.asked_not_measured`). `not_measured` also lists the
  variables `list_variables` marked unavailable here.
- `thinking {text}` and board notes are checked. A line with a figure no tool returned, a cause claim,
  "proof" or "this part is human" is shown as `Next: <tool>.` instead, and such a note is shown empty.
- The map moves on its own: after `profile_place` the code appends `map {op: "fly_to", bbox: place bbox,
  pitch: 55, bearing: 0}` unless the camera already moved, and a solved case's profile lists
  `case_layers [{layer_id, title, kind}]`. `show_layer` with no date and no year gets `year` = the last
  year of the most recent tested period (else the investigation's end), when the layer has that year
  (case layers: yearly ones only).
- `map {op: "show_before_after", layer_id, year_a, year_b}` may also carry `before_url`, `after_url` and
  `bbox` (from `satellite_picture`). `layer_id` is always a map catalog id, e.g. `true_colour`.
- `history` items describe a step by the **last** tool message of that step. When the model made several
  tool calls in one turn, only the name of the last one is shown.
- A follow-up on a thread whose last run was cut between the model's turn and its tools first closes
  each open tool call with a `Stopped.` result. Without that, the provider would refuse the conversation.

## Data tools

Besides the core tools (`profile_place`, `list_variables`, `get_series`, `trend_test`, `correlate`,
`climate_residual`, `compare`, the map tools and the board), the detective has:

| Tool / variables | Source | What it gives |
|---|---|---|
| `sst`, `chlorophyll` (monthly), `dhw` (yearly peak) via `get_series` | NOAA CoastWatch ERDDAP (`extractors/erddap.py`): MUR SST, chlorophyll, Coral Reef Watch | Sea series for a point or box. Offered only with sea tags (`ocean`, `coast`; `dhw` only on `reef`). Cached per (dataset, variable, cell or box, year) under `backend/data/cache/erddap/`: past years forever, the current year never. A failed year is a gap (`missing_years`); three failed first years end the call. |
| Zones in `profile_place` | GIBS land cover + GEBCO minimum elevation (ERDDAP) | Tags `ocean` (water at least half of the box, or nothing classified), `coast` (some water), `reef` (a coast within 30° of the equator), `city` + `atmosphere` (built-up at least 15 %). Sea tags need ground at or below −5 m in the box (a lake sits above it); a failed GEBCO call gives no sea tags, and a solved case never gets them. |
| `ndvi_gibs`, `lst_gibs` (yearly) via `get_series` | GIBS monthly layers, read from their colours (`extractors/gibs_values.py`) | The off-case twins of the AppEEARS monthly variables: annual mean of the monthly values. Inside a solved case the monthly AppEEARS series is used instead. Cache: `backend/data/cache/gibs_values/`. |
| `no2_omi`, `co_airs` (yearly) via `get_series` | GIBS: daily OMI NO₂ (sampled 4 days a month, months weighted equally), monthly AIRS CO | Air for `city` / `atmosphere` places. Values stop at the top of the colour scale; a `saturated_share` caveat says when the trend is understated. |
| `trend_map` | ERDDAP grids (`sst`, `chlorophyll`) and the GIBS yearly layers | A per-pixel trend PNG served at `GET /detective/maps/{name}.png`, sent as `map {op: "overlay", url, bounds, legend, title, source, resolution, period}`, plus one counted test on the median over the area. A repeated call returns the cached map with q and verdict recomputed over every test logged since. |
| `water_extent` | NASA JPL OPERA DSWx-HLS via GIBS, scene days from CMR (`extractors/water_extent.py`) | Open-water area per year in the box, stored as an annual series for `trend_test`. |

A refusal that depends on the place tags (`not_available_here`, a sea variable on land, `water_extent` before
profiling) is not cached while the place is unprofiled, so the call after `profile_place` gets a real answer.

## Known limitations

- GIBS yearly NDVI and ground temperature (`ndvi_gibs`, `lst_gibs`) average the months each pixel was seen,
  with no minimum number of valid months per pixel. A year with a cloudier season can lean towards the clear
  months.
- Sea tags trust GEBCO's minimum elevation: a box below sea level on land (Dead Sea, Caspian shore) can get
  sea tags.
- Heat stress (`dhw`) north of the equator uses July–December. Near the equator the warm season can fall
  outside that window, so the yearly peak may be understated there.
- Snow from GIBS (`snow_gibs`) is not offered: GIBS draws no-snow and unseen ground (cloud, polar night) with
  the same transparent pixel, so a snow trend can't be measured honestly from its colours. Off-case snow stays
  not available; in the solved cases the AppEEARS monthly snow cover is used.
- Nitrogen dioxide (`no2_omi`) reads the daily OMI layer on GIBS on 4 days a month, about 1,000 pictures for
  2005–2025: the first call for a new place takes about 2.5 minutes. Completed years are then served from the
  disk cache (`backend/data/cache/gibs_values/`). Before a demo, pre-warm the cache for the demo cities by
  running `get_series("no2_omi")` for each once (or `gibs_values.fetch_annual` on their box).
- Air values from GIBS colours stop at the top of the colour scale (NO₂ 2×10¹⁶ molecules/cm², CO 350 ppbv);
  when more than 1 % of a year's seen pixels sit there, the result says the yearly values and the trend are
  understated.
- `trend_map` (per-pixel "where" maps) has grids for ERDDAP monthly sea variables (`sst`, `chlorophyll`) and
  the GIBS yearly layers. Heat stress (`dhw`, a daily product reduced to a yearly peak) and every point source
  answer "no gridded source for this variable". Pixel significance is drawn (faded when p ≥ 0.05) but never
  corrected over the area; the one counted test is on the median over the map area. The PNGs live in
  `backend/data/detective/maps/` and are removed after 7 days; a re-opened thread whose map is gone draws it
  again under the same name from the grid caches (no new test). If those caches are gone too, that redraw
  fetches the pictures again inside the repeated call (NO₂: about 2.5 minutes). Only `share_significant` and
  `median_slope_per_decade` are quotable; bounds, legend and the area test's numbers sit under `map`. GIBS grids have their own disk cache (`backend/data/cache/gibs_grids/`),
  separate from the point-series cache, so the first map of a GIBS variable fetches the pictures again
  (NO₂: about 2.5 minutes).
- `water_extent` (reservoir or lake area, km² at 30 m) reads NASA JPL OPERA DSWx-HLS from GIBS (scene days from
  CMR): open water plus the partial-water pixels touching it, one clear scene a month, yearly median, 9 clear
  months a year. OPERA has no scenes from mid-August 2020 to the end of 2022, so the record is short and its
  `trend_test` (annual path) stays "too short" until it holds `stats.annual.MIN_YEARS` yearly values. It refuses an
  unprofiled place, a box with sea tags or ground below −5 m (GEBCO), and an unanswered sea check. The first call
  takes about 2 minutes for 2016–2025 (cache: `backend/data/cache/water_extent/`).
