"""NASA POWER monthly point extractor (no auth).

API docs: https://power.larc.nasa.gov/docs/services/api/temporal/monthly/
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

POWER_MONTHLY_URL = "https://power.larc.nasa.gov/api/temporal/monthly/point"
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "power"
TIMEOUT_S = 60.0


def parse_monthly(payload: Mapping, bands: Mapping[str, str]) -> dict[str, pd.Series]:
    """Turn a POWER monthly JSON payload into one monthly series per variable id.

    `bands` maps our variable id -> POWER parameter name. Month "13" (annual mean)
    is dropped and the POWER fill value becomes NaN.
    """
    fill = payload.get("header", {}).get("fill_value", -999.0)
    parameters = payload["properties"]["parameter"]
    result: dict[str, pd.Series] = {}
    for var_id, band in bands.items():
        raw = parameters[band]
        months = {k: v for k, v in raw.items() if not k.endswith("13")}
        index = pd.to_datetime(list(months), format="%Y%m")
        values = np.array(list(months.values()), dtype=float)
        values[values == fill] = np.nan
        result[var_id] = pd.Series(values, index=index, name=var_id).sort_index()
    return result


def _cache_path(cache_dir: Path, params: Mapping[str, str]) -> Path:
    key = hashlib.sha256(json.dumps(dict(params), sort_keys=True).encode()).hexdigest()[:16]
    return cache_dir / f"monthly_{key}.json"


def fetch_monthly(
    lat: float,
    lon: float,
    bands: Mapping[str, str],
    start_year: int,
    end_year: int,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    client: httpx.Client | None = None,
) -> dict[str, pd.Series]:
    """Fetch monthly POWER series for a point, caching the raw JSON on disk."""
    params = {
        "parameters": ",".join(sorted(set(bands.values()))),
        "community": "AG",
        "latitude": f"{lat:.4g}",
        "longitude": f"{lon:.4g}",
        "start": str(start_year),
        "end": str(end_year),
        "format": "JSON",
    }
    path = _cache_path(cache_dir, params)
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        logger.info("POWER request lat=%s lon=%s %s-%s", lat, lon, start_year, end_year)
        own_client = client is None
        http = client or httpx.Client(timeout=TIMEOUT_S)
        try:
            response = http.get(POWER_MONTHLY_URL, params=params)
            response.raise_for_status()
            payload = response.json()
        finally:
            if own_client:
                http.close()
        series = parse_monthly(payload, bands)  # validate before caching
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return series
    return parse_monthly(payload, bands)
