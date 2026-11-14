# Earth Trend Detective

**Is it the climate, or is it us?**

Pick any place on Earth and find out what is changing there, whether the change is real, and how much of it
the climate does not explain. Built on NASA Earth observation data, explained in plain language.

NASA Space Apps Challenge 2026 · Challenge: [Be An Earth System Trend Detective!](https://www.spaceappschallenge.org/2026/challenges/earth-system-trend-detective/)

## Status

🚧 Work in progress during the hackathon (Nov 14–15, 2026).

## How it works

1. **Sweep** — automatically analyzes every applicable NASA variable for a place.
2. **Significance** — Mann-Kendall trend test (autocorrelation-corrected) with false-discovery-rate control.
3. **Climate vs non-climate** — models each impact variable from its climate drivers; the trend in what climate
   does not explain is the non-climate signal (a generalized RESTREND approach).
4. **Explanation** — a language model writes plain-language findings from the computed numbers only; a validator
   checks every figure.

## Repository layout

```
backend/   FastAPI data pipeline and statistics
frontend/  Web app (2D explore mode + 3D story mode)
sites/     Precomputed assets for the story-mode case studies
docs/      Team notes
```

## Start here

_To be completed before submission._

## NASA data

_To be completed: each NASA resource, link and its role in the solution._

## Use of AI

_To be completed: tools used and how they were incorporated._
