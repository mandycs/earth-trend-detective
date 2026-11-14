"""Export the story-mode `sites/<id>/site.json` from the real pipeline output.

Usage (from backend/, venv active):
    python -m app.site_export lake_mead
    python -m app.site_export --all

Only site.json is written; image assets in sites/<id>/ are produced elsewhere and only
listed here when the files exist.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pandas as pd

from app.catalog import Variable, load_catalog
from app.gather import gather_site_series
from app.layers import write_layers
from app.site_report import GatherFn, report_from_gathered
from app.site_story import badge, headline, round_floats
from app.sites import Site, load_sites
from app.validation.mead_grace import SOURCE_TITLE, validate_grace_vs_mead
from app.validation.usbr import USBR_MEAD_URL

logger = logging.getLogger(__name__)

SITES_DIR = Path(__file__).resolve().parents[2] / "sites"
PIPELINE_VERSION = "0.1"
DEFAULT_EXAGGERATION = 3.0
VERTICAL_EXAGGERATION: Mapping[str, float] = {"lake_mead": 3, "aletsch": 1.5, "donana": 8}
STEPS = ("What is changing here?", "Is it real, or is it chance?", "Is it the climate?")
COUNTRY: Mapping[str, str] = {"lake_mead": "United States", "aletsch": "Switzerland", "donana": "Spain"}
MIN_MONTHS_PER_YEAR = 8
BASE_CAVEATS = ("The leftover share is a clue, not an attribution.",)
GRACE_CAVEAT = (
    "Total water stored comes from the GRACE satellites, which see a region about 300 km wide, "
    "not only this place."
)
VARIABLE_FIELDS = (
    "id",
    "label",
    "unit",
    "sen_slope_per_decade",
    "ci_low",
    "ci_high",
    "p_value",
    "q_value",
    "verdict",
    "direction",
    "years_needed",
    "residual_pct_non_climate",
)
_TREND_RE = re.compile(r"^trend_(?P<var>.+)\.png$")
_YEAR_RE = re.compile(r"^year_(?P<var>.+)_(?P<year>\d{4})\.png$")

Validator = Callable[[pd.Series, int, int], Mapping]


def find_assets(site_dir: Path) -> dict:
    """Assets present in `site_dir`; missing files are null / absent, never guessed."""
    names = sorted(p.name for p in site_dir.iterdir() if p.is_file()) if site_dir.is_dir() else []
    trend: dict[str, str] = {}
    yearly: dict[str, str] = {}
    for name in names:
        if m := _TREND_RE.match(name):
            trend[m["var"]] = name
        elif m := _YEAR_RE.match(name):
            yearly[m["var"]] = f"year_{m['var']}_{{YYYY}}.png"
    meta_path = site_dir / "heightmap.json"
    range_m = None
    if "heightmap.png" in names and meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        range_m = [meta["min_m"], meta["max_m"]]
    return {
        "heightmap": "heightmap.png" if "heightmap.png" in names else None,
        "heightmap_range_m": range_m,  # PNG 0 -> min_m, 65535 -> max_m
        "base": "base.jpg" if "base.jpg" in names else None,
        "trend": trend,
        "yearly": yearly,
    }


def yearly_series(series: pd.Series | None) -> list[dict]:
    """Calendar-year means for the story sparkline; years with < MIN_MONTHS_PER_YEAR are left out."""
    if series is None:
        return []
    valid = series.dropna()
    grouped = valid.groupby(valid.index.year)
    means = grouped.mean()[grouped.count() >= MIN_MONTHS_PER_YEAR]
    return [{"year": int(y), "value": float(v)} for y, v in means.items()]


def _withheld(row: Mapping) -> str | None:
    residual = row.get("residual") or {}
    return residual.get("withheld_reason")


def variable_rows(
    report_rows: Sequence[Mapping], series: Mapping[str, pd.Series] | None = None
) -> list[dict]:
    """Story-mode variable rows (subset of the sweep row) plus the UX badge, yearly series
    and, when the non-climate share is withheld, a plain-English note."""
    series = series or {}
    rows = []
    for row in report_rows:
        out = {k: row.get(k) for k in VARIABLE_FIELDS} | {"badge": badge(row["verdict"], row["direction"])}
        out["series"] = yearly_series(series.get(row["id"]))
        if note := _withheld(row):
            out["note"] = note
        rows.append(out)
    return rows


def site_caveats(report_rows: Sequence[Mapping]) -> list[str]:
    """Caveats shown with the case: base wording, GRACE footprint, withheld reasons (deduplicated)."""
    caveats = list(BASE_CAVEATS)
    if any(r["id"] == "grace_tws" for r in report_rows):
        caveats.append(GRACE_CAVEAT)
    for row in report_rows:
        note = _withheld(row)
        if note and note not in caveats:
            caveats.append(note)
    return caveats


def _default_validator(grace_tws: pd.Series, start: int, end: int) -> Mapping:
    return validate_grace_vs_mead(grace_tws, start, end).to_dict()


VALIDATORS: Mapping[str, tuple[str, Validator]] = {"lake_mead": ("grace_tws", _default_validator)}


def build_site_json(
    site: Site,
    catalog: Sequence[Variable],
    start: int,
    end: int,
    site_dir: Path,
    gather: GatherFn = gather_site_series,
    validators: Mapping[str, tuple[str, Validator]] = VALIDATORS,
    today: dt.date | None = None,
) -> dict:
    """The full site.json document for `site` (no file written)."""
    gathered = gather(site, catalog, start, end)
    report = report_from_gathered(site, catalog, start, end, gathered)
    rows = variable_rows(report["variables"], gathered.series)
    impacts = frozenset(v.id for v in catalog if v.role == "impact")
    sources = [{"title": s["title"], "url": s["url"]} for s in report["sources"]]

    validation = None
    if site.id in validators:
        var_id, validate = validators[site.id]
        series = gathered.series.get(var_id)
        if series is None:
            logger.warning("no %s series for %s; skipping validation", var_id, site.id)
        else:
            try:
                validation = dict(validate(series, start, end))
            except Exception as exc:  # noqa: BLE001 - validation is optional, the export still runs
                logger.warning("validation failed for %s: %s: %s", site.id, type(exc).__name__, exc)
    if validation is not None:
        sources.append({"title": SOURCE_TITLE, "url": USBR_MEAD_URL, "validation": True})

    assets = find_assets(site_dir)
    doc = {
        "id": site.id,
        "name": site.name,
        "country": COUNTRY.get(site.id),
        "bbox": list(site.bbox),
        "vertical_exaggeration": VERTICAL_EXAGGERATION.get(site.id, DEFAULT_EXAGGERATION),
        "elevation_m": assets["heightmap_range_m"],
        "years": [start, end],
        "assets": assets,
        "variables": round_floats(rows),
        "missing": dict(report["missing"]),
        "steps": list(STEPS),
        "headline": headline(rows, impacts),
        "narrative": None,
        "validation": round_floats(validation) if validation is not None else None,
        "sources": sources,
        "caveats": site_caveats(report["variables"]),
        "generated_at": (today or dt.date.today()).isoformat(),
        "pipeline_version": PIPELINE_VERSION,
    }
    return doc


def write_site_json(doc: Mapping, site_dir: Path) -> Path:
    """Write `doc` to `site_dir/site.json` (UTF-8, indent 2, non-ASCII kept)."""
    site_dir.mkdir(parents=True, exist_ok=True)
    path = site_dir / "site.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return path


def export_site(site_id: str, sites_dir: Path = SITES_DIR) -> dict:
    """Build and write site.json for one site id; raises KeyError for an unknown id."""
    site_catalog = load_sites()
    site = site_catalog.get(site_id)
    if site is None:
        known = ", ".join(s.id for s in site_catalog.sites)
        raise KeyError(f"unknown site {site_id!r}; known: {known}")
    start, end = site_catalog.study_period
    site_dir = sites_dir / site.id
    doc = build_site_json(site, load_catalog(), start, end, site_dir)
    path = write_site_json(doc, site_dir)
    write_layers(site.id, site_dir)
    logger.info("wrote %s", path)
    return doc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write sites/<id>/site.json from the real pipeline.")
    parser.add_argument("site_id", nargs="?", help="site id from catalog/sites.yaml")
    parser.add_argument("--all", action="store_true", help="export every site")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # signed URLs carry the user id
    if args.all == bool(args.site_id):
        parser.error("give a site id or --all (not both)")
    ids = [s.id for s in load_sites().sites] if args.all else [args.site_id]
    for site_id in ids:
        try:
            doc = export_site(site_id)
        except KeyError as exc:
            print(exc.args[0], file=sys.stderr)
            return 2
        badges = ", ".join(f"{v['id']}: {v['badge']}" for v in doc["variables"])
        print(f"{site_id}: {doc['headline']}\n  {badges}\n  missing: {', '.join(doc['missing']) or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
