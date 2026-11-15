"""/explain endpoints: question routing and verified narrative."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.catalog import load_catalog, variables_for_site
from app.explain.llm import LLM, make_llm
from app.explain.narrative import explain_report
from app.explain.route import route_question
from app.sites import load_sites

logger = logging.getLogger(__name__)

SITES_DIR = Path(__file__).resolve().parents[3] / "sites"

router = APIRouter(prefix="/explain", tags=["explain"])


class RouteRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    site_id: str | None = None


class NarrativeRequest(BaseModel):
    site_id: str | None = None
    report: dict | None = None


def get_llm() -> LLM | None:
    """Claude if LLM_API_KEY is set, else None -> template mode (overridden in tests)."""
    return make_llm()


def get_sites_dir() -> Path:
    return SITES_DIR


def _known_site(site_id: str):
    catalog = load_sites()
    site = catalog.get(site_id)
    if site is None:
        known = ", ".join(s.id for s in catalog.sites)
        raise HTTPException(404, f"We don't know a site called '{site_id}'. Pick one of: {known}.")
    return site


def _load_site_report(site_id: str, sites_dir: Path) -> dict:
    site = _known_site(site_id)  # also keeps site_id from reaching the filesystem unchecked
    path = sites_dir / site.id / "site.json"
    if not path.is_file():
        raise HTTPException(404, f"No story report for '{site.id}' yet. Run the site export first.")
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/route")
def explain_route(body: RouteRequest, llm: LLM | None = Depends(get_llm)) -> dict:
    """Which catalog variables answer a plain-language question."""
    catalog = load_catalog()
    if body.site_id is None:
        variables = catalog
    else:
        # the site report holds monthly variables only (yearly ones live in the detective)
        variables = tuple(v for v in variables_for_site(catalog, _known_site(body.site_id).tags) if v.temporal != "annual")
    choices = {v.id: v.label for v in variables}
    result = route_question(body.question, choices, llm)
    return result.to_dict() | {"allowed_ids": list(choices)}


# TODO(reef Task 7/9): this resolves the sea site great_barrier_reef with land logic; decide there.
@router.post("/narrative")
def explain_narrative(
    body: NarrativeRequest,
    llm: LLM | None = Depends(get_llm),
    sites_dir: Path = Depends(get_sites_dir),
) -> dict:
    """3-5 verified plain sentences for a site report (by site_id, or the report itself)."""
    if (body.site_id is None) == (body.report is None):
        raise HTTPException(422, "Send either a site_id or a report, not both and not neither.")
    report = body.report if body.report is not None else _load_site_report(body.site_id, sites_dir)
    if not isinstance(report.get("variables"), list):
        raise HTTPException(422, "The report has no 'variables' list. Send a /sites/{id}/sweep report or a site.json.")
    return explain_report(report, llm).to_dict()
