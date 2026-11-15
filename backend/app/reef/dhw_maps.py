"""Heat-stress maps (NOAA Coral Reef Watch DHW) for the reef's hot years: an observed layer.

For each year where a reef point inside the site box reached 4 °C-weeks, the map is the DHW
grid on the day the hottest of those points peaked (January to June). One request per day
through `erddap.fetch_day_grid` (sequential, cached for past years, retried; a failed day is
never cached). It shows heat stress, not bleaching or coral death.

Files, under `layers/dhw/`: `dhw_<YYYY>.png`, `dhw_<YYYY>_values.png` (16-bit, shared
encoding) and `meta.json` (read by `layers._observed_layers`).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from collections.abc import Callable, Sequence
from pathlib import Path

import httpx
import numpy as np

from app.assets import maps
from app.extractors import erddap
from app.reef import dhw

logger = logging.getLogger(__name__)

LAYER_ID = "dhw"
STOPS = ("#fde68a", "#f97316", "#b91c1c")
RANGE = (0, 12)
PIXEL_M = 5000
_LOW, _MID, _HIGH = (tuple(int(s[i : i + 2], 16) for i in (1, 3, 5)) for s in STOPS)
_ALPHA = (120, 220, 230)


def _default_bbox() -> tuple[float, float, float, float]:
    from app.reef.points import SITE_ID
    from app.sites import load_sites

    return tuple(load_sites().get(SITE_ID).bbox)  # type: ignore[union-attr]


def hot_years(summary: dict, bbox: Sequence[float] | None = None) -> dict[int, str]:
    """Year -> date of the highest DHW among the points inside the site box that year,
    for the years where any of those points reached 4 °C-weeks (tested on the unrounded value
    through `years_at_or_above`; the displayed values are rounded)."""
    w, s, e, n = bbox if bbox is not None else _default_bbox()
    inside = [p for p in summary["points"] if w <= p["lon"] <= e and s <= p["lat"] <= n]
    hot = {y for p in inside for y in p["years_at_or_above"]["4"]}
    out: dict[int, str] = {}
    for year in sorted(hot):
        best: tuple[float, str] | None = None
        for p in inside:
            row = next((r for r in p["yearly_max"] if r["year"] == year), None)
            if row and row["value"] is not None and row["date"] and (best is None or row["value"] > best[0]):
                best = (row["value"], row["date"])
        if best:
            out[year] = best[1]
    return out


def colorize_dhw(values: np.ndarray) -> np.ndarray:
    """RGBA: NaN transparent, < 4 pale yellow, 4 to < 8 orange, >= 8 dark red (unrounded)."""
    values = np.asarray(values, dtype=float)
    out = np.zeros(values.shape + (4,), dtype=np.uint8)
    finite = np.isfinite(values)
    with np.errstate(invalid="ignore"):
        for mask, rgb, alpha in (
            (finite & (values < 4), _LOW, _ALPHA[0]),
            (finite & (values >= 4) & (values < 8), _MID, _ALPHA[1]),
            (finite & (values >= 8), _HIGH, _ALPHA[2]),
        ):
            out[mask] = (*rgb, alpha)
    return out


def _offline_client() -> httpx.Client:
    """A client that answers 404 to everything: offline reads the cache or fails at once."""
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(404, text="offline")))


def write_dhw_maps(
    summary: dict,
    bbox: Sequence[float],
    site_dir: Path,
    cache_dir: Path | None,
    client: httpx.Client | None,
    offline: bool = False,
    fetch_day: Callable[..., object] = erddap.fetch_day_grid,
) -> list[Path]:
    """Write the DHW map of each hot year; returns the files (empty when no year was hot).

    A day that cannot be read is left out and listed in `missing_years`; if none can be read,
    `ErddapError` is raised and nothing is written. `fetch_day` has the signature of
    `erddap.fetch_day_grid` (the reef build injects its own).
    """
    dates = hot_years(summary, bbox)
    if not dates:
        logger.info("dhw maps: no year reached 4 degree heating weeks inside the map")
        return []
    box = tuple(float(x) for x in bbox)
    if offline and client is None:
        client = _offline_client()
    grids: dict[int, np.ndarray] = {}
    missing: list[int] = []
    for year, day in dates.items():  # strictly sequential
        try:
            grid = fetch_day(
                dhw.DHW_DATASET, dhw.DHW_VAR, box, dt.date.fromisoformat(day), 1, client, cache_dir
            )
        except erddap.ErddapError as exc:
            logger.warning("dhw %s (%s) not read: %s", year, day, exc)
            missing.append(year)
            continue
        grids[year] = np.asarray(grid.sortby("latitude", ascending=False).values, dtype=float)  # north -> south
    if not grids:
        raise erddap.ErddapError("DHW: no hot-year day could be read")

    out_dir = site_dir / "layers" / LAYER_ID
    out_dir.mkdir(parents=True, exist_ok=True)
    size = maps.overlay_size(site_dir, box)
    offset, scale = maps.value_encoding(np.stack(list(grids.values())))
    written: list[Path] = []
    for year, values in grids.items():
        written.append(maps.save_png(colorize_dhw(values), size, out_dir / f"dhw_{year}.png"))
        written.append(maps.save_values_png(values, size, offset, scale, out_dir / f"dhw_{year}_values.png"))
    meta = {
        "id": LAYER_ID,
        "title": "Heat stress on the peak day of each hot year",
        "file_pattern": "layers/dhw/dhw_{YYYY}.png",
        "value_pattern": "layers/dhw/dhw_{YYYY}_values.png",
        "value_scale": scale,
        "value_offset": offset,
        "pixel_m": PIXEL_M,
        "years": list(grids),
        "dates": {str(y): dates[y] for y in grids},
        "missing_years": missing,
        "months": None,
        "range": list(RANGE),
        "unit": dhw.UNIT,
        "stops": list(STOPS),
        "legend": {
            "less": "below 4 °C-weeks",
            "more": "8 °C-weeks or more (Alert Level 2)",
            "transparent": "Transparent = land or no data",
        },
        "method": (
            "NOAA Coral Reef Watch daily degree heating weeks on the day the reef points "
            "inside this map peaked that year (January–June)."
        ),
        "source": dict(dhw.SOURCE),
    }
    path = out_dir / "meta.json"
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    written.append(path)
    return written
