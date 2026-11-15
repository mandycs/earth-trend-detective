# Use of AI

Two separate uses, declared separately, as NASA Space Apps asks.

## 1. AI as a development tool

The team used **Claude (Anthropic)** through Claude Code as a coding assistant during the hackathon: writing and
refactoring backend and frontend code, data extraction scripts, tests, and editing English copy. Commits made
with its help carry a `Co-Authored-By: Claude` line in the git history.

The team chose the challenge approach, the method (trend test, false-discovery control, climate split), the
variables and the three cases, and reviewed, ran and tested the generated code. The backend test suite runs with
`cd backend && uv run pytest -q`.

## 2. AI inside the product

A large language model (Claude, called through OpenRouter) has three narrow jobs:

| Job | What it receives | What it may do | What checks it |
| --- | --- | --- | --- |
| **Narrator** | The computed trends of a place as JSON | Write a short plain-English paragraph | A validator compares every figure in the text with the JSON. On a mismatch the model gets one retry; after that a fixed template is shown. Banned words (proof, cause, statistics jargon) are also rejected. |
| **Investigation planner** | The user's question, the place and its land cover | Pick 2–5 steps from a fixed menu of checks | `clean_plan` enforces the menu, order and dependencies. The code runs the steps; the model never touches data. |
| **Question routing and layer suggestions** | The question and the list of variables or layers that exist for the place | Choose ids from that list | The answer is limited to the given ids; the layer suggestion text may contain no figures. |

The model never computes a trend, never decides significance and never names a cause. The share of a trend that
the climate does not explain is always called a clue, not proof. The headline answer of an investigation is
built by code from the data, not by the model.

In the interface, model-written text is labelled: *"Written by an AI narrator from the numbers above. Every
figure was checked against the data before showing it."*

No image or video in this project is AI-generated. The background music of the landing and web pitch films was generated with Google Lyria (AI); it is declared in the video descriptions and in the files' metadata. The 30-second submission video uses a separate instrumental track generated with Google Lyria 3 Pro (AI) through Artlist, declared in its description and metadata. Model output is attributed to the model, never to
NASA, and no NASA insignia appears in the project.
