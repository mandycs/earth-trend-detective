"""GLDAS Noah 0.25 deg monthly extractor (soil moisture, surface runoff).

Why this access path: the GES DISC Hydrology Data Rods service and the on-prem
GES DISC OPeNDAP (hydro1) were both retired (HTTP 410). The replacement is
Earthdata Cloud OPeNDAP (Hyrax): we list the monthly granules of
GLDAS_NOAH025_M v2.1 in CMR and ask Cloud OPeNDAP for a 3x3-cell subset around
the site point (DAP4 CSV, a few hundred bytes per granule). One request per month.

Docs: https://disc.gsfc.nasa.gov/information/howto (OPeNDAP in the cloud)
README: https://docserver.gesdisc.eosdis.nasa.gov/public/project/hydrology/README_GLDAS2.pdf
"""

from __future__ import annotations

import logging
import math
import os
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import httpx
import numpy as np
import pandas as pd
import yaml
from dotenv import load_dotenv

from app.catalog import Variable, load_catalog

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
SITES_PATH = BACKEND_DIR / "catalog" / "sites.yaml"
DEFAULT_CACHE_DIR = BACKEND_DIR / "data" / "cache" / "gldas"

COLLECTION_ID = "C1342986036-GES_DISC"  # GLDAS_NOAH025_M v2.1 (2000-present)
SHORT_NAME = "GLDAS_NOAH025_M"
VERSION = "2.1"
CMR_GRANULES_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
OPENDAP_BASE = f"https://opendap.earthdata.nasa.gov/collections/{COLLECTION_ID}/granules"

# Grid: cell centres lat -59.875..89.875 (600), lon -179.875..179.875 (1440).
GRID_RES = 0.25
LAT0, NLAT = -59.875, 600
LON0, NLON = -179.875, 1440
FILL_VALUE = -9999.0
HALF_WINDOW = 1  # 3x3 cells; centre used, window mean as fallback over masked cells

TIMEOUT_S = 120.0
MAX_WORKERS = 8
RETRIES = 3


@dataclass(frozen=True)
class Granule:
    month: pd.Timestamp
    ur: str  # e.g. "GLDAS_NOAH025_M.2.1:GLDAS_NOAH025_M.A200301.021.nc4"


def gldas_variables(catalog: Sequence[Variable]) -> tuple[Variable, ...]:
    return tuple(v for v in catalog if v.source == "gldas")


def grid_index(lat: float, lon: float) -> tuple[int, int]:
    """Nearest GLDAS 0.25 deg cell (row, col) for a point."""
    i = int(round((lat - LAT0) / GRID_RES))
    j = int(round((lon - LON0) / GRID_RES))
    if not (0 <= i < NLAT and 0 <= j < NLON):
        raise ValueError(f"point lat={lat} lon={lon} outside GLDAS grid (60S-90N)")
    return i, j


def window(i: int, j: int, half: int = HALF_WINDOW) -> tuple[slice, slice]:
    return (
        slice(max(i - half, 0), min(i + half, NLAT - 1) + 1),
        slice(max(j - half, 0), min(j + half, NLON - 1) + 1),
    )


def constraint_expression(bands: Sequence[str], rows: slice, cols: slice) -> str:
    r = f"[{rows.start}:{rows.stop - 1}]"
    c = f"[{cols.start}:{cols.stop - 1}]"
    parts = [f"/{band}[0]{r}{c}" for band in sorted(set(bands))]
    return ";".join([*parts, f"/lat{r}", f"/lon{c}"])


def subset_url(granule_ur: str, ce: str) -> str:
    # Hyrax (Tomcat) rejects raw brackets: everything must be percent-encoded.
    return f"{OPENDAP_BASE}/{quote(granule_ur, safe='')}.dap.csv?dap4.ce={quote(ce, safe='')}"


def parse_dap_csv(text: str) -> dict[str, np.ndarray]:
    """Parse a Hyrax DAP4 CSV response into {variable: 2-D array (lat, lon)}.

    Coordinate lines look like `/lat, 36.125, 36.375`; data rows look like
    `/Qs_acc[0][1], 5.9e-06, 3.8e-06` (one line per lat row). Fill -> NaN.
    """
    rows: dict[str, list[list[float]]] = {}
    for line in text.splitlines():
        if not line.startswith("/"):
            continue
        name, *values = (part.strip() for part in line.split(","))
        var = name.lstrip("/").split("[", 1)[0]
        rows.setdefault(var, []).append([float(v) for v in values if v])
    result: dict[str, np.ndarray] = {}
    for var, data in rows.items():
        arr = np.array(data, dtype=float)
        if var not in ("lat", "lon", "time"):
            arr[arr <= FILL_VALUE] = np.nan
        result[var] = arr
    return result


def cell_value(arr: np.ndarray, centre: tuple[int, int]) -> float:
    """Centre cell value; nan-mean of the window if the centre is masked (e.g. lake)."""
    value = float(arr[centre])
    if math.isnan(value):
        finite = arr[np.isfinite(arr)]
        value = float(finite.mean()) if finite.size else math.nan
    return value


def load_token() -> str:
    load_dotenv(REPO_ROOT / ".env")
    token = os.environ.get("NASA_TOKEN", "").strip()
    if not token:
        raise RuntimeError("NASA_TOKEN missing: put an Earthdata Login token in the repo-root .env")
    return token


def list_granules(
    start_year: int, end_year: int, client: httpx.Client, page_size: int = 500
) -> tuple[Granule, ...]:
    """Monthly granules in [start_year, end_year] from CMR (no auth needed)."""
    params = {
        "short_name": SHORT_NAME,
        "version": VERSION,
        "temporal": f"{start_year}-01-01T00:00:00Z,{end_year}-12-31T23:59:59Z",
        "page_size": str(page_size),
        "sort_key": "start_date",
    }
    granules: list[Granule] = []
    page = 1
    while True:
        response = client.get(CMR_GRANULES_URL, params={**params, "page_num": str(page)})
        response.raise_for_status()
        entries = response.json()["feed"]["entry"]
        for entry in entries:
            month = pd.Timestamp(entry["time_start"][:7] + "-01")
            if start_year <= month.year <= end_year:
                granules.append(Granule(month=month, ur=entry["title"]))
        if len(entries) < page_size:
            break
        page += 1
    unique = {g.month: g for g in granules}
    return tuple(unique[m] for m in sorted(unique))


def _get_with_retry(client: httpx.Client, url: str) -> str:
    for attempt in range(1, RETRIES + 1):
        try:
            response = client.get(url)
            if response.status_code < 500:
                response.raise_for_status()
                return response.text
            logger.warning("GLDAS OPeNDAP %s (attempt %d)", response.status_code, attempt)
        except httpx.TransportError as exc:
            logger.warning("GLDAS OPeNDAP transport error %s (attempt %d)", exc, attempt)
        time.sleep(2**attempt)
    raise RuntimeError(f"GLDAS OPeNDAP failed after {RETRIES} attempts: {url.split('?')[0]}")


def _fetch_granule(
    granule: Granule, ce: str, cache_file: Path, client: httpx.Client
) -> dict[str, np.ndarray]:
    if cache_file.exists():
        text = cache_file.read_text(encoding="utf-8")
    else:
        text = _get_with_retry(client, subset_url(granule.ur, ce))
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(text, encoding="utf-8")
    return parse_dap_csv(text)


def fetch_monthly(
    lat: float,
    lon: float,
    variables: Sequence[Variable],
    start_year: int,
    end_year: int,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    client: httpx.Client | None = None,
    max_workers: int = MAX_WORKERS,
) -> dict[str, pd.Series]:
    """Monthly GLDAS series at a point, in catalog units (raw * scale + offset).

    Raw OPeNDAP CSV subsets are cached per grid cell and month under `cache_dir`.
    """
    i, j = grid_index(lat, lon)
    rows, cols = window(i, j)
    centre = (i - rows.start, j - cols.start)
    ce = constraint_expression([v.band for v in variables], rows, cols)
    cell_dir = cache_dir / f"cell_{i}_{j}"

    own_client = client is None
    http = client or httpx.Client(
        headers={"Authorization": f"Bearer {load_token()}"},
        follow_redirects=True,
        timeout=TIMEOUT_S,
    )
    try:
        granules = list_granules(start_year, end_year, http)
        logger.info("GLDAS cell (%d,%d): %d monthly granules", i, j, len(granules))

        def work(g: Granule) -> dict[str, np.ndarray]:
            return _fetch_granule(g, ce, cell_dir / f"{g.month:%Y%m}.csv", http)

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            subsets = list(pool.map(work, granules))
    finally:
        if own_client:
            http.close()

    full_index = pd.date_range(f"{start_year}-01-01", f"{end_year}-12-01", freq="MS")
    result: dict[str, pd.Series] = {}
    for var in variables:
        values = [cell_value(s[var.band], centre) if var.band in s else math.nan for s in subsets]
        raw = pd.Series(values, index=pd.DatetimeIndex([g.month for g in granules]), dtype=float)
        series = raw.reindex(full_index) * var.scale + var.offset
        result[var.id] = series.rename(var.id)
    return result


def load_site_points(path: Path = SITES_PATH) -> tuple[tuple[str, float, float], ...]:
    """(site_id, lat, lon) for each site; sites.yaml stores point as [lon, lat]."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return tuple((s["id"], float(s["point"][1]), float(s["point"][0])) for s in data["sites"])


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    variables = gldas_variables(load_catalog())
    start, end = yaml.safe_load(SITES_PATH.read_text(encoding="utf-8"))["study_period"]
    for site_id, lat, lon in load_site_points():
        series = fetch_monthly(lat, lon, variables, int(start), int(end))
        print(f"\n{site_id} (lat={lat}, lon={lon}) cell={grid_index(lat, lon)}")
        for var in variables:
            s = series[var.id]
            if s.notna().sum() == 0:
                print(f"  {var.id:14s} no data")
                continue
            print(
                f"  {var.id:14s} n={s.notna().sum():3d}/{len(s)} "
                f"mean={s.mean():.3f} min={s.min():.3f} max={s.max():.3f} {var.units} "
                f"[{s.first_valid_index():%Y-%m} .. {s.last_valid_index():%Y-%m}]"
            )


if __name__ == "__main__":
    main()
