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

# GRACE sees ~300 km regions. At snow/glacier sites the regional signal is dominated by
# snow and ice melt, which the residual model has no driver for, so melt would be
# misread as "non-climate". The % is withheld there; MODIS variables still get it.
SNOW_TAGS = frozenset({"snow", "glacier"})

MODEL_REASON = (
    "This comes from a computer model of the land that does not include human water use, "
    "so it cannot show a human signal."
)
GRACE_SNOW_REASON = (
    "GRACE sees the whole region (about 300 km), where melting snow and ice dominate, "
    "and our climate model has no snow term, so the split would be misleading here."
)


def residual_withheld_reason(source: str | None, site_tags: Sequence[str]) -> str | None:
    """Plain-English reason to hide the non-climate %, or None to show it."""
    if source not in OBSERVED_SOURCES:
        return MODEL_REASON
    if source == "grace" and SNOW_TAGS & set(site_tags):
        return GRACE_SNOW_REASON
    return None

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
            source = sources_by_var.get(r.id)
            withheld = residual_withheld_reason(source, site.tags)
            row["residual_pct_non_climate"] = res.pct_non_climate if withheld is None else None
            pct_range = res.pct_range if withheld is None else None
            row["residual_pct_range"] = [round(x, 1) for x in pct_range] if pct_range is not None else None
            row["residual"] = res.to_dict() | {
                "observed": source in OBSERVED_SOURCES,
                "withheld_reason": withheld,
            }
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
