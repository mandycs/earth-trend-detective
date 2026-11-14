"""AppEEARS area extractor (MODIS NDVI, LST, ET, snow) — Earthdata Login token.

API docs: https://appeears.earthdatacloud.nasa.gov/api/

Flow: one *area* task per site (bbox polygon, every applicable appeears layer) ->
poll status -> download the bundle -> parse the per-product statistics CSV
(area mean per date) into monthly series in catalog units.

CLI (run from backend/ with the venv active):
    python -m app.extractors.appeears submit|status|download
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import yaml
from dotenv import load_dotenv

from app.catalog import Variable, load_catalog, variables_for_site

logger = logging.getLogger(__name__)

API_URL = "https://appeears.earthdatacloud.nasa.gov/api"
BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
SITES_PATH = BACKEND_DIR / "catalog" / "sites.yaml"
DEFAULT_CACHE_DIR = BACKEND_DIR / "data" / "cache" / "appeears"
TASKS_FILE = "tasks.json"
TIMEOUT_S = 120.0
START_YEAR = 2003
END_YEAR = 2024
# Head-room when splitting a request that AppEEARS rejects as too large.
SPLIT_MARGIN = 1.25
_TOO_LARGE_RE = re.compile(r"exceeds the maximum size allowed by ([0-9.]+)%")

# AppEEARS computes area statistics on values that already have the product's
# ScaleFactor applied (e.g. NDVI ~0.4, LST ~300 K). So we must NOT multiply by the
# catalog `scale` again; only the catalog `offset` (e.g. K -> °C) is applied.
STATS_ALREADY_SCALED = True

# Valid physical range per layer (after product scaling). Stats means outside it are
# contaminated by flag values (e.g. NDSI_Snow_Cover 200-254 = cloud/night/water) and
# are dropped to NaN.
VALID_RANGE: Mapping[str, tuple[float, float]] = {
    "_1_km_monthly_NDVI": (-0.2, 1.0),
    "LST_Day_1km": (150.0, 1310.7),
    "ET_500m": (0.0, 3270.0),
    "NDSI_Snow_Cover": (0.0, 100.0),
}


@dataclass(frozen=True)
class Site:
    id: str
    name: str
    bbox: tuple[float, float, float, float]
    tags: tuple[str, ...]


@dataclass(frozen=True)
class TaskRecord:
    """One submitted task. `key` is the site id, or `<site>@<y0>-<y1>` for a year chunk."""

    key: str
    site_id: str
    task_id: str
    submitted_at: str


class RequestTooLargeError(RuntimeError):
    """AppEEARS refused the request: it would generate too many files."""

    def __init__(self, overshoot_pct: float, message: str) -> None:
        super().__init__(message)
        self.overshoot_pct = overshoot_pct


def load_sites(path: Path = SITES_PATH) -> tuple[Site, ...]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return tuple(
        Site(
            id=str(s["id"]),
            name=str(s["name"]),
            bbox=tuple(float(x) for x in s["bbox"]),  # type: ignore[arg-type]
            tags=tuple(s.get("tags") or ()),
        )
        for s in data["sites"]
    )


def appeears_variables(catalog: Sequence[Variable], site: Site) -> tuple[Variable, ...]:
    return tuple(v for v in variables_for_site(catalog, site.tags) if v.source == "appeears")


def bbox_polygon(bbox: Sequence[float]) -> dict:
    """Closed GeoJSON polygon ring (counter-clockwise) from [min_lon, min_lat, max_lon, max_lat]."""
    w, s, e, n = bbox
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}


def build_area_request(
    site: Site,
    variables: Sequence[Variable],
    start_year: int = START_YEAR,
    end_year: int = END_YEAR,
    task_name: str | None = None,
) -> dict:
    """AppEEARS area-task JSON for one site, 01-01-<start_year> to 12-31-<end_year>."""
    if not variables:
        raise ValueError(f"site {site.id!r}: no appeears variables apply")
    layers = [{"product": v.dataset, "layer": v.band} for v in variables]
    return {
        "task_type": "area",
        "task_name": task_name or f"etd_{site.id}",
        "params": {
            "dates": [{"startDate": f"01-01-{start_year}", "endDate": f"12-31-{end_year}"}],
            "layers": layers,
            "output": {"format": {"type": "netcdf4"}, "projection": "geographic"},
            "geo": {
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "properties": {"site": site.id}, "geometry": bbox_polygon(site.bbox)}
                ],
            },
        },
    }


def year_chunks(start_year: int, end_year: int, n: int) -> list[tuple[int, int]]:
    """Split [start_year, end_year] into at most `n` contiguous, near-equal year ranges."""
    years = list(range(start_year, end_year + 1))
    n = max(1, min(n, len(years)))
    size = math.ceil(len(years) / n)
    return [(years[i], years[min(i + size, len(years)) - 1]) for i in range(0, len(years), size)]


# --------------------------------------------------------------------------- parsing


def _to_units(values: pd.Series, var: Variable) -> pd.Series:
    scale = 1.0 if STATS_ALREADY_SCALED else var.scale
    return values * scale + var.offset


def parse_stats_csv(path: Path, variables: Sequence[Variable]) -> dict[str, pd.Series]:
    """Parse an AppEEARS `*-Statistics.csv` into monthly series per variable id.

    Rows are filtered by the `Dataset` column (= layer name). Daily / 8-day dates
    are averaged per calendar month; months without data are NaN. Index is a
    month-start DatetimeIndex.
    """
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    result: dict[str, pd.Series] = {}
    for var in variables:
        rows = df[df["Dataset"].astype(str).str.strip() == var.band]
        if rows.empty:
            continue
        dates = pd.to_datetime(rows["Date"])
        mean = pd.to_numeric(rows["Mean"], errors="coerce")
        low, high = VALID_RANGE.get(var.band, (-np.inf, np.inf))
        mean = mean.where((mean >= low) & (mean <= high))
        if "Count" in rows:
            mean = mean.where(pd.to_numeric(rows["Count"], errors="coerce").fillna(0) > 0)
        daily = pd.Series(mean.to_numpy(dtype=float), index=pd.DatetimeIndex(dates)).sort_index()
        monthly = daily.resample("MS").mean()
        result[var.id] = _to_units(monthly, var).rename(var.id)
    return result


def parse_bundle(bundle_dir: Path, variables: Sequence[Variable]) -> dict[str, pd.Series]:
    """Merge every statistics CSV found in a downloaded bundle directory."""
    parts: dict[str, list[pd.Series]] = {}
    for csv in sorted(bundle_dir.rglob("*Statistics*.csv")):
        for var_id, series in parse_stats_csv(csv, variables).items():
            parts.setdefault(var_id, []).append(series)
    result: dict[str, pd.Series] = {}
    for var_id, chunks in parts.items():
        merged = pd.concat(chunks).groupby(level=0).mean().sort_index()
        full = pd.date_range(merged.index.min(), merged.index.max(), freq="MS")
        result[var_id] = merged.reindex(full).rename(var_id)
    return result


# --------------------------------------------------------------------------- tasks file


def load_tasks(cache_dir: Path = DEFAULT_CACHE_DIR) -> dict[str, TaskRecord]:
    path = cache_dir / TASKS_FILE
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        k: TaskRecord(
            key=k,
            site_id=v.get("site_id", k.split("@")[0]),
            task_id=v["task_id"],
            submitted_at=v["submitted_at"],
        )
        for k, v in raw.items()
    }


def save_tasks(tasks: Mapping[str, TaskRecord], cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        k: {"site_id": t.site_id, "task_id": t.task_id, "submitted_at": t.submitted_at}
        for k, t in tasks.items()
    }
    (cache_dir / TASKS_FILE).write_text(json.dumps(payload, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- HTTP


def load_token() -> str:
    load_dotenv(REPO_ROOT / ".env")
    token = os.environ.get("APPEEARS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("APPEEARS_TOKEN missing: put it in the repo-root .env")
    return token


def make_client(token: str) -> httpx.Client:
    return httpx.Client(
        base_url=API_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT_S,
        follow_redirects=True,
    )


def submit_task(client: httpx.Client, request: Mapping) -> str:
    response = client.post("/task", json=dict(request))
    if response.status_code >= 400:
        match = _TOO_LARGE_RE.search(response.text)
        if response.status_code == 400 and match:
            raise RequestTooLargeError(float(match.group(1)), response.text[:500])
        raise RuntimeError(f"AppEEARS submit failed {response.status_code}: {response.text[:500]}")
    return str(response.json()["task_id"])


def task_status(client: httpx.Client, task_id: str) -> dict:
    response = client.get(f"/task/{task_id}")
    response.raise_for_status()
    return response.json()


def list_bundle(client: httpx.Client, task_id: str) -> list[dict]:
    response = client.get(f"/bundle/{task_id}")
    response.raise_for_status()
    return list(response.json().get("files", []))


def download_bundle(
    client: httpx.Client, task_id: str, dest: Path, only_csv: bool = False
) -> list[Path]:
    """Download bundle files into `dest`, skipping files already present with the right size."""
    dest.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for f in list_bundle(client, task_id):
        name = Path(f["file_name"]).name
        if only_csv and not name.endswith(".csv"):
            continue
        target = dest / name
        size = f.get("file_size")
        if target.exists() and (size is None or target.stat().st_size == size):
            paths.append(target)
            continue
        logger.info("AppEEARS download %s -> %s", name, target)
        with client.stream("GET", f"/bundle/{task_id}/{f['file_id']}") as response:
            response.raise_for_status()
            tmp = target.with_suffix(target.suffix + ".part")
            with tmp.open("wb") as fh:
                for chunk in response.iter_bytes():
                    fh.write(chunk)
            tmp.replace(target)
        paths.append(target)
    return paths


def fetch_site_series(
    site_id: str, cache_dir: Path = DEFAULT_CACHE_DIR, catalog: Sequence[Variable] | None = None
) -> dict[str, pd.Series]:
    """Monthly series for a site from its already-downloaded bundle (no network)."""
    cat = catalog if catalog is not None else load_catalog()
    site = next(s for s in load_sites() if s.id == site_id)
    return parse_bundle(cache_dir / site_id, appeears_variables(cat, site))


# --------------------------------------------------------------------------- CLI


def submit_site(
    client: httpx.Client,
    site: Site,
    variables: Sequence[Variable],
    start_year: int = START_YEAR,
    end_year: int = END_YEAR,
    chunked: bool = False,
) -> list[TaskRecord]:
    """Submit one site, splitting by years (recursively) when AppEEARS says it is too large."""
    key = f"{site.id}@{start_year}-{end_year}" if chunked else site.id
    name = f"etd_{site.id}_{start_year}_{end_year}" if chunked else f"etd_{site.id}"
    request = build_area_request(site, variables, start_year, end_year, task_name=name)
    try:
        task_id = submit_task(client, request)
    except RequestTooLargeError as exc:
        n = math.ceil((1 + exc.overshoot_pct / 100) * SPLIT_MARGIN)
        if end_year == start_year:
            raise
        logger.info("%s %s-%s too large (+%.1f%%), splitting in %d", site.id, start_year, end_year, exc.overshoot_pct, n)
        records: list[TaskRecord] = []
        for y0, y1 in year_chunks(start_year, end_year, n):
            records.extend(submit_site(client, site, variables, y0, y1, chunked=True))
        return records
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    logger.info("%s: submitted %s layers=%s", key, task_id, [v.band for v in variables])
    return [TaskRecord(key, site.id, task_id, now)]


def cmd_submit(client: httpx.Client, sites: Sequence[Site], cache_dir: Path) -> None:
    catalog = load_catalog()
    tasks = load_tasks(cache_dir)
    for site in sites:
        existing = [t.task_id for t in tasks.values() if t.site_id == site.id]
        if existing:
            logger.info("%s: already submitted as %s, skipping", site.id, existing)
            continue
        variables = appeears_variables(catalog, site)
        if not variables:
            logger.info("%s: no appeears variables, skipping", site.id)
            continue
        new = submit_site(client, site, variables)
        tasks = {**tasks, **{r.key: r for r in new}}
        save_tasks(tasks, cache_dir)


def cmd_status(client: httpx.Client, cache_dir: Path) -> None:
    for key, rec in load_tasks(cache_dir).items():
        info = task_status(client, rec.task_id)
        logger.info("%s: %s status=%s", key, rec.task_id, info.get("status"))


def cmd_download(client: httpx.Client, cache_dir: Path, only_csv: bool) -> None:
    for key, rec in load_tasks(cache_dir).items():
        status = task_status(client, rec.task_id).get("status")
        if status != "done":
            logger.info("%s: %s not ready (status=%s)", key, rec.task_id, status)
            continue
        dest = cache_dir / rec.site_id
        paths = download_bundle(client, rec.task_id, dest, only_csv=only_csv)
        logger.info("%s: %d files in %s", key, len(paths), dest)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.extractors.appeears")
    parser.add_argument("command", choices=["submit", "status", "download"])
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--only-csv", action="store_true", help="download only the CSV files")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    with make_client(load_token()) as client:
        if args.command == "submit":
            cmd_submit(client, load_sites(), args.cache_dir)
        elif args.command == "status":
            cmd_status(client, args.cache_dir)
        else:
            cmd_download(client, args.cache_dir, args.only_csv)


if __name__ == "__main__":
    main()
