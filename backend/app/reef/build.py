"""One reproducible build of the Great Barrier Reef case: `python -m app.reef.build`.

Usage: python -m app.reef.build [--offline] [--refresh-base] [--cache-dir DIR]

Nine steps, strictly sequential (ERDDAP answers 408 to parallel requests):

1. base.jpg from NASA GIBS (MODIS Aqua true colour); kept when present unless --refresh-base
2. seabed relief from GEBCO_2020 (not NASA)
3. NASA JPL MUR sea temperature, one year per request, 2003-2024
4. SST trend and yearly maps, and the box-mean monthly series
5. chlorophyll (log10) at the Burdekin pixel; the cell actually used is logged
6. degree heating weeks at the five reef points, every year (NOAA Coral Reef Watch, not NASA)
7. heat-stress maps for the hot years
8. site.json
9. layers.json

Every network call goes through `ReefFetchers`, so tests inject fakes. Each result is kept in
`cache_dir` under a readable name (MUR `.nc` per year from `sst`, `gebco_*.npy`,
`chl_burdekin.csv`, `dhw_<point>_*.json`, `dhw_day_*.nc`). A failed request is never cached.
`--offline` reads that cache only: before writing anything it checks the cache and raises
`FileNotFoundError` naming every missing piece. Heat stress is heat stress, not bleaching.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import xarray as xr

from app import layers, site_export
from app.assets import gibs
from app.assets.build import BASE_IMAGERY
from app.catalog import Variable, load_catalog
from app.extractors import erddap
from app.reef import dhw, dhw_maps, relief, sst
from app.reef import export as reef_export
from app.reef.points import CHLOROPHYLL_POINT, DEFAULT_CACHE_DIR, REEF_POINTS, SITE_ID, ReefPoint
from app.sites import Site, load_sites

logger = logging.getLogger(__name__)

SITES_DIR = site_export.SITES_DIR
STEPS = 9
BASE_WIDTH = 2048


@dataclass(frozen=True)
class ReefFetchers:
    """The six network callables of the build (fakes in tests).

    - base(bbox, date, out_path) -> Path: true-colour JPEG written to out_path
    - mur_year(dataset, variable, bbox, start, end, stride) -> xr.DataArray (as `erddap.fetch_grid`)
    - chlorophyll_point(dataset, variable, lat, lon, start, end) -> (series, cell) (as `erddap.fetch_point_monthly`)
    - dhw_point_year(point, years) -> {year: dhw.YearlyMax} (as `dhw.yearly_max`; failed years absent)
    - gebco(bbox) -> np.ndarray of metres, rows north -> south (as `relief.fetch_gebco`)
    - dhw_day(dataset, variable, bbox, day, stride) -> xr.DataArray (as `erddap.fetch_day_grid`)
    """

    base: Callable[..., Path]
    mur_year: Callable[..., xr.DataArray]
    chlorophyll_point: Callable[..., tuple[pd.Series, tuple[float, float]]]
    dhw_point_year: Callable[[ReefPoint, Sequence[int]], dict[int, dhw.YearlyMax]]
    gebco: Callable[[Sequence[float]], np.ndarray]
    dhw_day: Callable[..., xr.DataArray]


def network_fetchers(client: httpx.Client, cache_dir: Path) -> ReefFetchers:
    """The real fetchers: ERDDAP through `client` (its CSV cache in `cache_dir`), GIBS for the base."""
    imagery = BASE_IMAGERY[SITE_ID]

    def base(bbox: Sequence[float], date: str, out_path: Path) -> Path:
        return gibs.fetch_base_image(bbox, date, out_path, width=BASE_WIDTH, layer=imagery.layer)

    def mur_year(dataset, variable, bbox, start, end, stride):
        return erddap.fetch_grid(dataset, variable, bbox, start, end, stride, client, cache_dir)

    def chlorophyll_point(dataset, variable, lat, lon, start, end):
        return erddap.fetch_point_monthly(dataset, variable, lat, lon, start, end, client, cache_dir)

    def dhw_point_year(point: ReefPoint, years: Sequence[int]) -> dict[int, dhw.YearlyMax]:
        return dhw.yearly_max(point, years, cache_dir, client)

    def gebco(bbox: Sequence[float]) -> np.ndarray:
        return relief.fetch_gebco(bbox, cache_dir, client)

    def dhw_day(dataset, variable, bbox, day, stride):
        return erddap.fetch_day_grid(dataset, variable, bbox, day, stride, client, cache_dir)

    return ReefFetchers(base, mur_year, chlorophyll_point, dhw_point_year, gebco, dhw_day)


def _offline_fetchers() -> ReefFetchers:
    def refuse(*_args, **_kwargs):
        raise FileNotFoundError("offline: this piece is not in the reef cache")

    return ReefFetchers(*(refuse,) * 6)


# --------------------------------------------------------------------------- cache files


def _box(bbox: Sequence[float]) -> str:
    return "_".join(str(float(x)) for x in bbox)


def _gebco_file(cache_dir: Path, bbox: Sequence[float]) -> Path:
    return cache_dir / f"gebco_{_box(bbox)}_s{relief.GEBCO_STRIDE}.npy"


def _chl_file(cache_dir: Path) -> Path:
    return cache_dir / f"chl_{CHLOROPHYLL_POINT}.csv"


def _dhw_file(cache_dir: Path, point: ReefPoint, start: int, end: int) -> Path:
    return cache_dir / f"dhw_{point.id}_{start}_{end}.json"


def _dhw_day_file(cache_dir: Path, bbox: Sequence[float], day: dt.date) -> Path:
    return cache_dir / f"dhw_day_{day.isoformat()}_{_box(bbox)}.nc"


def _atomic(path: Path, write: Callable[[Path], None]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=path.suffix)
    os.close(fd)
    try:
        write(Path(tmp))
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def missing_from_cache(site: Site, start: int, end: int, cache_dir: Path, site_dir: Path) -> list[str]:
    """What an offline build would need and the cache does not hold (empty = ready)."""
    missing = []
    if not (site_dir / "base.jpg").is_file():
        missing.append(f"base.jpg in {site_dir}")
    if not _gebco_file(cache_dir, site.bbox).is_file():
        missing.append("GEBCO relief grid")
    missing += [
        f"MUR {year}" for year in range(start, end + 1) if not sst._cache_file(year, site.bbox, cache_dir).is_file()
    ]
    if not _chl_file(cache_dir).is_file():
        missing.append(f"chlorophyll at {CHLOROPHYLL_POINT}")
    missing += [f"DHW at {p.id}" for p in REEF_POINTS if not _dhw_file(cache_dir, p, start, end).is_file()]
    return missing


# --------------------------------------------------------------------------- steps


def _relief(site: Site, cache_dir: Path, site_dir: Path, fetchers: ReefFetchers, offline: bool) -> list[Path]:
    path = _gebco_file(cache_dir, site.bbox)
    if path.is_file():
        elev = np.load(path)
    elif offline:
        raise FileNotFoundError(f"GEBCO: no cached grid at {path} (offline)")
    else:
        elev = np.asarray(fetchers.gebco(tuple(site.bbox)), dtype=np.float64)
        _atomic(path, lambda tmp: np.save(tmp, elev))
    relief.write_relief(elev, site.bbox, site_dir)
    return [site_dir / n for n in ("heightmap.png", "heightmap_rgb.png", "hillshade.png", "heightmap.json")]


def _read_chl(path: Path) -> tuple[pd.Series, tuple[float, float], list[int]]:
    with path.open(encoding="utf-8") as fh:
        head = json.loads(fh.readline().removeprefix("#"))
        frame = pd.read_csv(fh, parse_dates=["time"], index_col="time")
    series = frame["value"].astype(float)
    series.index = pd.DatetimeIndex(series.index)
    return series, (float(head["cell"][0]), float(head["cell"][1])), [int(y) for y in head["missing_years"]]


def _write_chl(path: Path, raw: pd.Series, cell: tuple[float, float], missing: Sequence[int]) -> None:
    def write(tmp: Path) -> None:
        with tmp.open("w", encoding="utf-8", newline="") as fh:
            fh.write("#" + json.dumps({"cell": list(cell), "missing_years": list(missing)}) + "\n")
            raw.rename("value").rename_axis("time").to_csv(fh)

    _atomic(path, write)


def _chlorophyll(
    var: Variable, start: int, end: int, cache_dir: Path, fetchers: ReefFetchers, offline: bool
) -> tuple[pd.Series, list[int]]:
    """log10 chlorophyll at the Burdekin point and the years whose fetch failed.

    The cache is refreshed online when the cached run had failed years.
    """
    point = next(p for p in REEF_POINTS if p.id == CHLOROPHYLL_POINT)
    path = _chl_file(cache_dir)
    cached = _read_chl(path) if path.is_file() else None
    if cached is not None and (offline or not cached[2]):
        raw, cell, missing = cached
    elif offline:
        raise FileNotFoundError(f"chlorophyll: no cached series at {path} (offline)")
    else:
        raw, cell = fetchers.chlorophyll_point(var.dataset, var.band, point.lat, point.lon, start, end)
        missing = [int(y) for y in raw.attrs.get("missing_years", [])]
        _write_chl(path, raw, cell, missing)
    logger.info("chlorophyll at %s (%.2f, %.2f): cell used %s", point.id, point.lat, point.lon, cell)
    if missing:
        logger.warning("chlorophyll: years %s failed and are gaps", missing)
    values = raw * var.scale + var.offset
    chl = np.log10(values.where(values > 0)).astype(float)
    chl = chl[(chl.index.year >= start) & (chl.index.year <= end)].rename(reef_export.CHLOROPHYLL_ID)
    return chl, missing


def _point_heat(
    point: ReefPoint, start: int, end: int, cache_dir: Path, fetchers: ReefFetchers, offline: bool
) -> dict[int, dhw.YearlyMax]:
    """Yearly DHW peaks at one point. Failed years are absent (never cached as values); the
    cache is refreshed online while any year is absent, and read as is offline."""
    years = list(range(start, end + 1))
    path = _dhw_file(cache_dir, point, start, end)
    if path.is_file():
        doc = json.loads(path.read_text(encoding="utf-8"))
        got = {int(y): dhw.YearlyMax(v["value"], v["date"]) for y, v in doc.items()}
        if offline or set(years) <= set(got):
            return got
    elif offline:
        raise FileNotFoundError(f"DHW at {point.id}: no cached record at {path} (offline)")
    got = {y: v for y, v in fetchers.dhw_point_year(point, years).items() if start <= y <= end}
    doc = {str(y): {"value": v.value, "date": v.date} for y, v in sorted(got.items())}
    _atomic(path, lambda tmp: tmp.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8"))
    absent = sorted(set(years) - set(got))
    if absent:
        logger.warning("DHW at %s: years %s failed and are listed as missing", point.id, absent)
    return got


def _day_fetch(fetchers: ReefFetchers, offline: bool) -> Callable[..., xr.DataArray]:
    """`erddap.fetch_day_grid`-shaped callable for `dhw_maps`, backed by the reef cache.

    A day not in the cache offline is an `ErddapError`, so it is listed in `missing_years`
    exactly as when its fetch failed online (failed days are never cached)."""

    def fetch(dataset, variable, bbox, day, stride, _client, cache_dir):
        path = _dhw_day_file(Path(cache_dir), bbox, day)
        if path.is_file():
            with xr.open_dataarray(path) as cached:
                return cached.load()
        if offline:
            raise erddap.ErddapError(f"offline: DHW day {day} is not in the cache")
        grid = fetchers.dhw_day(dataset, variable, bbox, day, stride)
        if day.year < dt.date.today().year:
            _atomic(path, lambda tmp: grid.drop_attrs().to_netcdf(tmp))
        return grid

    return fetch


@contextmanager
def _step(i: int, name: str) -> Iterator[None]:
    t0 = time.monotonic()
    yield
    logger.info("step %d/%d %s: %.1f s", i, STEPS, name, time.monotonic() - t0)


def build_reef(
    sites_dir: Path = SITES_DIR,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    offline: bool = False,
    refresh_base: bool = False,
    client: httpx.Client | None = None,
    fetchers: ReefFetchers | None = None,
) -> list[Path]:
    """Make the whole reef case in `sites_dir/great_barrier_reef/`; returns the files written."""
    if offline and refresh_base:
        raise ValueError("--refresh-base needs the network; it cannot run offline")
    registry = load_sites()
    site = registry.get(SITE_ID)
    start, end = registry.study_period
    site_dir = sites_dir / SITE_ID
    cache_dir = Path(cache_dir)
    if offline:
        missing = missing_from_cache(site, start, end, cache_dir, site_dir)
        if missing:
            raise FileNotFoundError("offline build: not in the cache: " + ", ".join(missing))
    own = None
    if fetchers is None:
        if offline:
            fetchers = _offline_fetchers()
        else:
            own = client is None
            client = client or erddap.new_client()
            fetchers = network_fetchers(client, cache_dir)
    try:
        return _run(site, start, end, site_dir, cache_dir, fetchers, offline, refresh_base)
    finally:
        if own and client is not None:
            client.close()


def _run(
    site: Site,
    start: int,
    end: int,
    site_dir: Path,
    cache_dir: Path,
    fetchers: ReefFetchers,
    offline: bool,
    refresh_base: bool,
) -> list[Path]:
    catalog = load_catalog()
    by_id = {v.id: v for v in catalog}
    written: list[Path] = []
    site_dir.mkdir(parents=True, exist_ok=True)

    with _step(1, "base image (NASA GIBS)"):
        base = site_dir / "base.jpg"
        if refresh_base or not base.is_file():
            imagery = BASE_IMAGERY[SITE_ID]
            written.append(fetchers.base(tuple(site.bbox), imagery.date, base))
        else:
            logger.info("base.jpg kept (pass --refresh-base to fetch it again)")
    with _step(2, "seabed relief (GEBCO)"):
        written += _relief(site, cache_dir, site_dir, fetchers, offline)
    with _step(3, f"MUR sea temperature {start}-{end}"):
        grid = sst.mur_grid(range(start, end + 1), site.bbox, cache_dir, fetch=fetchers.mur_year, offline=offline)
        if grid.missing_years:
            logger.warning("MUR: years %s failed and are gaps", list(grid.missing_years))
    with _step(4, "SST maps and box series"):
        written += sst.write_sst_maps(by_id[sst.SST_VAR_ID], grid, site_dir, site.bbox, start, end)
        sea = sst.box_mean_series(grid)
    with _step(5, f"chlorophyll at {CHLOROPHYLL_POINT}"):
        chl, chl_missing = _chlorophyll(by_id[reef_export.CHLOROPHYLL_ID], start, end, cache_dir, fetchers, offline)
    with _step(6, f"heat stress at {len(REEF_POINTS)} reefs x {end - start + 1} years"):
        yearly = {p.id: _point_heat(p, start, end, cache_dir, fetchers, offline) for p in REEF_POINTS}
        heat = dhw.heat_stress_summary(yearly, list(REEF_POINTS), start, end)
    with _step(7, "heat-stress maps"):
        written += dhw_maps.write_dhw_maps(
            heat, site.bbox, site_dir, cache_dir, None, offline=offline, fetch_day=_day_fetch(fetchers, offline)
        )
    with _step(8, "site.json"):
        series = reef_export.ReefSeries(
            sst=sea,
            chlorophyll_log10=chl,
            sst_missing_years=tuple(grid.missing_years),
            chlorophyll_missing_years=tuple(chl_missing),
        )
        doc = reef_export.build_reef_site_json(site, catalog, start, end, site_dir, series, heat)
        written.append(site_export.write_site_json(doc, site_dir))
    with _step(9, "layers.json"):
        written.append(layers.write_layers(site.id, site_dir))
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.reef.build", description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true", help="read the cache only; fail if a piece is missing")
    parser.add_argument("--refresh-base", action="store_true", help="fetch base.jpg again even if present")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    build_reef(offline=args.offline, refresh_base=args.refresh_base, cache_dir=args.cache_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
