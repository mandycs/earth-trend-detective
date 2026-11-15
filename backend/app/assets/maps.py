"""Story-mode raster maps from the AppEEARS NetCDF grids.

Usage (from backend/, venv active):  python -m app.assets.maps <site_id> [...]

Writes into sites/<id>/:
- trend_<var>.png + trend_<var>.json : per-pixel Sen slope per decade of deseasonalized
  anomalies, diverging colours centred at 0; pixels with Mann-Kendall p >= 0.05 faded.
- year_<var>_<YYYY>.png + year_<var>.json : annual mean anomaly per pixel, 2003-2024, one
  symmetric colour scale shared by every year.
- year_water_<YYYY>.png + year_water.json : open-water mask (blue on transparent) from the
  `<site>_water` MOD09A1 bundle (Lake Mead shrinking).

PNGs are RGBA, cropped to the site bbox and resized (nearest, no smoothing) to the
aspect of base.jpg, so they overlay base.jpg / the heightmap 1:1.

Simplification vs the site-level test (app/stats/trend.py, MK Hamed-Rao on ~264
monthly anomalies): per pixel we run on the ANNUAL means of the monthly anomalies
(22 values). Sen slope = median of the 231 pairwise slopes between years; MK S = sum
of the pairwise signs, Var(S) = n(n-1)(2n+5)/18 (no tie or autocorrelation correction,
annual averaging already removes most of the month-to-month autocorrelation). All of it
is vectorized over pixels with numpy; pymannkendall per pixel would be far too slow.
The map is a picture of where the change is; the verdict still comes from the site test.
"""

from __future__ import annotations

import argparse
import json
import logging
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
from PIL import Image
from scipy.stats import norm

from app.catalog import Variable, load_catalog
from app.extractors import appeears, water

logger = logging.getLogger(__name__)

SITES_DIR = Path(__file__).resolve().parents[3] / "sites"
START_YEAR = 2003
END_YEAR = 2024
SIG_LEVEL = 0.05
MIN_YEARS = 8  # valid annual means a pixel needs for a trend
MIN_MONTHS_PER_YEAR = 6  # valid monthly anomalies a pixel-year needs for an annual mean
SCALE_PERCENTILE = 98.0  # colour scale = this percentile of |values| (robust to outliers)
ALPHA_SIGNIFICANT = 230
ALPHA_FADED = 70
ALPHA_YEAR = 220
OVERLAY_MAX_WIDTH = 1024
ROW_BLOCK = 64  # rows per block in the pairwise computation (caps memory)
WATER_RGBA = (30, 120, 255, 220)
LEGEND_STOPS = 9


@dataclass(frozen=True)
class Style:
    colormap: str  # matplotlib name; low end = "less", high end = "more"
    more: str
    less: str


STYLES: Mapping[str, Style] = {
    "lst_day": Style("RdBu_r", "↑ more heat (warmer ground)", "↓ less heat (cooler ground)"),
    "ndvi": Style("BrBG", "↑ more plant greenness", "↓ less plant greenness"),
    "et": Style("BrBG", "↑ more water evaporated", "↓ less water evaporated"),
    "snow_cover": Style("RdBu", "↑ more snow cover", "↓ less snow cover"),
    "sst": Style("RdBu_r", "↑ warmer water", "↓ cooler water"),
}


def style_for(var: Variable) -> Style:
    return STYLES.get(var.id, Style("RdBu_r", f"↑ more {var.label.lower()}", f"↓ less {var.label.lower()}"))


# --------------------------------------------------------------------------- statistics


def deseasonalize(times: pd.DatetimeIndex, cube: np.ndarray) -> np.ndarray:
    """Per-pixel anomaly: value minus that calendar month's mean over the record."""
    out = np.full_like(cube, np.nan, dtype=float)
    months = np.asarray(times.month)
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for m in range(1, 13):
            sel = months == m
            if sel.any():
                out[sel] = cube[sel] - np.nanmean(cube[sel], axis=0)
    return out


def annual_means(
    times: pd.DatetimeIndex,
    anomalies: np.ndarray,
    years: Sequence[int],
    min_months: int = MIN_MONTHS_PER_YEAR,
) -> np.ndarray:
    """(Y, ny, nx) annual mean of monthly anomalies; NaN when < `min_months` valid months."""
    out = np.full((len(years),) + anomalies.shape[1:], np.nan)
    year_of = np.asarray(times.year)
    for k, y in enumerate(years):
        block = anomalies[year_of == y]
        if block.size == 0:
            continue
        count = np.isfinite(block).sum(axis=0)
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = np.nansum(block, axis=0) / count
        out[k] = np.where(count >= min_months, mean, np.nan)
    return out


def sen_mk_grid(
    years: Sequence[int], annual: np.ndarray, min_years: int = MIN_YEARS
) -> tuple[np.ndarray, np.ndarray]:
    """Per-pixel (Sen slope per decade, MK two-sided p) on annual means, vectorized.

    Pairs with a NaN year are skipped; pixels with < `min_years` valid years are NaN.
    """
    t = np.asarray(years, dtype=float)
    i, j = np.triu_indices(len(t), k=1)
    dt = (t[j] - t[i])[:, None, None]
    ny = annual.shape[1]
    slope = np.full(annual.shape[1:], np.nan)
    pval = np.full(annual.shape[1:], np.nan)
    n_valid = np.isfinite(annual).sum(axis=0)
    for r0 in range(0, ny, ROW_BLOCK):
        block = annual[:, r0 : r0 + ROW_BLOCK]
        diff = block[j] - block[i]
        with np.errstate(invalid="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            slope[r0 : r0 + ROW_BLOCK] = np.nanmedian(diff / dt, axis=0) * 10.0
        s = np.nansum(np.sign(diff), axis=0)
        n = n_valid[r0 : r0 + ROW_BLOCK].astype(float)
        var_s = n * (n - 1) * (2 * n + 5) / 18.0
        with np.errstate(invalid="ignore", divide="ignore"):
            z = (s - np.sign(s)) / np.sqrt(var_s)
        pval[r0 : r0 + ROW_BLOCK] = 2.0 * norm.sf(np.abs(z))
    enough = n_valid >= min_years
    return np.where(enough, slope, np.nan), np.where(enough, pval, np.nan)


def symmetric_limit(values: np.ndarray, percentile: float = SCALE_PERCENTILE) -> float:
    finite = np.abs(values[np.isfinite(values)])
    if finite.size == 0:
        return 1.0
    v = float(np.percentile(finite, percentile))
    return v if v > 0 else float(finite.max()) or 1.0


# --------------------------------------------------------------------------- rendering


def colorize(values: np.ndarray, vmax: float, colormap: str, alpha: np.ndarray | int) -> np.ndarray:
    """RGBA uint8 grid; NaN -> fully transparent; colour scale [-vmax, vmax] centred at 0."""
    cmap = matplotlib.colormaps[colormap]
    norm01 = np.clip((np.nan_to_num(values) + vmax) / (2 * vmax), 0.0, 1.0)
    rgba = (cmap(norm01) * 255).astype(np.uint8)
    a = np.broadcast_to(np.asarray(alpha, dtype=np.uint8), values.shape)
    rgba[..., 3] = np.where(np.isfinite(values), a, 0)
    return rgba


def legend_stops(colormap: str, n: int = LEGEND_STOPS) -> list[str]:
    cmap = matplotlib.colormaps[colormap]
    return [matplotlib.colors.to_hex(cmap(x)) for x in np.linspace(0, 1, n)]


def crop_to_bbox(
    grid: np.ndarray, lat: np.ndarray, lon: np.ndarray, bbox: Sequence[float]
) -> np.ndarray:
    """Rows/cols whose pixel centre lies inside bbox (lat is north -> south)."""
    w, s, e, n = bbox
    rows = (lat >= s) & (lat <= n)
    cols = (lon >= w) & (lon <= e)
    if not rows.any() or not cols.any():
        return grid
    return grid[np.ix_(rows, cols)]


def overlay_size(site_dir: Path, bbox: Sequence[float]) -> tuple[int, int]:
    """(width, height) with base.jpg's aspect (else the bbox's), width <= OVERLAY_MAX_WIDTH."""
    base = site_dir / "base.jpg"
    if base.exists():
        with Image.open(base) as im:
            bw, bh = im.size
    else:
        w, s, e, n = bbox
        bw, bh = 2048, max(1, round(2048 * (n - s) / (e - w)))
    width = min(bw, OVERLAY_MAX_WIDTH)
    return width, max(1, round(width * bh / bw))


def save_png(rgba: np.ndarray, size: tuple[int, int], path: Path) -> Path:
    Image.fromarray(rgba, "RGBA").resize(size, Image.Resampling.NEAREST).save(path, optimize=True)
    return path


def value_encoding(values: np.ndarray) -> tuple[float, float]:
    """(offset, scale) so every finite value fits pixels 1..65535 (0 = no data)."""
    finite = values[np.isfinite(values)]
    limit = float(np.abs(finite).max()) if finite.size else 1.0
    limit = limit or 1.0
    return -limit, 2 * limit / 65534


def save_values_png(values: np.ndarray, size: tuple[int, int], offset: float, scale: float, path: Path) -> Path:
    """16-bit value grid for the identify tool: value = offset + scale * pixel, 0 = no data."""
    code = np.round((values - offset) / scale)
    code = np.where(np.isfinite(code), np.clip(code, 1, 65535), 0).astype(np.uint16)
    Image.fromarray(code).resize(size, Image.Resampling.NEAREST).save(path, optimize=True)
    return path


def _write_json(doc: Mapping, path: Path) -> Path:
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def round_sig(x: float) -> float:
    return float(f"{x:.4g}")


# --------------------------------------------------------------------------- per variable


@dataclass(frozen=True)
class Grid:
    times: pd.DatetimeIndex  # month starts
    monthly: np.ndarray  # (M, ny, nx) catalog units
    lat: np.ndarray
    lon: np.ndarray


def load_monthly_grid(bundle_dir: Path, var: Variable) -> Grid | None:
    units = appeears.load_layer_units(bundle_dir, var)  # flags masked, QC-filtered
    if units is None:
        return None
    min_frac = appeears.SNOW_MIN_VALID_FRACTION if var.band == appeears.SNOW_BAND else 0.0
    times, monthly = appeears.monthly_grid(units, min_valid_fraction=min_frac)
    return Grid(times, monthly, np.asarray(units["lat"].values), np.asarray(units["lon"].values))


def write_variable_maps(
    var: Variable, grid: Grid, site_dir: Path, bbox: Sequence[float],
    start: int = START_YEAR, end: int = END_YEAR,
) -> list[Path]:
    years = list(range(start, end + 1))
    sel = (grid.times.year >= start) & (grid.times.year <= end)
    times, cube = grid.times[sel], grid.monthly[sel]
    anomalies = deseasonalize(times, cube)
    annual = annual_means(times, anomalies, years)
    annual = np.stack([crop_to_bbox(a, grid.lat, grid.lon, bbox) for a in annual])
    slope, pval = sen_mk_grid(years, annual)
    style = style_for(var)
    size = overlay_size(site_dir, bbox)
    written: list[Path] = []

    vmax = symmetric_limit(slope)
    significant = np.isfinite(pval) & (pval < SIG_LEVEL)
    alpha = np.where(significant, ALPHA_SIGNIFICANT, ALPHA_FADED).astype(np.uint8)
    written.append(save_png(colorize(slope, vmax, style.colormap, alpha), size, site_dir / f"trend_{var.id}.png"))
    t_off, t_scale = value_encoding(slope)
    written.append(save_values_png(slope, size, t_off, t_scale, site_dir / f"trend_{var.id}_values.png"))
    sig_code = np.where(np.isfinite(pval), np.where(significant, 2, 1), 0).astype(np.uint8)
    Image.fromarray(sig_code).resize(size, Image.Resampling.NEAREST).save(site_dir / f"trend_{var.id}_significant.png")
    finite = np.isfinite(slope)
    written.append(_write_json({
        "var": var.id,
        "label": var.label,
        "kind": "trend",
        "unit": f"{var.units} per decade",
        "vmin": -round_sig(vmax),
        "vmax": round_sig(vmax),
        "colormap": style.colormap,
        "stops": legend_stops(style.colormap),
        "legend": {
            "more": style.more,
            "less": style.less,
            "faded": "Faded = could be chance at this pixel",
            "transparent": "Transparent = not enough data",
        },
        "alpha": {"significant": ALPHA_SIGNIFICANT, "faded": ALPHA_FADED},
        "years": [start, end],
        "pixels": int(finite.sum()),
        "share_significant": round_sig(float(significant[finite].mean())) if finite.any() else None,
        "share_up": round_sig(float((slope[finite] > 0).mean())) if finite.any() else None,
        "method": "Per pixel: Sen slope and Mann-Kendall S on annual means of deseasonalized monthly anomalies.",
        "value_file": f"trend_{var.id}_values.png",
        "value_offset": t_off,
        "value_scale": t_scale,
        "significance_file": f"trend_{var.id}_significant.png",  # 0 no data, 1 not significant, 2 significant
        "source": var.dataset,
    }, site_dir / f"trend_{var.id}.json"))

    ymax = symmetric_limit(annual)
    y_off, y_scale = value_encoding(annual)
    have = []
    for k, y in enumerate(years):
        if not np.isfinite(annual[k]).any():
            continue
        have.append(y)
        written.append(save_png(colorize(annual[k], ymax, style.colormap, ALPHA_YEAR), size, site_dir / f"year_{var.id}_{y}.png"))
        written.append(save_values_png(annual[k], size, y_off, y_scale, site_dir / f"value_{var.id}_{y}.png"))
    written.append(_write_json({
        "var": var.id,
        "label": var.label,
        "kind": "anomaly",
        "unit": var.units,
        "vmin": -round_sig(ymax),
        "vmax": round_sig(ymax),
        "colormap": style.colormap,
        "stops": legend_stops(style.colormap),
        "legend": {
            "more": f"{style.more} than usual",
            "less": f"{style.less} than usual",
            "transparent": "Transparent = not enough data that year",
        },
        "baseline": f"{start}-{end} average for each calendar month",
        "years": have,
        "file_pattern": f"year_{var.id}_{{YYYY}}.png",
        "value_pattern": f"value_{var.id}_{{YYYY}}.png",
        "value_offset": y_off,
        "value_scale": y_scale,
        "source": var.dataset,
    }, site_dir / f"year_{var.id}.json"))
    logger.info("%s: trend + %d yearly maps (scale ±%.3g, ±%.3g)", var.id, len(have), vmax, ymax)
    return written


def write_water_maps(
    bundle_dir: Path, site_dir: Path, bbox: Sequence[float],
    start: int = START_YEAR, end: int = END_YEAR,
) -> list[Path]:
    masks, lat, lon = water.annual_water_masks(bundle_dir, start, end)
    area = crop_to_bbox(water.pixel_area_km2(lat, lon), lat, lon, bbox)
    size = overlay_size(site_dir, bbox)
    written: list[Path] = []
    areas: dict[str, float] = {}
    for year, mask in masks.items():
        m = crop_to_bbox(mask, lat, lon, bbox)
        rgba = np.zeros(m.shape + (4,), dtype=np.uint8)
        rgba[m] = WATER_RGBA
        written.append(save_png(rgba, size, site_dir / f"year_water_{year}.png"))
        areas[str(year)] = round(float(area[m].sum()), 1)
    written.append(_write_json({
        "var": "water_area",
        "label": "Open water",
        "kind": "mask",
        "color": matplotlib.colors.to_hex([c / 255 for c in WATER_RGBA[:3]]),
        "legend": {"water": "Blue = open water that year", "transparent": "Transparent = land or no clear view"},
        "area_km2": areas,
        "years": [int(y) for y in areas],
        "file_pattern": "year_water_{YYYY}.png",
        "method": f"MODIS MOD09A1 NDWI > {water.NDWI_WATER_THRESHOLD} in ≥ {water.WATER_FREQUENCY:.0%} of clear 8-day looks",
        "source": "MOD09A1.061",
    }, site_dir / "year_water.json"))
    logger.info("water: %d yearly masks", len(masks))
    return written


# --------------------------------------------------------------------------- site


def build_site_maps(
    site_id: str,
    cache_dir: Path = appeears.DEFAULT_CACHE_DIR,
    sites_dir: Path = SITES_DIR,
    catalog: Sequence[Variable] | None = None,
) -> list[Path]:
    """Every map we can build for a site from whatever bundles are downloaded."""
    cat = catalog if catalog is not None else load_catalog()
    site = next(s for s in appeears.load_sites() if s.id == site_id)
    site_dir = sites_dir / site_id
    site_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for var in appeears.appeears_variables(cat, site):
        grid = load_monthly_grid(cache_dir / site_id, var)
        if grid is None:
            logger.info("%s/%s: no NetCDF grid yet", site_id, var.id)
            continue
        written.extend(write_variable_maps(var, grid, site_dir, site.bbox))
    water_dir = appeears.water_bundle_dir(site_id, cache_dir)
    if water.bundle_paths(water_dir):
        written.extend(write_water_maps(water_dir, site_dir, site.bbox))
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.assets.maps")
    parser.add_argument("site_ids", nargs="+")
    parser.add_argument("--cache-dir", type=Path, default=appeears.DEFAULT_CACHE_DIR)
    parser.add_argument("--sites-dir", type=Path, default=SITES_DIR)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for site_id in args.site_ids:
        paths = build_site_maps(site_id, args.cache_dir, args.sites_dir)
        logger.info("%s: wrote %d files", site_id, len(paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
