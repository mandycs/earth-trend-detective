"""Pre-warm the slow `water_extent` cache for the demo places, without the language model.

    python scripts/prewarm.py                         # Aral and Lake Mead, into backend/data/cache
    python scripts/prewarm.py --cache-dir /path/to/backend/data/cache --timeout 900

For each place it builds the same box the detective builds for a picked point (`box_around`),
runs the same sea check as the `water_extent` tool (GEBCO lowest point), and if the tool would
measure there, calls the extractor for every completed OPERA year. Completed years land in
`<cache-dir>/water_extent/` under the extractor's own keys, so a later run of the tool reads them.
Files are only added (the extractor writes atomically); nothing is deleted here.
Each place runs under a time cap; a place over it is reported and left to finish in the background
thread until the script exits (years already done are kept).
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.detective.tools import data  # noqa: E402
from app.extractors import erddap  # noqa: E402
from app.extractors import water_extent as wx  # noqa: E402
from app.investigate.landcover import box_around  # noqa: E402

PLACES = {"aral": (45.0, 59.5), "lake_mead": (36.1, -114.7)}
DEFAULT_CACHE = Path(__file__).resolve().parents[1] / "data" / "cache"


def warm(name: str, lat: float, lon: float, cache_dir: Path) -> str:
    bbox = box_around(lat, lon)
    try:
        lowest = erddap.fetch_min_elevation(bbox)
    except Exception as exc:  # noqa: BLE001 - the tool refuses on an unknown sea check too
        return f"{name}: sea check failed ({type(exc).__name__}); the tool would refuse here, skipped"
    if lowest <= data.SEA_MAX_ELEVATION_M:
        return f"{name}: lowest point {lowest:.0f} m, the tool treats this box as sea; skipped"
    series = wx.fetch_yearly_water(bbox, wx.FIRST_YEAR, wx.last_complete_year(), cache_dir=cache_dir)
    years = [int(t.year) for t in series.index]
    attrs = series.attrs
    return (
        f"{name}: {len(years)} years kept {years}; dropped {attrs.get('dropped_years')}, "
        f"no scene {attrs.get('no_scene_years')}, failed {attrs.get('missing_years')}"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE, help="the backend/data/cache folder")
    ap.add_argument("--timeout", type=float, default=900.0, help="seconds per place")
    ap.add_argument("--only", choices=sorted(PLACES), action="append")
    args = ap.parse_args(argv)
    cache_dir = args.cache_dir / "water_extent"
    cache_dir.mkdir(parents=True, exist_ok=True)
    pool = ThreadPoolExecutor(max_workers=1)
    code = 0
    for name in args.only or list(PLACES):
        lat, lon = PLACES[name]
        t0 = time.monotonic()
        fut = pool.submit(warm, name, lat, lon, cache_dir)
        try:
            line = fut.result(timeout=args.timeout)
        except FutureTimeout:
            line, code = f"{name}: over the {args.timeout:.0f} s cap", 1
        except Exception as exc:  # noqa: BLE001 - report and go on to the next place
            line, code = f"{name}: failed ({type(exc).__name__}: {str(exc)[:120]})", 1
        print(f"{line}  [{time.monotonic() - t0:.1f} s]", flush=True)
    pool.shutdown(wait=False, cancel_futures=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
