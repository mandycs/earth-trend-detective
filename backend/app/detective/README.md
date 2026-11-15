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
- `done {thread_id, n_tests, n_tests_branch, n_tool_calls}`. `n_tests` counts the thread's whole family;
  `n_tests_branch` counts the tests on this branch.
- `thinking {text}` and board notes are checked. A line with a figure no tool returned, a cause claim,
  "proof" or "this part is human" is shown as `Next: <tool>.` instead, and such a note is shown empty.
- `map {op: "show_before_after", layer_id, year_a, year_b}` may also carry `before_url`, `after_url` and
  `bbox` (from `satellite_picture`). `layer_id` is always a map catalog id, e.g. `true_colour`.
- `history` items describe a step by the **last** tool message of that step. When the model made several
  tool calls in one turn, only the name of the last one is shown.
- A follow-up on a thread whose last run was cut between the model's turn and its tools first closes
  each open tool call with a `Stopped.` result. Without that, the provider would refuse the conversation.

## Known limitations

- GIBS yearly NDVI and ground temperature (`ndvi_gibs`, `lst_gibs`) average the months each pixel was seen,
  with no minimum number of valid months per pixel. A year with a cloudier season can lean towards the clear
  months.
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
  `backend/data/detective/maps/` and are removed after 7 days, so a thread re-opened later can point to a map
  that is gone (the route answers 404). GIBS grids have their own disk cache (`backend/data/cache/gibs_grids/`),
  separate from the point-series cache, so the first map of a GIBS variable fetches the pictures again
  (NO₂: about 2.5 minutes).
