"""AppEEARS area extractor (MODIS NDVI, LST, ET, snow) — Earthdata Login token.

API docs: https://appeears.earthdatacloud.nasa.gov/api/

Flow: one *area* task per site (bbox polygon, every applicable appeears layer) ->
poll status -> download the bundle -> parse the per-product statistics CSV
(area mean per date) into monthly series in catalog units.

Snow cover is computed pixel-wise from the MOD10A1 NetCDF when present (flags > 100
masked per pixel before averaging); the stats CSV is only a fallback for it.

CLI (run from backend/ with the venv active):
    python -m app.extractors.appeears submit|status|download
    python -m app.extractors.appeears watch [--interval 600] [--build]
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import xarray as xr
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
# ScaleFactor applied (e.g. NDVI ~0.4, LST ~300 K). So by default we do NOT multiply
# by the catalog `scale` again; only the catalog `offset` (e.g. K -> °C) is applied.
# Safety net: if a layer's median stats mean is outside VALID_RANGE but inside it once
# scaled, the CSV holds raw DNs and the scale is applied (logged), see `_stats_scale`.
STATS_ALREADY_SCALED = True

# Pixel-wise snow cover: a month is NaN when fewer than this share of its pixel-days
# carry a real 0-100 NDSI snow value (the rest are cloud/night/water/fill flags).
SNOW_MIN_VALID_FRACTION = 0.2
SNOW_BAND = "NDSI_Snow_Cover"
WATER_SUFFIX = "_water"
DONE_MARKER = ".done_{task_id}"
WATCH_FINAL = frozenset({"done", "error", "deleted", "expired"})

# Plausible range of a site-mean monthly value in catalog units; outside -> warning
# (wrong scale/offset), never silently corrected.
PLAUSIBLE: Mapping[str, tuple[float, float]] = {
    "lst_day": (-40.0, 80.0),
    "ndvi": (-0.2, 1.0),
    "et": (0.0, 120.0),
    "snow_cover": (0.0, 100.0),
}

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


def _stats_scale(mean: pd.Series, var: Variable) -> float:
    """Scale to apply to stats-CSV means of `var` (1.0 when AppEEARS already scaled them)."""
    default = 1.0 if STATS_ALREADY_SCALED else var.scale
    if var.scale == 1.0 or var.band not in VALID_RANGE:
        return default
    finite = mean[np.isfinite(mean)]
    if finite.empty:
        return default
    low, high = VALID_RANGE[var.band]
    median = float(finite.median())
    as_is = low <= median * default <= high
    if not as_is:
        other = var.scale if default == 1.0 else 1.0
        if low <= median * other <= high:
            logger.warning("%s: stats CSV median %.4g implies scale %g, not %g", var.band, median, other, default)
            return other
    return default


def _to_units(values: pd.Series, var: Variable, scale: float | None = None) -> pd.Series:
    applied = (1.0 if STATS_ALREADY_SCALED else var.scale) if scale is None else scale
    return values * applied + var.offset


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
        scale = _stats_scale(mean, var)
        mean = mean * scale
        low, high = VALID_RANGE.get(var.band, (-np.inf, np.inf))
        mean = mean.where((mean >= low) & (mean <= high))
        if "Count" in rows:
            mean = mean.where(pd.to_numeric(rows["Count"], errors="coerce").fillna(0) > 0)
        daily = pd.Series(mean.to_numpy(dtype=float), index=pd.DatetimeIndex(dates)).sort_index()
        monthly = daily.resample("MS").mean()
        result[var.id] = _to_units(monthly, var, scale=1.0).rename(var.id)
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
    variables = appeears_variables(cat, site)
    bundle = cache_dir / site_id
    result = parse_bundle(bundle, variables)
    for var in variables:
        if var.band != SNOW_BAND:
            continue
        pixel = snow_cover_monthly(bundle)
        if pixel is not None and pixel.notna().any():
            logger.info("%s: snow_cover from pixel-wise MOD10A1 NetCDF (%d months)", site_id, pixel.notna().sum())
            result = {**result, var.id: pixel.rename(var.id)}
        elif var.id in result:
            logger.info("%s: snow_cover from stats CSV (no MOD10A1 NetCDF)", site_id)
    check_units(result)
    return result


def check_units(series: Mapping[str, pd.Series]) -> list[str]:
    """Warn (and return the ids) of series whose median is outside PLAUSIBLE."""
    bad = []
    for var_id, s in series.items():
        if var_id not in PLAUSIBLE or s.notna().sum() == 0:
            continue
        low, high = PLAUSIBLE[var_id]
        median = float(s.median())
        if not low <= median <= high:
            logger.warning("%s: median %.4g outside plausible %s - check scale/offset", var_id, median, (low, high))
            bad.append(var_id)
    return bad


# --------------------------------------------------------------------------- NetCDF grids


def nc_times(values: np.ndarray) -> pd.DatetimeIndex:
    """DatetimeIndex from decoded NetCDF times (numpy datetime64 or cftime, e.g. julian)."""
    arr = np.asarray(values)
    if np.issubdtype(arr.dtype, np.datetime64):
        return pd.DatetimeIndex(arr)
    return pd.DatetimeIndex([pd.Timestamp(t.year, t.month, t.day) for t in arr.ravel()])


def _nc_files(bundle_dir: Path) -> list[Path]:
    return sorted(p for p in bundle_dir.rglob("*.nc") if p.is_file()) if bundle_dir.is_dir() else []


def open_layer(bundle_dir: Path, band: str) -> xr.DataArray | None:
    """One layer over (time, lat, lon) merged across every NetCDF (year chunks) in a bundle.

    CF decoding is on: `_FillValue` -> NaN and `scale_factor`/`add_offset` applied when
    the file carries them (check `da.attrs["etd_scaled"]`). Time is a pandas index; lat
    is sorted north -> south.
    """
    parts = []
    scaled = False
    for path in _nc_files(bundle_dir):
        with xr.open_dataset(path) as ds:
            if band not in ds.data_vars:
                continue
            da = ds[band].load()
        scaled = scaled or "scale_factor" in da.encoding
        da = da.assign_coords(time=nc_times(da["time"].values))
        parts.append(da)
    if not parts:
        return None
    merged = xr.concat(parts, dim="time") if len(parts) > 1 else parts[0]
    merged = merged.sortby("time")
    _, keep = np.unique(merged["time"].values, return_index=True)
    merged = merged.isel(time=np.sort(keep)).sortby("lat", ascending=False)
    merged.attrs = {**merged.attrs, "etd_scaled": bool(scaled)}
    return merged


def layer_to_units(da: xr.DataArray, var: Variable) -> xr.DataArray:
    """Catalog units, with flag values outside VALID_RANGE masked per pixel (NaN)."""
    values = da.astype(float)
    if not da.attrs.get("etd_scaled", False):
        values = values * var.scale
    low, high = VALID_RANGE.get(var.band, (-np.inf, np.inf))
    values = values.where((values >= low) & (values <= high))
    return values + var.offset


def monthly_grid(
    da: xr.DataArray, min_valid_fraction: float = 0.0
) -> tuple[pd.DatetimeIndex, np.ndarray]:
    """Per-pixel monthly mean over valid observations -> (month starts, (M, ny, nx)).

    A pixel-month is NaN when its valid share of observations is below `min_valid_fraction`.
    """
    times = pd.DatetimeIndex(da["time"].values)
    data = np.asarray(da.values, dtype=float)
    months = times.to_period("M")
    uniq = months.unique().sort_values()
    out = np.full((len(uniq),) + data.shape[1:], np.nan)
    for k, m in enumerate(uniq):
        block = data[np.asarray(months == m)]
        valid = np.isfinite(block)
        count = valid.sum(axis=0)
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = np.where(valid, block, 0.0).sum(axis=0) / count
        frac = count / block.shape[0]
        out[k] = np.where((count > 0) & (frac >= min_valid_fraction), mean, np.nan)
    return uniq.to_timestamp(), out


def snow_cover_monthly(
    bundle_dir: Path, min_valid_fraction: float = SNOW_MIN_VALID_FRACTION
) -> pd.Series | None:
    """Site-mean monthly snow cover (%) from MOD10A1 NDSI_Snow_Cover, pixel-wise.

    Values > 100 (200-254 cloud/night/water/... flags, 255 fill) are masked per pixel
    BEFORE averaging. Monthly value = mean over all valid pixel-days of the month; NaN
    when valid pixel-days < `min_valid_fraction` of all pixel-days. None if no NetCDF.
    """
    da = open_layer(bundle_dir, SNOW_BAND)
    if da is None:
        return None
    data = np.asarray(da.values, dtype=float)
    data = np.where((data >= 0) & (data <= 100), data, np.nan)
    times = pd.DatetimeIndex(da["time"].values)
    flat = data.reshape(data.shape[0], -1)
    frame = pd.DataFrame(
        {"sum": np.nansum(flat, axis=1), "valid": np.isfinite(flat).sum(axis=1), "total": flat.shape[1]},
        index=times,
    )
    monthly = frame.resample("MS").sum()
    with np.errstate(invalid="ignore", divide="ignore"):
        value = monthly["sum"] / monthly["valid"]
    ok = (monthly["total"] > 0) & (monthly["valid"] >= min_valid_fraction * monthly["total"])
    return value.where(ok).rename("snow_cover")


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


def bundle_dest(cache_dir: Path, rec: TaskRecord) -> Path:
    """Download folder: `<site>/` or `<site>/<y0-y1>/` for a year chunk (chunk files share names)."""
    base = cache_dir / rec.site_id
    return base / rec.key.split("@", 1)[1] if "@" in rec.key else base


def water_bundle_dir(site_id: str, cache_dir: Path = DEFAULT_CACHE_DIR) -> Path:
    return cache_dir / f"{site_id}{WATER_SUFFIX}"


def is_downloaded(cache_dir: Path, rec: TaskRecord) -> bool:
    return (bundle_dest(cache_dir, rec) / DONE_MARKER.format(task_id=rec.task_id)).exists()


def download_task(client: httpx.Client, cache_dir: Path, rec: TaskRecord, only_csv: bool = False) -> list[Path]:
    dest = bundle_dest(cache_dir, rec)
    paths = download_bundle(client, rec.task_id, dest, only_csv=only_csv)
    if not only_csv:
        (dest / DONE_MARKER.format(task_id=rec.task_id)).write_text(
            datetime.now(timezone.utc).isoformat(timespec="seconds"), encoding="utf-8"
        )
    logger.info("%s: %d files in %s", rec.key, len(paths), dest)
    return paths


def cmd_download(client: httpx.Client, cache_dir: Path, only_csv: bool) -> None:
    for key, rec in load_tasks(cache_dir).items():
        status = task_status(client, rec.task_id).get("status")
        if status != "done":
            logger.info("%s: %s not ready (status=%s)", key, rec.task_id, status)
            continue
        download_task(client, cache_dir, rec, only_csv=only_csv)


def story_site(site_id: str) -> str:
    """Story-mode site a task feeds (`lake_mead_water` -> `lake_mead`)."""
    return site_id.removesuffix(WATER_SUFFIX)


def build_site_assets(site_id: str) -> None:
    """Maps + site.json for a site whose bundles are all in; failures are logged, not raised."""
    if site_id not in {s.id for s in load_sites()}:
        logger.info("build: %s is not a story site, nothing to build", site_id)
        return
    for module, args in (("app.assets.maps", [site_id]), ("app.site_export", [site_id])):
        cmd = [sys.executable, "-m", module, *args]
        logger.info("build: %s", " ".join(cmd[1:]))
        result = subprocess.run(cmd, cwd=BACKEND_DIR, check=False)
        if result.returncode != 0:
            logger.warning("build: %s exited %d", module, result.returncode)


def watch(
    client: httpx.Client,
    cache_dir: Path,
    interval: float = 600.0,
    max_rounds: int | None = None,
    sleep=time.sleep,
    on_site_complete=None,
) -> dict[str, str]:
    """Poll every task; download each as soon as it is `done`. Returns final status per key.

    Idempotent: a task with a done-marker is never re-downloaded. Exits when every task
    is downloaded or in a final non-done state (error/deleted/expired); tasks.json is re-read
    every round. A transient HTTP
    error only skips that task this round. `on_site_complete(story_site_id)` runs once per
    story site when all of its tasks (incl. `<site>_water`) are downloaded.
    """
    final: dict[str, str] = {}
    built: set[str] = set()
    rounds = 0
    while True:
        rounds += 1
        tasks = load_tasks(cache_dir)  # re-read: tasks submitted meanwhile are picked up
        final = {**final, **{k: "done" for k, r in tasks.items() if is_downloaded(cache_dir, r)}}
        for key, rec in tasks.items():
            if key in final:
                continue
            try:
                status = str(task_status(client, rec.task_id).get("status"))
                if status == "done":
                    download_task(client, cache_dir, rec)
                    final[key] = "done"
                elif status in WATCH_FINAL:
                    logger.error("%s: task %s ended with status=%s", key, rec.task_id, status)
                    final[key] = status
                else:
                    logger.info("%s: status=%s", key, status)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (401, 403):
                    raise RuntimeError("AppEEARS token rejected (expired?): log in again") from exc
                logger.warning("%s: HTTP %s, retry next round", key, exc.response.status_code)
            except httpx.HTTPError as exc:
                logger.warning("%s: %s, retry next round", key, type(exc).__name__)
        if on_site_complete is not None:
            for site_id in sorted({story_site(r.site_id) for r in tasks.values()} - built):
                keys = [k for k, r in tasks.items() if story_site(r.site_id) == site_id]
                if all(final.get(k) == "done" for k in keys):
                    built.add(site_id)
                    on_site_complete(site_id)
        pending = [k for k in tasks if k not in final]
        logger.info("watch round %d: %d/%d downloaded, pending=%s", rounds, sum(v == "done" for v in final.values()), len(tasks), pending)
        if not pending or (max_rounds is not None and rounds >= max_rounds):
            return final
        sleep(interval)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.extractors.appeears")
    parser.add_argument("command", choices=["submit", "status", "download", "watch"])
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--only-csv", action="store_true", help="download only the CSV files")
    parser.add_argument("--interval", type=float, default=600.0, help="watch: seconds between polls")
    parser.add_argument("--build", action="store_true", help="watch: build maps + site.json per finished site")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    with make_client(load_token()) as client:
        if args.command == "submit":
            cmd_submit(client, load_sites(), args.cache_dir)
        elif args.command == "status":
            cmd_status(client, args.cache_dir)
        elif args.command == "watch":
            hook = build_site_assets if args.build else None
            final = watch(client, args.cache_dir, args.interval, on_site_complete=hook)
            logger.info("watch finished: %s", final)
        else:
            cmd_download(client, args.cache_dir, args.only_csv)


if __name__ == "__main__":
    main()
