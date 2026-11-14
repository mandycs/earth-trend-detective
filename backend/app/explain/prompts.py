"""Prompt text and the compact facts the narrator sees. No secrets ever go in here."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from app.explain.validator import Rejection

ROUTE_SYSTEM = (
    "You map a plain-language question about a place on Earth to the NASA variables that "
    "help answer it. Pick only ids from the list you are given. Pick the few that matter "
    "most (usually 1 to 4). If none fits, return [\"unknown\"]."
)

NARRATIVE_SYSTEM = """You explain satellite trend results to a 14-year-old.

Write 3 to 5 short sentences of plain English, as one paragraph, following three steps:
1. What is changing here? 2. Is it real or just chance? 3. Is it the climate?

Hard rules:
- Use ONLY numbers that appear in the facts. You may round them (for example -6.47 to -6.5, 83.7% to 84%). Never convert units, never compute new numbers, never add years, counts or dates that are not in the facts. Write numbers with digits.
- A trend with verdict "real" is real. "likely" means probably real but not sure. "unknown" means we can't tell yet; never describe it as rising or falling for sure.
- Keep each trend's direction: "down" means falling, "up" means rising.
- If a trend has a "percent_not_explained_by_climate_range_across_climate_models", give that range (for example "between 54% and 84%, depending on the climate model") instead of the single percent.
- The share "not explained by climate" is a lead, not proof: you must write the exact words "a lead, not proof". Never say it proves anything or that people caused it.
- No jargon: do not write Mann-Kendall, FDR, p-value, q-value, significance, regression, residual or statistics words.
- If the facts include a "question", write only 2 or 3 sentences. Your FIRST sentence answers it directly with the trends in "answer_with": say whether each is going up, going down, or can't be told yet. After that, mention at most one other trend, and only if it helps answer the question.
- No headings, lists or markdown. Return only the paragraph."""

_FACT_KEYS = {
    "label": "name",
    "unit": "unit",
    "sen_slope_per_decade": "change_per_decade",
    "ci_low": "change_per_decade_low_end",
    "ci_high": "change_per_decade_high_end",
    "verdict": "verdict",
    "direction": "direction",
    "years_needed": "more_years_of_data_needed",
    "residual_pct_non_climate": "percent_not_explained_by_climate",
    "residual_pct_range": "percent_not_explained_by_climate_range_across_climate_models",
}


def site_name(report: Mapping) -> str:
    site = report.get("site")
    if isinstance(site, Mapping) and site.get("name"):
        return str(site["name"])
    return str(report.get("name") or "this place")


def report_facts(report: Mapping) -> dict:
    """The report fields the narrator may use (no p-values: they are jargon)."""
    years = report.get("years") or [report.get("start"), report.get("end")]
    variables = []
    for row in report.get("variables") or ():
        fact = {out: row.get(key) for key, out in _FACT_KEYS.items() if row.get(key) is not None}
        variables.append(fact)
    facts = {"place": site_name(report), "years": list(years), "trends_in_rank_order": variables}
    if report.get("question"):
        labels = {r.get("id"): r.get("label") for r in report.get("variables") or ()}
        facts["question"] = str(report["question"])
        facts["answer_with"] = [labels[i] for i in report.get("focus_ids") or () if labels.get(i)]
    return facts


def route_user(question: str, choices: Mapping[str, str]) -> str:
    listing = "\n".join(f"- {vid}: {label}" for vid, label in choices.items())
    return f"Variables:\n{listing}\n\nQuestion: {question.strip()}"


def narrative_user(report: Mapping, previous: str | None, errors: Sequence[Rejection]) -> str:
    facts = json.dumps(report_facts(report), ensure_ascii=False, indent=1)
    prompt = f"Facts (JSON):\n{facts}\n\nWrite the paragraph."
    if previous is not None and errors:
        problems = "\n".join(f"- {e.detail}" for e in errors)
        prompt += (
            f"\n\nYour previous paragraph was rejected:\n{previous}\n\nProblems:\n{problems}\n"
            "Write it again and fix every problem."
        )
    return prompt
