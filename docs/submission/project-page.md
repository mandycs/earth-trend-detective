# Project page — submission copy (English)

> Paste-ready text for the NASA Space Apps 2026 Project tab, in the official form order (`rules.md` §4).
> Checked against the code and `sites/*/site.json` on 14 Nov 2026 (evening). Every figure below comes from
> `site.json`; re-check them if the pipeline is re-run.

## Slots to resolve before submitting

| Slot | Where | What to do |
|---|---|---|
| `[DEMO_URL]` | §3 | Public link to the 30-second video (YouTube unlisted is fine), or the deck at `<LIVE_URL>/deck.html`. |
| `[LIVE_URL]` / `[REPO_URL]` | §4 | Deployed app and the GitHub repository, made public at freeze. Test both in a private window. The deployed web app must be built with `NEXT_PUBLIC_API_URL` pointing at the public API, and the API must list the web origin in `CORS_ORIGINS`. |
| Team names | §6 | Team name and member names, as registered on the Space Apps site. |

---

## 1. Project Name

**Alibi — an Earth trend detective**

---

## 2. High-Level Project Summary

Alibi answers three questions about a place on Earth: what is changing here, is the change real, and how much of it does the climate not explain?

For each place, the tool takes the NASA records that apply there (GRACE water storage, MODIS land surface temperature and vegetation, GLDAS soil moisture, NASA POWER climate), removes the seasonal cycle and runs a Mann–Kendall trend test with Sen's slope, corrected for autocorrelation and for testing many variables at once. Each record gets a plain verdict: real, likely, or can't tell yet. Then it models each impact variable on its climate drivers and reports the share of the trend the climate leaves unexplained, as a range across climate models. That share is a clue, not an attribution.

Three solved cases (Lake Mead, the Aletsch Glacier, Doñana) are told over a 3D relief with yearly NASA maps. An investigator lets anyone pick a point and ask a question; a language model plans the checks from a fixed menu, the code runs them, and every figure in the answer is checked against the data.

*171 words.*

---

## 3. Link to Project Demo

`[DEMO_URL]`

Format: 30-second screen recording, English voice-over with burned-in English captions. Script: `video-30s.md`.

---

## 4. Link to Final Project

Live app: `[LIVE_URL]`
Source code (Apache-2.0): `[REPO_URL]`

---

## 5. Detailed Project Description

### What it does

Most climate tools show you a line. This one tells you what the line means, and what it does not mean.

**Solved cases.** Three places, 2003–2024, each a 3D block of real terrain (NASADEM) under a cloud-free satellite picture. Each case walks through the same three questions and the user scrubs a shared timeline. All three have yearly MODIS maps of ground temperature and vegetation from NASA GIBS (`sites/*/layers.json`); only Lake Mead also has the pipeline's own yearly and per-pixel trend maps; every map layer names its source and says when it has no data for a year.

- **Lake Mead (USA).** Total water stored is going down for real: −6.5 cm per decade (interval −9.6 to −3.6). Local rainfall shows no clear trend, while rain and snow upstream fall. Between 54% and 84% of the water loss is not explained by climate, depending on whether the upstream basin's climate is included.
- **Aletsch Glacier (Switzerland).** Air temperature rises 1.0 °C per decade and total water stored falls 6.9 cm per decade, both real. Here the tool deliberately gives no climate split: GRACE sees a region about 300 km wide dominated by snow and ice, and our climate model has no snow term, so a split would mislead. It says so on screen.
- **Doñana (Spain).** Total water stored is probably going down (−8.6 cm per decade, "likely", not "real"), topsoil moisture is falling for real, and rainfall shows no clear trend.

For a closer look, a **drone view** flies low over each case on higher-resolution relief and real aerial photographs, year by year; at Lake Mead the water surface sits at the level the U.S. Bureau of Reclamation measured that year.

**Ask the detective.** The user clicks any point and asks a question in plain English. NASA land cover tells the tool what kind of place it is; a language model picks 2–5 checks from a fixed menu (climate trends, water storage, soil moisture and runoff, land cover, then-and-now pictures); the code runs them and draws each result on the map. The screen leads with the answer, built by code from the data ("Total water stored is going down, for real." · "54–84%" · "A clue, not proof."), followed by a short checked paragraph and the evidence.

**Explore.** A quick click-anywhere sweep of the NASA POWER climate records at a point.

Every verdict is shown as icon plus words, never colour alone:

- **↑/↓ Real** — the trend survives the significance test and the multiple-testing correction.
- **Likely** — the trend is there but the evidence is not strong enough to call it.
- **? Can't tell yet** — with an estimate of how many more years of data would be needed.

### How we built it

**Pipeline** (`backend/app`), each stage testable on its own:

1. **Catalogue and gather.** A closed catalogue of variables stores dataset, band, units and where each applies, so a snow variable is never offered for a desert. Series come from GRACE (PO.DAAC), NASA POWER, GLDAS (GES DISC data rods) and MODIS (AppEEARS), in parallel.
2. **Sweep.** Monthly series become anomalies (seasonal cycle removed) and are tested with Mann–Kendall plus the Hamed–Rao autocorrelation correction, Sen's slope with its interval, and Benjamini–Hochberg control across all variables tested at once.
3. **Climate split.** A generalised RESTREND approach (Evans & Geerken 2004; Wessels et al. 2012): regress the impact variable on its climate drivers and trend-test what is left. We fit more than one climate model and report the range. A policy withholds the split where it would mislead (snow and glacier sites, model-only variables).
4. **Explain.** The narrator receives computed values as JSON and writes prose; a validator checks every number, direction and certainty word, and rejects causal claims, "proof" and statistics jargon. On failure, a fixed template is shown.

**Maps and relief.** Per-pixel Sen slope of MODIS daytime ground temperature at Lake Mead, faded where not significant. Yearly maps of ground temperature (MOD11C3) and vegetation (MOD13A3) decoded from NASA GIBS colour maps into value grids. Relief from NASADEM heights, cloud-free 30 m HLS base imagery, and close-up relief and aerial photos for the drone view.

**Frontend.** Two modes: a documentary mode that tells a case in three chapters, and an instrument mode (a case's free mode, the investigator and explore) with layers, Identify and the full evidence. Next.js 16, React 19, three.js with react-three-fiber for the relief and the drone view, MapLibre GL for the investigator and explore maps.

**Backend.** FastAPI: `/health`, `/variables`, `/sweep` (POWER sweep at a point), `/sites`, `/sites/{id}/sweep`, `/explain/route`, `/explain/narrative`, `/investigate` (server-sent events, one per step) and `/layers/suggest`. The solved cases are precomputed into `sites/<id>/`, so the demo does not depend on a live download. 345 backend tests.

### Built / Simulated / Next

**Built — runs on real NASA data**

- The statistics engine: anomalies, Mann–Kendall with Hamed–Rao, Sen's slope and interval, Benjamini–Hochberg, verdicts and years needed.
- The climate split as a range across climate models, with the policy that withholds it where it would mislead.
- Three solved cases with 3D relief, yearly NASA maps, a shared timeline and the drone view.
- The investigator: land cover, LLM-planned steps from a fixed menu, live results on the map, an answer built from data.
- The narrator with its figure validator and template fallback.

**Narrowed for the demo**

- The per-pixel trend map exists for one variable at one site (Lake Mead, daytime ground temperature). Other layers are yearly observed maps, not trend-tested per pixel, and are labelled as such.
- At an arbitrary point, the investigator covers climate (POWER), water storage (GRACE), soil moisture and runoff (GLDAS, slow), land cover and pictures. The 3D relief and drone view exist only for the three cases.
- The drone view's close-up relief and photos are national datasets (USGS, swisstopo, IGN Spain), not NASA, and are credited on screen.
- Vertical exaggeration in the 3D relief is a visual choice, labelled on screen.

**Next**

- Precompute relief and yearly maps on demand, so any point can become a solved case.
- Per-pixel trend maps for vegetation and water extent.
- Ocean and atmosphere variables (sea surface temperature, aerosols) to match the breadth of the challenge.
- Spanish interface.

### NASA data used

| Resource | Link | Role in the solution |
|---|---|---|
| **GRACE / GRACE-FO JPL mascons RL06.3 v04** (PO.DAAC) | https://podaac.jpl.nasa.gov/dataset/TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4 | Total water storage anomaly: the main record of the water cases and of the investigator's water step. |
| **NASA POWER** (MERRA-2, IMERG, CERES) | https://power.larc.nasa.gov/ | Air temperature, rain and snow, sunshine: the climate drivers of the split, the investigator's climate step and explore. |
| **GLDAS Noah 0.25° monthly v2.1** (GES DISC, Hydrology Data Rods) | https://disc.gsfc.nasa.gov/datasets/GLDAS_NOAH025_M_2.1/summary | Topsoil moisture and surface runoff. |
| **MODIS MOD11A2** land surface temperature, via AppEEARS | https://doi.org/10.5067/MODIS/MOD11A2.061 | Daytime ground temperature: series and the per-pixel trend map at Lake Mead. |
| **MODIS MOD11C3** and **MOD13A3**, via NASA GIBS | https://nasa-gibs.github.io/gibs-api-docs/ | Yearly maps of daytime ground temperature and vegetation (NDVI), decoded into value grids. |
| **MODIS MCD12Q1** land cover, via NASA GIBS | https://doi.org/10.5067/MODIS/MCD12Q1.061 | What kind of place a clicked point is; drives the investigator's plan. |
| **MODIS Terra corrected reflectance**, via NASA GIBS | https://nasa-gibs.github.io/gibs-api-docs/ | Then-and-now pictures of the same season (pictures, not measurements). |
| **NASADEM** 1 arc-second (LP DAAC) | https://lpdaac.usgs.gov/products/nasadem_hgtv001/ | Elevation for the 3D relief of the three cases. |
| **HLS** Harmonized Landsat Sentinel-2 (LP DAAC) | https://lpdaac.usgs.gov/data/get-started-data/collection-overview/missions/harmonized-landsat-sentinel-2-hls-overview/ | Cloud-free 30 m median base imagery draped on the relief. |
| **Blue Marble** via NASA GIBS | https://nasa-gibs.github.io/gibs-api-docs/ | Base map of the investigator and explore. |

Not NASA, used for validation or close-ups and credited on screen: U.S. Bureau of Reclamation Lake Mead elevations (validation of the GRACE story and the drone view's water level), USGS 3DEP lidar and USDA NAIP, swisstopo swissALTI3D and SWISSIMAGE, IGN Spain MDT05 and PNOA, OpenStreetMap / OpenFreeMap map labels.

### Limitations

- **The climate split is a clue, not an attribution.** Any driver we did not include ends up in the unexplained share. We report it as "not explained by climate", with a range across models, never as "caused by people".
- **GRACE sees a region about 300 km wide**, not only the lake, glacier or wetland. The app says so next to every GRACE figure.
- **The answer depends on the period.** All cases use 2003–2024; a different start year changes the slope.
- **Short or gappy records cannot carry a conclusion.** GRACE has a gap between missions (2017–2018); where a series is too short the app says "can't tell yet" and estimates the years needed.
- **Mann–Kendall tests a monotonic trend.** A step change or a reversal can mislead it; Lake Mead's 2023 rebound is visible in the series for that reason.
- **Multiple-testing control costs power.** A real but weak trend can come out as "likely". A false "real" is worse for a student than an honest "can't tell".
- **Smoothed maps.** MODIS layers are 1 km pixels; where they are smoothed for display, the legend says so.
- **The language model can still be wrong in tone** even when every number is checked; if the validator fails twice, the text is replaced by a template.

### References & licenses

**Method**

- Mann, H. B. (1945). Nonparametric tests against trend. *Econometrica* 13, 245–259.
- Sen, P. K. (1968). Estimates of the regression coefficient based on Kendall's tau. *JASA* 63, 1379–1389.
- Hamed, K. H. & Rao, A. R. (1998). A modified Mann–Kendall trend test for autocorrelated data. *Journal of Hydrology* 204, 182–196. https://doi.org/10.1016/S0022-1694(97)00125-X
- Benjamini, Y. & Hochberg, Y. (1995). Controlling the false discovery rate. *JRSS-B* 57, 289–300.
- Evans, J. & Geerken, R. (2004). Discrimination between climate and human-induced dryland degradation. *Journal of Arid Environments* 57, 535–554. https://doi.org/10.1016/S0140-1963(03)00121-6
- Wessels, K. J. et al. (2012). Limits to detectability of land degradation by trend analysis of vegetation index data. *Remote Sensing of Environment*. https://doi.org/10.1016/j.rse.2012.06.022

**Data.** All NASA datasets above are open through NASA Earthdata and cited in the app. NASA imagery and data are generally not subject to copyright in the United States, but attribution is required and the NASA insignia is not public domain, so no NASA logo appears in this project.

**Software licences** (from the installed versions on 14 Nov 2026)

| Component | Licence |
|---|---|
| Next.js 16.4.6, React 19.3.0 | MIT |
| three.js 0.187.0, @react-three/fiber 9.8.2, @react-three/drei 10.7.9 | MIT |
| MapLibre GL JS 5.24.1 | BSD-3-Clause |
| zod 3.25.76 | MIT |
| FastAPI 0.162.7, pymannkendall 1.4.3, anthropic 2.8.0 | MIT |
| numpy 2.5.4, pandas 3.1.1, scipy 1.18.1, statsmodels 0.15.0, httpx 0.28.1 | BSD-3-Clause |
| xarray 2026.9.0 | Apache-2.0 |
| Pillow 13.0.0 | MIT-CMU (HPND) |

**Our project** is released under the **Apache License 2.0** (`LICENSE`).

### Use of AI

See `AI.md` in the repository. Claude (Anthropic) was used as a coding assistant; commits made with its help carry a `Co-Authored-By: Claude` line. Inside the product, a language model plans investigations from a fixed menu, routes questions to variables and writes explanations. It never computes, decides significance or names a cause; every figure it writes is checked against the data, and model-written text is labelled on screen ("Written by an AI narrator from this case’s numbers.").

---

## 6. Space Agency Partner Data and Other References

Short version for the dedicated form field:

- NASA PO.DAAC — GRACE/GRACE-FO JPL mascons RL06.3 — total water storage.
- NASA POWER — https://power.larc.nasa.gov/ — climate drivers, investigator and explore.
- NASA GES DISC — GLDAS Noah v2.1 via Hydrology Data Rods — soil moisture and runoff.
- NASA AppEEARS / LP DAAC — MODIS MOD11A2 — ground temperature series and per-pixel trend.
- NASA GIBS — MODIS MOD11C3, MOD13A3, MCD12Q1, Terra true colour and Blue Marble — yearly maps, land cover, pictures, base map.
- NASA LP DAAC — NASADEM elevation and HLS imagery.
- U.S. Bureau of Reclamation — Lake Mead elevations (validation, not NASA).
- USGS 3DEP and USDA NAIP; swisstopo swissALTI3D and SWISSIMAGE; IGN Spain MDT05 and PNOA — close-up relief and aerial photos for the drone view.
- OpenStreetMap contributors (ODbL) via OpenFreeMap — map labels, attributed on screen.
- Open-source libraries listed in §5.

No Space Agency Partner data was used beyond NASA's own.

---

## 7. Use of Super Intelligence (SI) — form field answer

> Yes, in two ways.
>
> **(1) As a development tool.** Claude (Anthropic) assisted with writing and refactoring backend and frontend code, data scripts, tests and English copy. The team chose the method, variables and cases, and reviewed, ran and tested the code. Commits made with its help are marked in the git history; details in `AI.md`.
>
> **(2) Inside the product.** A language model plans an investigation by picking steps from a fixed menu, routes questions to the variables that exist for a place, and turns computed values into a plain-language explanation. It does not compute, does not decide significance and cannot assign a cause. A validator compares every figure in its output with the source values; on a mismatch the text is replaced by a fixed template. The interface labels model-written text.
>
> No image, audio or video in this project is SI-generated. Model output is attributed to the model, never to NASA, and no NASA branding appears alongside it.
