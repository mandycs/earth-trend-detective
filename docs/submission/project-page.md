# Project page — submission copy (English)

> Paste-ready text for the NASA Space Apps 2026 Project tab. Fields follow the official form order
> (`rules.md` §4). Written to be copied as-is; only the slots listed below need to be resolved.

## Slots to resolve before submitting

| Slot | Where | What to do |
|---|---|---|
| `[DEMO_URL]` | §3 | Public link to the 30-second video (YouTube unlisted is fine: public, no login, no permission request). |
| `[LIVE_URL]` / `[REPO_URL]` | §4 | Deployed app and public GitHub repository. Test both in a private window. |
| `[CASE 3 SITE]` | §5, twice | Third story-mode case (working candidate: Doñana wetlands, Spain). Confirm with the data before naming it. |
| Case figures | §5 "Built / Simulated / Next" | Insert the final Sen slopes and p-values from the last pipeline run. Do not estimate them. |
| Dependency licences | §5 "References & licenses" | Re-generate from `package-lock.json` / backend lockfile at freeze time; the list below is current as of the draft. |
| Team names | §6 | Team name and member names, as registered on the Space Apps site. |

---

## 1. Project Name

**Earth Trend Detective**

---

## 2. High-Level Project Summary

Earth Trend Detective answers one question for any place on Earth: what is changing here, is the change real, and how much of it does the climate not explain?

A user picks a location. The tool selects the NASA Earth-observation variables that apply there, pulls their time series, removes the seasonal cycle, and runs a Mann–Kendall trend test with Sen's slope, corrected for autocorrelation and controlled for false discovery across the many variables tested. It reports a verdict in plain words — real change, likely change, or can't tell yet — plus how many more years of data would probably be needed. It then models each impact variable on its climate drivers; the trend left in the residual is the part the climate does not explain. A language model turns the computed numbers into a short explanation, and a validator checks every figure against the data it was given; if a number does not match, the text falls back to a template.

Three worked cases in 3D and a free-explore map teach the method rather than just plotting data.

*179 words. Our team's internal target is 50–200 words; NASA publishes no word limit for this field, so treat the range as our own convention, not a requirement.*

---

## 3. Link to Project Demo

`[DEMO_URL]`

Format: 30-second screen-recorded video, English voice-over with burned-in English captions. Script: `video-30s.md`.

---

## 4. Link to Final Project

Live app: `[LIVE_URL]`
Source code (Apache-2.0): `[REPO_URL]`

---

## 5. Detailed Project Description

### What it does

Most climate tools show you a line. This one tells you what the line means, and — more importantly — what it does not mean.

The app has two ways in.

**Story mode** walks through three solved cases, each rendered as a 3D block of real terrain built from an elevation model. Lake Mead: total water storage falls, while rainfall over the same basin shows no trend. Aletsch Glacier: snow cover retreats and land surface temperature rises together, so here the climate signal is the story. `[CASE 3 SITE]`: a place where the non-climate signal dominates. Each case is a short investigation with the same four steps, and the user scrubs a 2003–2024 timeline to watch the anomaly build up year by year. A trend layer can be switched on, painted per pixel from Sen's slope and dimmed where the trend is not significant.

**Explore mode** lets the user click anywhere on the map. The app profiles the location — land cover, climate zone, whether it is coastal, whether it has snow — decides which of its catalogued variables actually apply, fetches those series, and runs the same pipeline. If the record is too short, if the point is over open ocean, or if the data has a gap, it says so. It does not fill the hole with a guess.

Every result ends in one of three verdicts, always as icon plus text and never as colour alone, because a red/green scale excludes users who cannot separate the two:

- **↑ Real change** — the trend survives the significance test and the multiple-testing correction.
- **~ Likely change** — the trend is there but the evidence is not strong enough to call it.
- **? Can't tell yet** — including how many more years of data would probably be needed.

Then the part that we think matters most. For each impact variable (water storage, vegetation, snow), the app fits a regression on its climate drivers and runs the same trend test on the residual. The output is not "climate change caused this". The output is: *this fraction of the trend is not explained by the climate variables we have, and here is the list of things that could be responsible.* That is a lead for a student, a journalist or a council technician — not a verdict on the world.

### How we built it

**Pipeline.** Four stages, each one testable on its own.

1. **Profile.** A closed catalogue of variables (`variables.yaml`) stores, for each variable, its dataset, band, units, temporal resolution and where it applies. The region profile filters the catalogue down to the variables that make sense for that place, so a snow-cover variable is never offered for a mangrove.
2. **Sweep.** Monthly series are fetched, converted to anomalies by removing the mean seasonal cycle, and tested. We use the Mann–Kendall test with the Hamed–Rao variance correction for autocorrelation, Sen's slope for the rate, and Benjamini–Hochberg to control the false discovery rate across all the variables tested at once — because testing twenty variables at p < 0.05 will hand you one "significant" trend by chance. Variables are ranked by change normalised to standard deviations per decade, so a shrinking reservoir and a warming surface can be compared on the same axis.
3. **Residual.** A generalised RESTREND approach (Evans & Geerken 2004; Wessels et al. 2012): regress the impact variable on its climate drivers, then trend-test what is left. We report the share of the trend the drivers do not explain, with the honest caveat that omitted drivers end up in the residual too.
4. **Explain.** The language model receives a JSON object of computed values and returns prose. It never computes, never decides significance and never assigns a cause. A validator checks every number in the output against the JSON; on any mismatch the prose is discarded and a deterministic template is shown instead.

**Frontend.** React 19 with react-three-fiber for the terrain scenes, MapLibre for the 2D explore map. Terrain comes from a heightmap with a satellite base texture; the trend layer is a texture generated from the per-pixel Sen slope on a diverging scale, alpha-damped where the pixel's trend is not significant. The timeline swaps annual anomaly textures, so scrubbing is a texture swap rather than a re-render of the geometry.

**Backend.** FastAPI. Endpoints: `/profile`, `/sweep`, `/residual`, `/years`, `/explain`, `/sites/{id}`. Expensive work is precomputed for the story cases and cached for explore-mode points, so the demo does not depend on a live download during judging.

**Deployment.** Static frontend plus a small API service, both public. No login, no key required from the user; Earthdata credentials stay server-side in environment variables.

### Built / Simulated / Next

We are explicit about this because a demo that blurs the line is worse than a smaller demo that does not.

**Built — runs on real NASA data**

- The statistics engine: anomaly decomposition, Mann–Kendall with Hamed–Rao correction, Sen's slope, Benjamini–Hochberg control, verdict thresholds.
- The residual model and the "% not explained by climate" figure.
- Story-mode 3D viewer: terrain, trend layer, timeline, verdict panels, all driven by the `site.json` contract.
- Explore mode: click → profile → sweep → verdict, on NASA POWER variables (temperature, precipitation, radiation, humidity), which need no authentication.
- The narrator with its number validator and template fallback.

**Simulated or narrowed for the demo**

- Explore-mode points are limited to the variables available from NASA POWER; water storage and snow are only computed for precomputed case sites. The UI says which variables were checked and which were not.
- Per-pixel trend maps are computed at reduced resolution for browser performance, not at native 1 km.
- The RAG corpus behind the follow-up questions is a curated set of dataset sheets and method papers, not an open web search.
- Vertical exaggeration in the 3D scenes is a visual choice, labelled on screen; it is not a measurement.

**Next**

- Ocean and atmosphere variables (sea surface temperature, aerosol, ozone) to match the breadth the challenge describes.
- Uncertainty bands on the residual share instead of a point value.
- Spanish UI, since the first audience we tested with is in Málaga.
- Precompute on demand for any region, so explore mode is not limited to POWER.
- A "compare two places" view, because the same variable moving in opposite directions in two regions is the clearest way to show that a trend is local.

### NASA data used

| Resource | Link | Role in the solution |
|---|---|---|
| **NASA POWER** (Prediction Of Worldwide Energy Resources) | https://power.larc.nasa.gov/ | Meteorology for any clicked point — temperature, precipitation, radiation, humidity — with no authentication. Drives explore mode and supplies the climate-driver side of the residual model. |
| **MODIS MOD13Q1** vegetation indices (16-day, 250 m), via AppEEARS | https://appeears.earthdatacloud.nasa.gov/ · https://doi.org/10.5067/MODIS/MOD13Q1.061 | NDVI/EVI series for case areas. Primary impact variable for the vegetation case and an input to the residual regression. |
| **MODIS MOD11A2** land surface temperature (8-day, 1 km), via AppEEARS | https://doi.org/10.5067/MODIS/MOD11A2.061 | Land surface temperature trend, and the climate driver in the glacier case. |
| **MODIS MOD16A2** evapotranspiration (8-day, 500 m), via AppEEARS | https://doi.org/10.5067/MODIS/MOD16A2.061 | Water-flux variable: an impact variable in its own right and a driver when explaining vegetation change. |
| **MODIS MOD10A2** snow cover (8-day, 500 m), via AppEEARS | https://doi.org/10.5067/MODIS/MOD10A2.061 | Snow persistence for the Aletsch case; the variable that makes the seasonal cycle removal visible. |
| **GRACE / GRACE-FO JPL mascon RL06.3 v04** (equivalent water height, CRI filtered), via PO.DAAC | https://podaac.jpl.nasa.gov/dataset/TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4 | Total water storage anomaly. The primary variable for the Lake Mead case and the reason the app can talk about groundwater loss at all. |
| **GLDAS** land surface fields, via GES DISC Hydrology Time Series ("data rods") | https://disc.gsfc.nasa.gov/information/tools?title=Hydrology%20Data%20Rods | Model-consistent soil moisture, evapotranspiration and runoff, used where GRACE resolution is too coarse to separate the components of storage change. |
| **NASADEM** merged DEM, 1 arc-second | https://lpdaac.usgs.gov/products/nasadem_hgtv001 | Elevation for the 3D terrain in story mode. Relief is real; the vertical exaggeration is labelled. |
| **NASA GIBS** (Global Imagery Browse Services) | https://nasa-gibs.github.io/gibs-api-docs/ | Satellite base imagery draped on the terrain and the explore-mode basemap. |
| **Giovanni** (validation only, not runtime) | https://giovanni.gsfc.nasa.gov/giovanni/ | Independent check of one series per case site: we compare our extracted series against Giovanni's for the same variable, period and area, and keep the screenshot as evidence. |

### Limitations

- **The residual is a lead, not an attribution.** Any driver we did not include — irrigation efficiency, land-use policy, a new dam, fire — lands in the residual. We report it as "not explained by these climate variables", never as "caused by humans".
- **The answer depends on the period.** Start the series in a wet year and the slope changes. The app shows the period it used and lets the user see the series rather than only the verdict.
- **Short records cannot carry a conclusion.** GRACE has a gap between missions and SWOT's record is short; where the series is too short, the app says "can't tell yet" and estimates the years needed rather than reporting a slope.
- **Different resolutions.** MODIS at 250 m to 1 km, GRACE at 3° mascons and POWER at its own grid are harmonised onto a common analysis grid. That harmonisation is a modelling choice and it smooths small-scale features.
- **Mann–Kendall tests a monotonic trend.** A step change, a reversal or a strongly non-linear trend can pass or fail in ways that mislead. Seasonal removal is a monthly-climatology approach, which is adequate for these series but not for every variable.
- **Multiple-testing control costs power.** With FDR control, a real but weak trend can be labelled "likely" instead of "real". We chose that trade deliberately: a false "real" is worse for a student than an honest "can't tell".
- **The language model can still be wrong in tone**, even when every number is checked. If the validator fails, the text is replaced by a template, which reads flatter but cannot be wrong.
- **Explore mode is narrower than story mode.** It sees POWER variables only; it will not detect groundwater depletion at an arbitrary point. The UI states which variables were tested.

### References & licenses

**Method**

- Mann, H. B. (1945). Nonparametric tests against trend. *Econometrica* 13, 245–259.
- Sen, P. K. (1968). Estimates of the regression coefficient based on Kendall's tau. *JASA* 63, 1379–1389.
- Hamed, K. H. & Rao, A. R. (1998). A modified Mann–Kendall trend test for autocorrelated data. *Journal of Hydrology* 204, 182–196. https://doi.org/10.1016/S0022-1694(97)00125-X
- Benjamini, Y. & Hochberg, Y. (1995). Controlling the false discovery rate. *JRSS-B* 57, 289–300.
- Evans, J. & Geerken, R. (2004). Discrimination between climate and human-induced dryland degradation. *Journal of Arid Environments* 57, 535–554. https://doi.org/10.1016/S0140-1963(03)00121-6
- Wessels, K. J. et al. (2012). Limits to detectability of land degradation by trend analysis of vegetation index data. *Remote Sensing of Environment*. https://doi.org/10.1016/j.rse.2012.06.022

**Data**

All NASA datasets above are open and free of charge through NASA Earthdata; each is cited by DOI in the table and in the app's footer. NASA imagery and data are generally not subject to copyright in the United States, but attribution is required and the NASA insignia is not public domain, so no NASA logo appears anywhere in this project.

**Software licences** (verified from the lockfiles at draft time; re-check at freeze)

| Component | Licence |
|---|---|
| React 19.3.1 | MIT |
| three.js 0.187.0 | MIT |
| @react-three/fiber 9.8.2 | MIT |
| @react-three/drei 10.7.9 | MIT |
| Vite 8.3.8 | MIT |
| TypeScript 7.0.2 | Apache-2.0 |
| FastAPI, pandas, numpy, pymannkendall | to be confirmed from the backend lockfile before submission |

**Our project** is released under the **Apache License 2.0** (`LICENSE` in the repository), which is also the licence NASA applies by default when a team does not specify one.

### Use of AI

Two separate uses, declared separately.

**1. AI as a development tool.** We used Claude (Anthropic) as a coding assistant: scaffolding the frontend, writing and refactoring parts of the statistics and API code, generating test cases, and tightening the English copy. Every generated change was reviewed, run and corrected by a team member; the method, the scope, the choice of variables and the interpretation of results are ours. The repository contains an `AI.md` file that records this, which is how we meet NASA's requirement to acknowledge SI-generated code in descriptive text.

**2. AI inside the product.** The explanation layer is a large language model that receives computed values as JSON and writes a short plain-language paragraph. Its role is deliberately narrow:

- It does not compute, rank or decide significance.
- It cannot name a cause; the prompt forbids causal language. It reports a lead, not an attribution.
- Every figure it writes is checked by a validator against the source values. On a mismatch the text is discarded and a deterministic template is shown.
- In the interface, the paragraph carries a visible label: *"Written by a language model from the computed values below. Every figure is checked against the data."*

No image, audio or video in this project is AI-generated. The demo is screen capture of the running application. Per NASA's SI guidelines, model output is attributed to the model, never to NASA, and no NASA branding appears alongside generated content.

---

## 6. Space Agency Partner Data and Other References

Short version for the dedicated form field:

- NASA POWER — https://power.larc.nasa.gov/ — meteorology, explore mode and climate drivers.
- NASA AppEEARS / LP DAAC — https://appeears.earthdatacloud.nasa.gov/ — MODIS subsets (MOD13Q1, MOD11A2, MOD16A2, MOD10A2).
- NASA PO.DAAC — https://podaac.jpl.nasa.gov/ — GRACE/GRACE-FO mascon total water storage.
- NASA GES DISC — https://disc.gsfc.nasa.gov/ — GLDAS land surface fields via the Hydrology Time Series service.
- NASA LP DAAC — https://lpdaac.usgs.gov/products/nasadem_hgtv001 — NASADEM elevation.
- NASA GIBS — https://nasa-gibs.github.io/gibs-api-docs/ — satellite base imagery.
- NASA Giovanni — https://giovanni.gsfc.nasa.gov/giovanni/ — independent validation of one series per case site.
- MapLibre GL JS (BSD-3-Clause) — 2D map rendering.
- OpenStreetMap contributors (ODbL) — basemap data where used, attributed on screen.
- Open source libraries listed in §5, all MIT or Apache-2.0.

No Space Agency Partner data was used beyond NASA's own. No third-party dataset with a non-open licence is included.

---

## 7. Use of Super Intelligence (SI) — form field answer

Short, paste-ready answer for the dedicated SI field:

> Yes. We used SI in two ways.
>
> **(1) As a development tool.** Claude (Anthropic) assisted with frontend scaffolding, refactoring parts of the statistics and API code, generating test cases and editing the English copy. Every change was reviewed and run by a team member. This is recorded in `AI.md` in the repository.
>
> **(2) Inside the product.** A large language model turns computed values into a plain-language explanation. It does not compute, does not decide significance and cannot assign a cause. A validator compares every figure in its output against the source values; on any mismatch the text is discarded and a deterministic template is shown. The interface labels the paragraph as model-written.
>
> No image, audio or video in this project is SI-generated. All model output is attributed to the model, never to NASA, and no NASA branding appears alongside it.
