"""`sites/<id>/layers.json`: inventory of the map layers a site really has on disk.

Each layer says where it comes from (NASA product + link), what its colours mean, which
dates it covers and whether it went through the statistics (`analysed`) or is only a
picture (`visual_only`). Nothing is listed unless its file exists; a trend or yearly map
without its JSON sidecar is skipped, because without the sidecar we cannot write a legend.

Usage (from backend/, venv active):
    python -m app.layers lake_mead
    python -m app.layers --all
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from app.assets.build import BASE_IMAGERY
from app.sites import load_sites

logger = logging.getLogger(__name__)

SITES_DIR = Path(__file__).resolve().parents[2] / "sites"
LAYERS_VERSION = 1

GIBS = {"name": "NASA GIBS (Global Imagery Browse Services)", "url": "https://nasa-gibs.github.io/gibs-api-docs/"}
NASADEM = {"name": "NASADEM elevation (NASA JPL / LP DAAC)", "url": "https://lpdaac.usgs.gov/products/nasadem_hgtv001/"}
HLS = {
    "name": "NASA Harmonized Landsat Sentinel-2 (HLS) 30 m, via GIBS",
    "url": "https://www.earthdata.nasa.gov/data/projects/hls",
}
MODIS_TRUE_COLOR = {
    "name": "MODIS Terra corrected reflectance true colour, via GIBS",
    "url": "https://nasa-gibs.github.io/gibs-api-docs/",
}
DATASETS: Mapping[str, Mapping[str, str]] = {
    "MOD13A3.061": {
        "name": "MODIS Terra vegetation index NDVI (MOD13A3 v061), via AppEEARS",
        "url": "https://lpdaac.usgs.gov/products/mod13a3v061/",
    },
    "MOD11A2.061": {
        "name": "MODIS Terra land surface temperature (MOD11A2 v061), via AppEEARS",
        "url": "https://lpdaac.usgs.gov/products/mod11a2v061/",
    },
    "MOD16A2GF.061": {
        "name": "MODIS Terra evapotranspiration (MOD16A2GF v061), via AppEEARS",
        "url": "https://lpdaac.usgs.gov/products/mod16a2gfv061/",
    },
    "MOD10A1.061": {
        "name": "MODIS Terra snow cover (MOD10A1 v061), via AppEEARS",
        "url": "https://nsidc.org/data/mod10a1/versions/61",
    },
    "MOD09A1.061": {
        "name": "MODIS Terra surface reflectance (MOD09A1 v061), via AppEEARS",
        "url": "https://lpdaac.usgs.gov/products/mod09a1v061/",
    },
}
_TREND_JSON_RE = re.compile(r"^trend_(?P<var>.+)\.json$")
_YEAR_JSON_RE = re.compile(r"^year_(?P<var>[^\d].*)\.json$")


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("cannot read %s: %s", path, exc)
        return None


def _dataset_source(dataset: str | None) -> dict:
    if dataset and dataset in DATASETS:
        return dict(DATASETS[dataset])
    return {"name": dataset or "unknown", "url": None}


def _legend(meta: Mapping) -> dict:
    legend = {
        "unit": meta.get("unit"),
        "labels": dict(meta.get("legend") or {}),
    }
    if "stops" in meta:
        legend["stops"] = list(meta["stops"])
    if "vmin" in meta and "vmax" in meta:
        legend["range"] = [meta["vmin"], meta["vmax"]]
    if "color" in meta:
        legend["color"] = meta["color"]
    return legend


def _base_layers(site_id: str, site_dir: Path, names: set[str]) -> list[dict]:
    layers: list[dict] = []
    if "base.jpg" in names:
        imagery = BASE_IMAGERY.get(site_id)
        is_hls = imagery is not None and imagery.layer.startswith("HLS")
        layers.append({
            "id": "base",
            "kind": "image",
            "title": "Satellite picture",
            "file": "base.jpg",
            "status": "visual_only",
            "source": dict(HLS if is_hls else MODIS_TRUE_COLOR),
            "dates": [imagery.date] if imagery else [],
        })
    if "base_hq.jpg" in names:
        meta = _read_json(site_dir / "base_hq.json") or {}
        dates = sorted({scene[0] for scene in meta.get("scenes", [])})
        layers.append({
            "id": "base_hq",
            "kind": "image",
            "title": "Cloud-free satellite picture (30 m)",
            "file": "base_hq.jpg",
            "status": "visual_only",
            "source": dict(HLS),
            "dates": dates,
            "method": meta.get("method"),
        })
    return layers


def _relief_layers(site_dir: Path, names: set[str]) -> list[dict]:
    meta = _read_json(site_dir / "heightmap.json") if "heightmap.json" in names else None
    range_m = [meta["min_m"], meta["max_m"]] if meta and "min_m" in meta else None
    layers: list[dict] = []
    if "heightmap_rgb.png" in names:
        layers.append({
            "id": "relief",
            "kind": "heightmap",
            "title": "Terrain height",
            "file": "heightmap_rgb.png",
            "encoding": "terrain-rgb",  # height_m = -10000 + (R*65536 + G*256 + B) * 0.1
            "range_m": range_m,
            "status": "visual_only",
            "source": dict(NASADEM),
        })
    if "hillshade.png" in names:
        layers.append({
            "id": "hillshade",
            "kind": "shading",
            "title": "Relief shading",
            "file": "hillshade.png",
            "status": "visual_only",
            "source": dict(NASADEM),
        })
    return layers


def _before_after(site_dir: Path, names: set[str]) -> list[dict]:
    if not {"before.jpg", "after.jpg", "before_after.json"} <= names:
        return []
    meta = _read_json(site_dir / "before_after.json")
    if meta is None:
        return []
    before, after = meta.get("before", {}), meta.get("after", {})
    return [{
        "id": "before_after",
        "kind": "before_after",
        "title": f"Then and now ({before.get('year')} vs {after.get('year')})",
        "status": "visual_only",
        "source": dict(MODIS_TRUE_COLOR),
        "season": meta.get("season"),
        "note": "Two pictures of the same season, not a measured trend.",
        "before": {"file": "before.jpg", "year": before.get("year"), "dates": list(before.get("dates", []))},
        "after": {"file": "after.jpg", "year": after.get("year"), "dates": list(after.get("dates", []))},
    }]


def _detail(site_dir: Path) -> list[dict]:
    """High-detail crop for the drone view (detail/), listed only when complete."""
    d = site_dir / "detail"
    if not all((d / f).is_file() for f in ("detail.json", "heightmap_rgb.png", "base.jpg")):
        return []
    meta = _read_json(d / "detail.json")
    if meta is None:
        return []
    layer = {
        "id": "detail",
        "kind": "detail",
        "title": "Close-up: real ground and aerial photo",
        "status": "visual_only",
        "bbox": meta.get("bbox"),
        "files": {
            "heightmap_rgb": "detail/heightmap_rgb.png",
            "base": "detail/base.jpg",
            **({"hillshade": "detail/hillshade.png"} if (d / "hillshade.png").is_file() else {}),
        },
        "encoding": "terrain-rgb",
        "resolution_m": meta.get("resolution_m"),
        "height_range_m": meta.get("height_range_m"),
        "water_level_m_by_year": meta.get("water_level_m_by_year"),
        "drawable_years": meta.get("drawable_years"),
        "photos_by_year": meta.get("photos_by_year"),
        "photo_note": meta.get("photo_note"),
        "lidar_water_surface_m": meta.get("lidar_water_surface_m"),
        "note": meta.get("note"),
        "sources": meta.get("sources", []),
    }
    return [layer]


def _analysed_layers(site_dir: Path, names: set[str]) -> list[dict]:
    layers: list[dict] = []
    for name in sorted(names):
        if m := _TREND_JSON_RE.match(name):
            var = m["var"]
            if f"trend_{var}.png" not in names:
                continue
            meta = _read_json(site_dir / name)
            if meta is None:
                continue
            layers.append({
                "id": f"trend_{var}",
                "kind": "trend",
                "var": var,
                "title": f"{meta.get('label', var)}: trend",
                "file": f"trend_{var}.png",
                "status": "analysed",
                "years": list(meta.get("years", [])),
                "legend": _legend(meta),
                "method": meta.get("method"),
                "source": _dataset_source(meta.get("source")),
            })
        elif m := _YEAR_JSON_RE.match(name):
            var = m["var"]
            meta = _read_json(site_dir / name)
            if meta is None or "file_pattern" not in meta:
                continue
            pattern = meta["file_pattern"]
            years = [y for y in meta.get("years", []) if pattern.replace("{YYYY}", str(y)) in names]
            if not years:
                continue
            layer = {
                "id": f"year_{var}",
                "kind": "yearly",
                "var": var,
                "title": f"{meta.get('label', var)}: year by year",
                "file_pattern": pattern,
                "status": "analysed",
                "years": years,
                "legend": _legend(meta),
                "method": meta.get("method"),
                "source": _dataset_source(meta.get("source")),
            }
            if "baseline" in meta:
                layer["baseline"] = meta["baseline"]
            if "area_km2" in meta:
                layer["area_km2"] = {y: v for y, v in meta["area_km2"].items() if int(y) in years}
            layers.append(layer)
    return layers


def _layer_years(layer: dict) -> dict:
    """How one layer behaves on the shared timeline."""
    kind = layer["kind"]
    if kind == "yearly":
        return {"mode": "yearly", "years": list(layer["years"])}
    if kind == "trend":
        return {"mode": "span", "years": list(layer.get("years", []))}
    if kind == "before_after":
        return {"mode": "pair", "years": [layer["before"]["year"], layer["after"]["year"]]}
    if kind == "detail":
        photos = layer.get("photos_by_year") or {}
        out = {"mode": "static"}
        if photos:
            out = {
                "mode": "yearly",
                "years": sorted(int(y) for y in photos),
                "new_photo_years": sorted(int(y) for y, p in photos.items() if "same_as" not in p),
            }
        if layer.get("water_level_m_by_year"):
            out["water_years"] = list(layer.get("drawable_years") or [])
        return out
    return {"mode": "static"}


def build_timeline(layers: list[dict], site_dir: Path) -> dict:
    """One shared timeline for the site: the study years, which layer has what each year,
    and which record (site.json variable) has a yearly value each year."""
    site_json = _read_json(site_dir / "site.json") if (site_dir / "site.json").is_file() else None
    span = (site_json or {}).get("years") or []
    years = list(range(span[0], span[1] + 1)) if len(span) == 2 else []
    records = {
        v["id"]: [p["year"] for p in v.get("series", []) if p.get("value") is not None]
        for v in (site_json or {}).get("variables", [])
    }
    maps_for = {layer["var"]: layer["id"] for layer in layers if layer["kind"] == "yearly" and "var" in layer}
    return {
        "years": years,
        "layers": {layer["id"]: _layer_years(layer) for layer in layers},
        "records": records,
        # record id -> its own yearly map layer, when one exists; otherwise the map shows a picture.
        "record_map": {rid: maps_for.get(rid) for rid in records},
    }


def build_layers(site_id: str, site_dir: Path) -> dict:
    """The layers.json document for one site (no file written)."""
    names = {p.name for p in site_dir.iterdir() if p.is_file()} if site_dir.is_dir() else set()
    layers = [
        *_base_layers(site_id, site_dir, names),
        *_relief_layers(site_dir, names),
        *_before_after(site_dir, names),
        *_detail(site_dir),
        *_analysed_layers(site_dir, names),
    ]
    return {
        "site": site_id,
        "version": LAYERS_VERSION,
        "layers": layers,
        "timeline": build_timeline(layers, site_dir),
    }


def write_layers(site_id: str, site_dir: Path) -> Path:
    doc = build_layers(site_id, site_dir)
    path = site_dir / "layers.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    logger.info("%s: %d layers -> %s", site_id, len(doc["layers"]), path)
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.layers", description="Write sites/<id>/layers.json.")
    parser.add_argument("site_ids", nargs="*")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.all == bool(args.site_ids):
        parser.error("give site ids or --all (not both)")
    ids = [s.id for s in load_sites().sites] if args.all else args.site_ids
    for site_id in ids:
        write_layers(site_id, SITES_DIR / site_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
