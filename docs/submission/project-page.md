# Project page — submission copy (English)

> Paste-ready text for the NASA Space Apps 2026 Project tab, in the official form order (`rules.md` §4).
> Rewritten on 15 Nov 2026 (freeze day) for the current product, Alibi. Every figure below comes from
> `sites/*/site.json` or from the recorded run `backend/data/recordings/mead.json`; re-check them if the
> pipeline is re-run or the recording is replaced.

## Slots to resolve before submitting

| Slot | Where | What to do |
|---|---|---|
| `[DEMO_URL]` | §3 | Public link to the deck at `[LIVE_URL]/deck.html` (7 slides, no login), or the 30-second video if it is recorded. PDF copy of the deck: `docs/submission/deck.pdf` (if exported). |
| `[LIVE_URL]` / `[REPO_URL]` | §4, deck slide 7 | Deployed app and the GitHub repository (`https://github.com/mandycs/earth-trend-detective`), made public at freeze. Test both in a private window. The deployed web app must be built with `NEXT_PUBLIC_API_URL` pointing at the public API, and the API must list the web origin in `CORS_ORIGINS`. |
| `43Segfault` | §6, deck slides 1 and 7 | Team name and member names, as registered on the Space Apps site. |

---

## 1. Project Name

**Alibi — an Earth trend detective**

---

## 2. High-Level Project Summary

The satellites saw it all; nobody told the story. NASA has measured every place on Earth for decades and the data is public, but reading it takes tools few people speak: gravity-satellite mascons, trend tests, false-discovery control. Alibi brings those tools into everyday language.

Anyone, from a curious 16-year-old to a journalist, asks about a place in their own words: "Is the lake near me really going down? Is it the drought, or us?" Alibi's detective agent picks the NASA records that apply there (GRACE water storage, NASA POWER climate, GLDAS soil moisture, MODIS land cover and temperature), runs the statistics in code, lays every record over the same ground, and answers in plain words: real, likely, or can't tell yet.

It stays honest by design. A checker compares every figure in the answer with the data, the share of a change the measured climate does not explain is "a clue, not proof", and a map guide explains every layer in plain words or under the hood. Four solved cases show it: Lake Mead, the Aletsch Glacier, Doñana and the Great Barrier Reef.

*184 words.*

---

## 3. Link to Project Demo

`[DEMO_URL]`

Format: 7-slide deck (`frontend/public/deck.html`, served at `[LIVE_URL]/deck.html`; title and team on slide 1). Works on desktop and phone, no login.

---

## 4. Link to Final Project

Live app: `[LIVE_URL]`
Recorded detective run (no API key needed): `[LIVE_URL]/detective?replay=mead`
Source code (Apache-2.0): `[REPO_URL]`

---

## 5. Detailed Project Description

### What it does

Most climate tools show you a line. Alibi tells you what the line means, and what it does not mean, in the words you would use to ask.

**Ask the detective (`/detective`).** Click any point on the globe and ask a question in plain English. The detective agent:

1. **Reads the place.** NASA MODIS land cover says what kind of place it is (desert, water body, cropland...), so a snow record is never offered for a desert.
2. **Turns your words into records.** "Is the water going down?" becomes *Total water stored* (GRACE & GRACE-FO gravity satellites), *Rainfall* (NASA POWER) and *Air temperature* (MERRA-2). The screen shows this translation ("How Alibi read your question") with the source of each record, and "The methods behind the words" one tap away.
3. **Tests what changed.** Trend tests, a climate check (how much of the change the measured climate explains), year-by-year matches between records, then-and-now land cover. Code runs every test; the model only chooses which to run, from a fixed menu.
4. **Lays the evidence over the same ground.** Each record is drawn on the map; "Explode the evidence" stacks every layer over the 3D ground of the place.
5. **Answers in plain words.** A short answer, "A clue, not proof.", "✓ every figure checked · N tests run", a case board of suspects (supported, hint, ruled out) and the next questions to ask. A follow-up question continues the same case.

A recorded run (`/detective?replay=mead`) replays a real investigation without a live model call. In it, the question "Lake Mead has been dropping for twenty years. Is it the drought upstream or is it us taking too much water, and is it still getting worse recently?" gets, after 7 tests: total water stored fell about 6.5 cm per decade from 2003 to 2024, a real drop; local rain shows no clear trend; air temperature rose about 0.68 °C per decade but no test links it to the water; 77.5% of the fall is not explained by the climate measured there, a clue, not proof; and whether it is still getting worse is unknown (2014–2024 alone: can't tell yet).

**"How to read this map."** A guide with two tabs: *In plain words* (the pin, the dashed square that one satellite value covers, the curtain, the stamps) and *Under the hood* (dataset ids, servers, resolution and period of every layer and record).

**Four solved cases**, 2003–2024, told in three chapters (*What is changing? → Is it real? → Is it the climate?*) over real terrain and yearly maps:

- **Lake Mead (USA).** Total water stored is going down for real: −6.5 cm per decade (likely range −9.6 to −3.6). Between 54% and 84% of that change is not explained by climate, depending on the climate model (with or without the upstream basin).
- **Aletsch Glacier (Switzerland).** Air temperature rises 1.0 °C per decade and total water stored falls 6.9 cm per decade, both real. Here Alibi deliberately gives no climate split: GRACE sees a region about 300 km wide dominated by snow and ice, and the climate model has no snow term, so a split would mislead. It says so on screen.
- **Doñana wetlands (Spain).** Total water stored is likely going down (−8.6 cm per decade, "likely", not "real"); topsoil moisture is falling for real; rainfall shows no clear trend.
- **Great Barrier Reef (Australia).** Sea surface temperature over the reef is going up for real (0.23 °C per decade). Reef-years with heat stress at or above 4 °C-weeks: 1 in 2003–2013, 20 in 2014–2024. Sea temperature is itself climate, so this case has no climate split; heat stress is not coral death, and the case does not count corals.

Every verdict is icon plus words, never colour alone:

- **↑/↓ Real** — the trend survives the significance test and the correction for testing many records at once.
- **Likely** — probably changing; a strong hint, not proof yet.
- **? Can't tell yet** — too noisy or too short to tell a change from chance, with an estimate of how many more years would be needed.

### How we built it

**Pipeline** (`backend/app`), each stage testable on its own:

1. **Catalogue and gather.** A closed catalogue of variables stores dataset, band, units and where each applies. Series come from GRACE (PO.DAAC), NASA POWER, GLDAS (GES DISC), MODIS (AppEEARS, GIBS) and, for the ocean, JPL MUR SST and MODIS Aqua chlorophyll via NOAA CoastWatch ERDDAP.
2. **Trend test.** Monthly series become anomalies (seasonal cycle removed) and are tested with Mann–Kendall plus the Hamed–Rao autocorrelation correction, Sen's slope with its interval, and Benjamini–Hochberg control across every test in the case.
3. **Climate check.** A generalised RESTREND approach (Evans & Geerken 2004; Wessels et al. 2012): regress the impact variable on its climate drivers and trend-test what is left, across more than one climate model, reported as a range. A policy withholds the split where it would mislead (snow and glacier sites, ocean temperature, model-only variables).
4. **Detective agent** (`backend/app/detective`, LangGraph). A language model plans the investigation by calling tools from a fixed menu (profile the place, list the records, fetch a series, trend test, climate check, correlate, land cover change, water extent, show a layer, update the case board). The code runs each tool, keeps a ledger of every test, applies the multiple-testing correction over the whole case, and decides what a suspect's status may be. Runs stream as server-sent events, are checkpointed in SQLite, and can be continued or forked.
5. **Checker.** The answer is checked against the ledger: every number, direction and certainty word must match a computed value; causal claims, "proof" and statistics jargon are rejected. On failure, a template answer built by code is shown.

**Frontend.** Next.js 16, React 19. The detective map uses MapLibre GL over NASA Blue Marble with 3D relief; the evidence stack and the case relief use three.js with react-three-fiber. Brand: Alibi (ink on ground; the red thread lives only in the mark).

**Backend.** FastAPI: `/detective` (SSE), `/sites`, `/sweep`, `/investigate`, `/explain/*`, `/layers/suggest`. The solved cases are precomputed into `sites/<id>/`, and recorded runs live in `backend/data/recordings/`, so the demo does not depend on a live download.

### Built / Simulated / Next

**Built — runs on real data**

- The detective agent at any point on Earth: land cover, records chosen from the question, tests run by code, layers on the map, the evidence stack, the case board, the checked answer and next questions.
- The statistics engine: anomalies, Mann–Kendall with Hamed–Rao, Sen's slope and interval, Benjamini–Hochberg, verdicts and years needed.
- The climate check as a range across climate models, with the policy that withholds it where it would mislead.
- Four solved cases with terrain, yearly maps and a shared timeline.
- The map guide in plain words and under the hood.

**Narrowed for the demo**

- The Lake Mead replay is a recording of a real run (15 Nov 2026), labelled "Replay of a recorded run" on screen; "Run it live" starts a new one.
- Live runs need a model key and can be slow when a source (GLDAS, AppEEARS) is slow.
- The per-pixel trend map exists for one variable at one site (Lake Mead, daytime ground temperature). Other layers are yearly observed maps, labelled as such.
- Close-up relief and photos are national datasets (USGS, swisstopo, IGN Spain); the detective map's relief is AWS Terrain Tiles (Mapzen). None of these is NASA, and each says so on screen.
- Vertical exaggeration in 3D relief is a visual choice, labelled on screen.

**Next**

- Turn any point into a solved case, with relief and yearly maps, on demand.
- Per-pixel trend maps for vegetation and water.
- More ocean and air records.
- Spanish interface.

### NASA data used

| Resource | Link | Role in the solution |
|---|---|---|
| **GRACE / GRACE-FO JPL mascons RL06.3 v04** (PO.DAAC) | https://podaac.jpl.nasa.gov/dataset/TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4 | Total water storage anomaly: the main record of the water cases and of the detective's water questions. |
| **NASA POWER** (MERRA-2, IMERG, CERES) | https://power.larc.nasa.gov/ | Air temperature, rain and snow, sunshine: the climate drivers of the climate check and the detective's climate records. |
| **GLDAS Noah 0.25° monthly v2.1** (GES DISC, Hydrology Data Rods) | https://disc.gsfc.nasa.gov/datasets/GLDAS_NOAH025_M_2.1/summary | Topsoil moisture and surface runoff. |
| **MODIS MOD11A2** land surface temperature, via AppEEARS | https://doi.org/10.5067/MODIS/MOD11A2.061 | Daytime ground temperature: series and the per-pixel trend map at Lake Mead. |
| **MODIS MOD11C3** and **MOD13A3**, via NASA GIBS | https://nasa-gibs.github.io/gibs-api-docs/ | Yearly maps of daytime ground temperature and vegetation (NDVI), decoded into value grids. |
| **MODIS MCD12Q1** land cover, via NASA GIBS | https://doi.org/10.5067/MODIS/MCD12Q1.061 | What kind of place a clicked point is; drives which records the detective offers; then-and-now land cover. |
| **MODIS Terra corrected reflectance**, via NASA GIBS | https://nasa-gibs.github.io/gibs-api-docs/ | Then-and-now pictures of the same season (pictures, not measurements). |
| **NASADEM** 1 arc-second (LP DAAC) | https://lpdaac.usgs.gov/products/nasadem_hgtv001/ | Elevation for the 3D relief of the solved cases. |
| **HLS** Harmonized Landsat Sentinel-2 (LP DAAC) | https://lpdaac.usgs.gov/data/get-started-data/collection-overview/missions/harmonized-landsat-sentinel-2-hls-overview/ | Cloud-free 30 m median base imagery draped on the relief. |
| **Blue Marble** via NASA GIBS | https://nasa-gibs.github.io/gibs-api-docs/ | Base map of the detective and explore. |
| **OPERA DSWx-HLS** surface water, via NASA GIBS | https://nasa-gibs.github.io/gibs-api-docs/ | Yearly open-water area of a lake or reservoir box (the detective's `water_extent` tool). |
| **JPL MUR SST** (GHRSST L4, monthly), via NOAA CoastWatch ERDDAP | https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST41mday.html | Sea surface temperature trend of the Great Barrier Reef case. NASA data, served by NOAA. |
| **MODIS Aqua chlorophyll-a** (R2022), via NOAA CoastWatch ERDDAP | https://coastwatch.pfeg.noaa.gov/erddap/griddap/erdMH1chlamday_R2022SQ.html | Chlorophyll in the sea at the reef. NASA data, served by NOAA. |

Not NASA, used for validation, context or close-ups and credited on screen: NOAA Coral Reef Watch degree heating weeks (reef heat stress), GEBCO 2020 bathymetry via ERDDAP, AWS Terrain Tiles (Mapzen) relief on the detective map, U.S. Bureau of Reclamation Lake Mead elevations (validation), USGS 3DEP lidar and USDA NAIP, swisstopo swissALTI3D and SWISSIMAGE, IGN Spain MDT05 and PNOA, OpenStreetMap / OpenFreeMap map labels.

### Limitations

- **The climate split is a clue, not an attribution.** Any driver we did not include ends up in the unexplained share. We report it as "not explained by climate", with a range across models, never as "caused by people".
- **GRACE sees a region about 300 km wide**, not only the lake, glacier or wetland. The app says so next to every GRACE figure.
- **The answer depends on the period.** All cases use 2003–2024; a different start year changes the slope.
- **Short or gappy records cannot carry a conclusion.** GRACE has a gap between missions (2017–2018); where a series is too short the app says "can't tell yet" and estimates the years needed.
- **Mann–Kendall tests a monotonic trend.** A step change or a reversal can mislead it; Lake Mead's 2023 rebound is visible in the series for that reason.
- **Multiple-testing control costs power.** A real but weak trend can come out as "likely". A false "real" is worse for a student than an honest "can't tell".
- **Smoothed maps.** MODIS layers are 1 km pixels; where they are smoothed for display, the legend says so.
- **The language model can still be wrong in tone** even when every number is checked; if the checker fails, the text is replaced by a template.
- **The detective only answers with what it measured.** Water use, dams and pumping are not measured directly; when an answer points at people, it is a clue, never a cause.
- **Ocean.** Heat stress (degree heating weeks) measures heat, not bleaching or coral death. Sea temperature is part of the climate, so the reef case has no climate split. NASA MUR SST and NOAA Coral Reef Watch are never mixed in one verdict.

### References & licenses

**Method**

- Mann, H. B. (1945). Nonparametric tests against trend. *Econometrica* 13, 245–259.
- Sen, P. K. (1968). Estimates of the regression coefficient based on Kendall's tau. *JASA* 63, 1379–1389.
- Hamed, K. H. & Rao, A. R. (1998). A modified Mann–Kendall trend test for autocorrelated data. *Journal of Hydrology* 204, 182–196. https://doi.org/10.1016/S0022-1694(97)00125-X
- Benjamini, Y. & Hochberg, Y. (1995). Controlling the false discovery rate. *JRSS-B* 57, 289–300.
- Evans, J. & Geerken, R. (2004). Discrimination between climate and human-induced dryland degradation. *Journal of Arid Environments* 57, 535–554. https://doi.org/10.1016/S0140-1963(03)00121-6
- Wessels, K. J. et al. (2012). Limits to detectability of land degradation by trend analysis of vegetation index data. *Remote Sensing of Environment*. https://doi.org/10.1016/j.rse.2012.06.022

**Data.** All NASA datasets above are open through NASA Earthdata and cited in the app. NASA imagery and data are generally not subject to copyright in the United States, but attribution is required and the NASA insignia is not public domain, so no NASA logo appears in this project.

**Software licences** (from the installed versions on 14–15 Nov 2026; LangGraph and LangChain versions from `backend/uv.lock`)

| Component | Licence |
|---|---|
| Next.js 16.4.6, React 19.3.0 | MIT |
| three.js 0.187.0, @react-three/fiber 9.8.2, @react-three/drei 10.7.9 | MIT |
| MapLibre GL JS 5.24.1 | BSD-3-Clause |
| zod 3.25.76 | MIT |
| LangGraph 1.2.22, langgraph-checkpoint-sqlite 3.1.3, langchain-core 1.8.0, langchain-anthropic 1.7.10, langchain-openai 1.8.0 | MIT |
| FastAPI 0.162.7, pymannkendall 1.4.3, anthropic 2.8.0 | MIT |
| numpy 2.5.4, pandas 3.1.1, scipy 1.18.1, statsmodels 0.15.0, httpx 0.28.1 | BSD-3-Clause |
| xarray 2026.9.0 | Apache-2.0 |
| Pillow 13.0.0 | MIT-CMU (HPND) |

**Our project** is released under the **Apache License 2.0** (`LICENSE`).

### Use of AI

See `AI.md` in the repository. Claude (Anthropic) was used as a coding assistant; commits made with its help carry a `Co-Authored-By: Claude` line. Inside the product, a language model (Claude) runs the detective: it turns a question into records, picks tools from a fixed menu, and writes the plain-words answer. It also routes questions to variables and writes case explanations. It never computes, decides significance or names a cause; every figure it writes is checked against the data, and model-written text is labelled on screen ("Written by an AI narrator from this case’s numbers.").

---

## 6. Space Agency Partner Data and Other References

Short version for the dedicated form field:

- NASA PO.DAAC — GRACE/GRACE-FO JPL mascons RL06.3 — total water storage.
- NASA POWER — https://power.larc.nasa.gov/ — climate drivers, the detective and explore.
- NASA GES DISC — GLDAS Noah v2.1 via Hydrology Data Rods — soil moisture and runoff.
- NASA AppEEARS / LP DAAC — MODIS MOD11A2 — ground temperature series and per-pixel trend.
- NASA GIBS — MODIS MOD11C3, MOD13A3, MCD12Q1, Terra true colour, OPERA DSWx-HLS and Blue Marble — yearly maps, land cover, water extent, pictures, base map.
- NASA JPL MUR SST and MODIS Aqua chlorophyll, served by NOAA CoastWatch ERDDAP — the Great Barrier Reef case.
- NASA LP DAAC — NASADEM elevation and HLS imagery.
- NOAA Coral Reef Watch degree heating weeks and GEBCO 2020 bathymetry, via NOAA CoastWatch ERDDAP (not NASA) — reef heat stress and seabed.
- AWS Terrain Tiles (Mapzen) — relief on the detective map (not NASA).
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
> **(2) Inside the product.** A language model (Claude) runs Alibi's detective: it turns a plain question into the records that exist for a place, picks tools from a fixed menu, and turns computed values into a plain-language answer. It does not compute, does not decide significance and cannot assign a cause. A validator compares every figure in its output with the source values; on a mismatch the text is replaced by a fixed template. The interface labels model-written text.
>
> No image or video in this project is SI-generated. The background music of the films (the landing film and the web pitch film) was generated with Google Lyria (SI) and is labelled as such in the video descriptions and in the files' metadata. The 30-second submission video uses a separate instrumental track generated with Google Lyria 3 Pro (AI) through Artlist, declared in its description and metadata. Model output is attributed to the model, never to NASA, and no NASA branding appears alongside it.

