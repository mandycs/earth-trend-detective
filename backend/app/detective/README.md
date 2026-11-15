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
- Each suspect in `board.suspects` is `{id, label, status, claimed, evidence, dropped, note, downgraded,
  target_var, kind, suspect_var}`. `status` is one of `open`, `supported`, `hint`, `ruled_out` or
  **`trend_only`** (shown as "TREND REAL · NOT LINKED"). The model can only ask for the first four; the
  code decides what is shown (`board.py`). `supported` needs an evidence test that links the suspect to the
  variable under investigation and survives the correction: a `correlate` test between the target and the
  suspect's own variable `suspect_var` (any lag), or, for a non-climate suspect only, the target's
  residual with a real verdict. With no `suspect_var`, no correlate counts as a link. When only the trend of
  `suspect_var` is real, the status is `trend_only` and `downgraded` is
  `"its own trend is real, but no test links it to <target label>"`. Other `hint` reasons:
  `"fails correction over N tests"`, `"no test links it to <target label>"`, and
  `"no test links its own data to <target label>"` (when `suspect_var` is unknown).
- `target_var`, `kind` (`climate` / `non_climate`) and `suspect_var` are what the model gave, or `null` on
  older calls and boards. When they are `null`, the code infers them:
  - the target from the residual test, else the first trend-tested series, else `series_a` of the
    first correlate;
  - `suspect_var` from the first non-target variable of the suspect's non-correlate evidence;
  - the kind from whether `suspect_var` (else the evidence variables, else the suspect's name matched
    against the catalog driver labels) is a climate driver.
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
