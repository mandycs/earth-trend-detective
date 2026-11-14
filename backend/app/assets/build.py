"""Build story-mode image assets (heightmap + base texture) for every site.

Usage: python -m app.assets.build [site_id ...]

Base imagery choice per site (picked by cloud/no-data score over Jul-Aug 2024 scenes):
- lake_mead: MODIS Terra true colour (250 m) - the 0.9° box needs a single wide scene.
- aletsch, donana: HLS Landsat 30 m (NASA Harmonized Landsat Sentinel-2) - small boxes
  are a blur at 250 m.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from app.assets.dem import build_heightmap
from app.assets.gibs import DEFAULT_LAYER, fetch_base_image
from app.sites import load_sites

logger = logging.getLogger(__name__)

SITES_DIR = Path(__file__).resolve().parents[3] / "sites"
HLS_LANDSAT = "HLS_L30_Nadir_BRDF_Adjusted_Reflectance"


@dataclass(frozen=True)
class BaseImagery:
    layer: str
    date: str


BASE_IMAGERY: dict[str, BaseImagery] = {
    "lake_mead": BaseImagery(DEFAULT_LAYER, "2024-06-20"),
    "aletsch": BaseImagery(HLS_LANDSAT, "2024-08-31"),
    "donana": BaseImagery(HLS_LANDSAT, "2024-08-23"),
}


def build_site_assets(site_id: str, sites_dir: Path = SITES_DIR) -> None:
    site = load_sites().get(site_id)
    if site is None:
        raise KeyError(f"unknown site {site_id!r}")
    out = sites_dir / site_id
    imagery = BASE_IMAGERY.get(site_id, BaseImagery(DEFAULT_LAYER, "2024-07-15"))
    fetch_base_image(site.bbox, imagery.date, out / "base.jpg", layer=imagery.layer)
    hm = build_heightmap(site.bbox, out / "heightmap.png")
    meta = {"min_m": hm.min_m, "max_m": hm.max_m, "width": hm.width, "height": hm.height,
            "source": "NASADEM_HGT v001 (NASA JPL / LP DAAC)"}
    (out / "heightmap.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    logger.info("%s: heightmap %dx%d, %.0f-%.0f m", site_id, hm.width, hm.height, hm.min_m, hm.max_m)


def main(argv: list[str]) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    ids = argv or [s.id for s in load_sites().sites]
    for site_id in ids:
        build_site_assets(site_id)


if __name__ == "__main__":
    main(sys.argv[1:])
