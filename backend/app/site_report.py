"""Per-site sweep report: gather every NASA series, trend-test, split climate vs non-climate.

Shared by the `/sites/{id}/sweep` endpoint and the story-mode exporter (site_export.py).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from app.catalog import Variable
from app.gather import SOURCES, GatherResult, gather_site_series
from app.sites import Site
from app.stats import compute_residuals, run_sweep

# Only observed impacts can carry a human signal in the residual. GLDAS is a land model
# without irrigation or pumping, so its residual is not reported as "non-climate %".
OBSERVED_SOURCES = frozenset({"grace", "appeears"})

GatherFn = Callable[[Site, Sequence[Variable], int, int], GatherResult]


def report_from_gathered(
    site: Site, catalog: Sequence[Variable], start: int, end: int, gathered: GatherResult
) -> dict:
    """The site sweep report for already gathered series (pure, no I/O)."""
    results = run_sweep(gathered.series, catalog) if gathered.series else []
    residuals = compute_residuals(gathered.series, catalog) if gathered.series else {}
    sources_by_var = {v.id: v.source for v in catalog}
    variables_out = []
    for r in results:
        row = r.to_dict()
        res = residuals.get(r.id)
        if res is not None:
            observed = sources_by_var.get(r.id) in OBSERVED_SOURCES
            row["residual_pct_non_climate"] = res.pct_non_climate if observed else None
            row["residual"] = res.to_dict() | {"observed": observed}
        variables_out.append(row)
    return {
        "site": {"id": site.id, "name": site.name, "bbox": list(site.bbox), "tags": list(site.tags)},
        "start": start,
        "end": end,
        "variables": variables_out,
        "missing": dict(gathered.missing),
        "sources": [{"id": k, "title": SOURCES[k].title, "url": SOURCES[k].url} for k in gathered.sources],
    }


def build_site_report(
    site: Site,
    catalog: Sequence[Variable],
    start: int,
    end: int,
    gather: GatherFn = gather_site_series,
) -> dict:
    """Gather the site's series with `gather` and build its sweep report."""
    return report_from_gathered(site, catalog, start, end, gather(site, catalog, start, end))
