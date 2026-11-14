# Earth Trend Detective

**Is it the climate, or is it us?**

Pick a place on Earth and find out what is changing there, whether the change is real, and how much of it the
climate does not explain. Built on NASA Earth observation data, explained in plain language.

NASA Space Apps Challenge 2026 · Challenge: [Be An Earth System Trend Detective!](https://www.spaceappschallenge.org/2026/challenges/earth-system-trend-detective/)
· Licence: Apache-2.0

## What you can do with it

- **Solved cases** (`/story/<id>`): Lake Mead, the Aletsch Glacier and the Doñana wetlands, 2003–2024, over a 3D
  relief built from NASADEM. Each case walks through three questions: *What is changing? Is it real? Is it the
  climate?* Yearly maps, a drone view over real aerial photographs, and every layer names its source.
- **Ask the detective** (`/investigate`): pick a point and ask a question. A language model plans the checks
  from a fixed menu of NASA data; the code runs them and the answer comes first, with every figure checked.
- **Explore** (`/explore`): click anywhere for a quick trend sweep of NASA POWER climate records at that point.

## How it works

1. **Sweep.** Every NASA variable that applies to the place is fetched as a monthly series and deseasonalised.
2. **Is it real?** Mann–Kendall trend test with the Hamed–Rao autocorrelation correction, Sen's slope with its
   interval, and Benjamini–Hochberg false-discovery control across all the variables tested. Verdicts: *real*,
   *likely*, *can't tell yet*.
3. **Is it the climate?** Each impact variable is modelled on its climate drivers; the share of its trend that
   the drivers do not explain is reported as a range across climate models (Lake Mead: 54–84 %). It is a clue,
   not an attribution.
4. **Explain.** A language model writes plain English from the computed numbers only. A validator checks every
   figure; if one does not match, the text is replaced by a fixed template.

## Start here

Requirements: Python ≥ 3.12 with [uv](https://docs.astral.sh/uv/), Node.js ≥ 20.

```bash
cp .env.example .env           # repo root; fill in the tokens (see below)

# 1. API (FastAPI) on :8765
cd backend
uv sync
uv run uvicorn app.main:app --port 8765

# 2. Web app (Next.js) on :5180
cd ../frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8765 npm run build
npm run start                  # or: npm run dev
```

Open http://localhost:5180. The three solved cases are precomputed in `sites/` and work without the API; the
narrator, the investigator and explore need it.

Environment (`.env` at the repo root, never committed):

| Variable | Used for |
| --- | --- |
| `NASA_TOKEN` | Earthdata Login token: GRACE (PO.DAAC) and GLDAS (GES DISC) |
| `APPEEARS_TOKEN` | AppEEARS session token: MODIS subsets for the pipeline |
| `OPENROUTER_API_KEY` or `LLM_API_KEY` | The language model (narrator, planner, question routing) |
| `CORS_ORIGINS` | Comma-separated web origins allowed to call the API (defaults cover localhost) |

Tests: `cd backend && uv run pytest -q` · `cd frontend && npm run typecheck`.

## Repository layout

```
backend/   FastAPI API, data extractors, statistics, narrator and investigator
frontend/  Next.js app: cover, solved cases (3D), investigator, explore
sites/     Precomputed case data: site.json, layers.json, relief, imagery, yearly layers
docs/      Team notes (Spanish) and submission copy (English)
```

## NASA data

| Resource | Role |
| --- | --- |
| [GRACE/GRACE-FO JPL mascons RL06.3](https://podaac.jpl.nasa.gov/dataset/TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4) (PO.DAAC) | Total water storage: the main record of the water cases |
| [NASA POWER](https://power.larc.nasa.gov/) (MERRA-2, IMERG, CERES) | Temperature, rain, snow and sunshine: climate drivers and the explore sweep |
| [GLDAS Noah 0.25° v2.1](https://disc.gsfc.nasa.gov/datasets/GLDAS_NOAH025_M_2.1/summary) (GES DISC) | Soil moisture and runoff |
| [MODIS MOD11A2](https://doi.org/10.5067/MODIS/MOD11A2.061) via [AppEEARS](https://appeears.earthdatacloud.nasa.gov/) | Daytime ground temperature, per-pixel trend map (Lake Mead) |
| MODIS MOD11C3 and MOD13A3 via [GIBS](https://nasa-gibs.github.io/gibs-api-docs/) | Yearly maps of ground temperature and vegetation (NDVI) |
| MODIS MCD12Q1 via GIBS | Land cover: what kind of place a clicked point is |
| MODIS Terra corrected reflectance via GIBS | Then-and-now pictures (pictures, not measurements) |
| [NASADEM](https://lpdaac.usgs.gov/products/nasadem_hgtv001/) (LP DAAC) | Elevation for the 3D relief |
| HLS (Harmonized Landsat Sentinel-2, LP DAAC) | Cloud-free 30 m base imagery of the cases |

Not NASA, labelled on screen: U.S. Bureau of Reclamation Lake Mead levels (validation and the drone view's
water plane), USGS 3DEP lidar + USDA NAIP, swisstopo swissALTI3D + SWISSIMAGE, IGN Spain MDT05 + PNOA (close-up
relief and aerial photos for the drone view), OpenStreetMap / OpenFreeMap (map labels).

## Use of AI

See [`AI.md`](AI.md). In short: Claude (Anthropic) was used as a coding assistant, and a language model inside the
product plans investigations and writes explanations, never computing or deciding anything, with every figure
checked against the data.
