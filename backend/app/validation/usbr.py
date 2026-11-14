"""Lake Mead end-of-month water surface elevation (U.S. Bureau of Reclamation).

Not NASA data: used only to VALIDATE the NASA-based story (GRACE water storage, MODIS
water area). Source table: https://www.usbr.gov/lc/region/g4000/hourly/mead-elv.html
(public domain, U.S. Government work). Values are feet above mean sea level.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

USBR_MEAD_URL = "https://www.usbr.gov/lc/region/g4000/hourly/mead-elv.html"
DEFAULT_CACHE = Path(__file__).resolve().parents[2] / "data" / "cache" / "usbr" / "mead-elv.html"
FEET_TO_M = 0.3048
TIMEOUT_S = 60.0

_ROW_RE = re.compile(r"<TR>\s*<TH>\s*(\d{4})\s*</TH>(.*?)</TR>", re.I | re.S)
_CELL_RE = re.compile(r"<TD>(.*?)</TD>", re.I | re.S)


def _to_float(cell: str) -> float:
    text = re.sub(r"<[^>]+>|&nbsp;", "", cell).strip()
    try:
        return float(text)
    except ValueError:
        return float("nan")


def parse_elevation_table(html: str) -> pd.Series:
    """Monthly end-of-month elevation in metres, month-start index, NaN for empty cells."""
    values: dict[pd.Timestamp, float] = {}
    for year, row in _ROW_RE.findall(html):
        cells = _CELL_RE.findall(row)[:12]
        for month, cell in enumerate(cells, start=1):
            values[pd.Timestamp(int(year), month, 1)] = _to_float(cell) * FEET_TO_M
    if not values:
        raise ValueError("no year rows found in USBR elevation table")
    series = pd.Series(values, name="mead_elevation_m").sort_index()
    return series.where(np.isfinite(series))


def fetch_mead_elevation(
    start_year: int = 2003, end_year: int = 2024, cache_path: Path = DEFAULT_CACHE
) -> pd.Series:
    """Lake Mead elevation (m) for [start_year, end_year], cached on disk."""
    if cache_path.exists():
        html = cache_path.read_text(encoding="utf-8")
    else:
        logger.info("USBR request %s", USBR_MEAD_URL)
        response = httpx.get(USBR_MEAD_URL, timeout=TIMEOUT_S, follow_redirects=True)
        response.raise_for_status()
        html = response.text
        parse_elevation_table(html)  # validate before caching
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(html, encoding="utf-8")
    series = parse_elevation_table(html)
    full = pd.date_range(f"{start_year}-01-01", f"{end_year}-12-01", freq="MS")
    return series.reindex(full).rename("mead_elevation_m")
