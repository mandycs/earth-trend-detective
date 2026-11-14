# Case file 04 — Rondônia, Brazilian Amazon (Brazil)

> Research dossier for **Earth Trend Detective** · NASA Space Apps Challenge 2026 · compiled 2026-11-14.
> Every number carries a bracketed source id that maps to the URL table in §10.
>
> **Labels:** **[P]** published / measured · **[E]** estimate, model or projection · **[press]** media reporting of official data · **(computed)** our own arithmetic on published values · **not found** = we looked and could not source it.

---

## 1. Pitch (EN — usable as `site.json` copy)

> Rondônia once held 208,000 km² of Amazon forest. It has cleared about a third of it, in a fishbone pattern that follows the roads. The forest that remains is measurably hotter: each 10 points of forest lost raise dry-season surface temperature by 0.71 K once you count the warming up to 100 km downwind. And then the plot twists — new clearing has fallen by about 90% since 2021.

**Verdict this case must land:** *it's us — and we can also show a human trend going the right way.* It is the case that proves the detector reports good news too.

---

## 2. Site

| Item | Value | Source |
|---|---|---|
| State | Rondônia, western Brazilian Amazon | [2] |
| Approx. centroid | 10.5 S, 63.5 W | (site location) |
| Suggested bbox (data pull) | lon −64.5 … −62.5 ; lat −11.0 … −9.0 (central Rondônia, Machadinho/Buritis frontier) | (our choice, approximate) |
| State area | **237,753.439 km²** (IBGE 2025) | [6] |
| Original forest cover | **208,000 km²** | [1] |
| Population (2022 census) | 1,581,196 | [6] |

---

## 3. The headline change (published numbers)

**Annual clear-cut rate, PRODES/INPE** [2] — the full series is in the source file; the shape is what matters:

| Year | Cleared (km²) | Type | Source |
|---|---|---|---|
| 1988 | 2,340 | [P] | [2] |
| 1995 (peak) | **4,730** | [P] | [2] |
| 2004 | 3,858 | [P] | [2] |
| 2010 (minimum) | 435 | [P] | [2] |
| 2019 | 1,257 | [P] | [2] |
| 2020 | 1,273 | [P] | [2] |
| 2021 | 1,673 | [P] | [2] |
| 2022 | 1,480 | [P] | [2] |
| 2023 | 867 | [P] | [2] |
| 2024 | 360 | [P] | [2] |
| 2025 | 229 | [P] | [2] |
| 2026 | **149** | **[E]** — INPE state estimate, not yet consolidated | [2], [3] |
| Cumulative 1988–2026 | **67,708 km²** | (computed sum of the series; matches INPE's accumulated figure, 13.37% of the Legal Amazon total) | [2], [7] |
| Cumulative as share of the state | **28.5%** | (computed from [2] and [6]) | [2], [6] |
| Cumulative as share of original forest | **32.6%** (lower bound — PRODES series starts in 1988 and excludes earlier clearing) | (computed from [2] and [1]) | [1], [2] |
| Change 2021 → 2026 | **−91%** | (computed from [2]) | [2] |

**Context, so the Rondônia numbers are not read as an Amazon-wide claim:** INPE's estimate for the whole Legal Amazon in 2026 is **3,335 km²**, with Rondônia contributing **149 km² (4.5%)** — down from being one of the top three deforesting states for most of the record [3].

**The historical arc, from NASA's own long-term series** [1]:

| Year | Cumulative cleared | Type | Source |
|---|---|---|---|
| 1978 | 4,200 km² | [P] | [1] |
| 1988 | 30,000 km² | [P] | [1] |
| 1998 | 53,300 km² | [P] | [1] |
| 2003 | 67,764 km² | [P] | [1] |

**Read the two sources carefully.** NASA's 2003 cumulative figure (67,764 km²) and INPE's 1988–2026 sum (67,708 km²) are almost identical numbers with different meanings — NASA's counts clearing from the 1970s, INPE's starts in 1988. They are **not** a consistent time series and must not be plotted on the same axis. This is exactly the kind of trap the app should flag rather than smooth over.

---

## 4. Is the change statistically real?

- A published Mann–Kendall / Sen test on Rondônia's annual PRODES rate: **not found.** What is published is the full annual series [2] and the state estimate methodology [3].
- The series is **not monotone** and that is the interesting part: peak 1995 (4,730 km²), collapse to 435 km² in 2010, rebound to 1,673 km² in 2021, collapse again to 149 km² (est.) in 2026 [2]. A MK test over 1988–2026 will be dominated by which end you pick — this is the textbook case for our "period dependence" warning.
- Published quantitative trend claim we *can* use: the 2001–2020 dry-season land-surface-temperature relationship with forest loss, quantified below [4].

**Design consequence for our product:** Rondônia is the case where we must show the **Sen slope over a stated window** plus the raw series, and refuse to print a single "trend" number without the window. If we get that right on stage, it is more convincing than any p-value.

---

## 5. Climate vs not-climate: what the literature separates

| Claim | Number / statement | Type | Source |
|---|---|---|---|
| Local warming per 10 percentage points of forest loss | **0.16 K** | [P] | [4] |
| Warming per 10 pp of forest loss **including non-local effects up to 100 km away** | **0.71 K** — a factor of **>4** | [P] | [4] |
| Distance over which deforestation warms the surface | up to **100 km** | [P] | [4] |
| Period and variable | dry-season land-surface temperature, **2001–2020**, remote sensing | [P] | [4] |
| Potential reduction in future warming in the southern Amazon from cutting deforestation | **0.56 °C** | [P] | [4] |
| Modelled dry-season warming across Mato Grosso, 2020–2050, strong-inequality scenario | 0.96 K | [P] | [4] |
| Rainfall effect of deforesting protected areas | dry-season rainfall **down up to 30%** in the existing agricultural region | [P] | [5] |
| Land-use driver of the clearing | cattle pasture and crops along legal and illegal roads; fishbone pattern collapsing into pasture | [P] | [1] |

**Why this is a clean "us" case.** The 0.71 K per 10 pp is a *land-surface* temperature response measured against forest-loss gradients, not a global climate-model attribution. It is the closest thing in this set to a controlled experiment: same climate zone, different amount of forest left [4]. Nothing in the global-warming signal can produce a 4× amplification that tracks the fishbone pattern of roads [1].

**The nuance that makes it honest.** Deforestation rates in Rondônia are driven by policy and enforcement, not by rainfall. The 2010 collapse and the 2023–2026 collapse are political and economic events, not climatic ones [2]. So the case has **two** non-climatic signals: the land-cover change itself, and the policy that turned it off. Our app should say that out loud — it is a rare chance to show a human trend moving in the right direction.

---

## 6. NASA data available for this site

| Variable | NASA product | Resolution / cadence | Period | Access |
|---|---|---|---|---|
| Vegetation index (the workhorse here) | MODIS MOD13Q1 NDVI / EVI | **250 m**, 16-day | 2000–present | LP DAAC [8] |
| Land surface temperature | MODIS MOD11A2 | 1 km, 8-day | 2000–present | LP DAAC [9] |
| Forest clearing at field scale | Landsat 5/7/8/9 | 30 m, 16-day | 1984–present | Earthdata [10] |
| Precipitation | GPM IMERG | 0.1°, 30-min | 2000–present | gpm.nasa.gov [11] |
| Evapotranspiration | MODIS MOD16A2 | 500 m, 8-day | 2000–present | LP DAAC [12] |
| Soil moisture | SMAP L4 | 9 km | 2015–present | smap.jpl.nasa.gov [13] |
| Total water storage (basin context) | GRACE/GRACE-FO | monthly, ~300 km | 2002–present | grace.jpl.nasa.gov [14] |
| Climate drivers | NASA POWER | 0.5°, daily | 1981–present | power.larc.nasa.gov [15] |

**Honesty requirement.** The official deforestation rate is **INPE/PRODES, a Brazilian programme — not NASA** [2][3]. NASA supplies the 250 m vegetation and 1 km temperature record that lets us see the *effect* of clearing on the land surface [8][9], and the Landsat imagery that shows the fishbone pattern [1]. Never label PRODES as NASA data.

**Why this site is the best NASA-data case in the set:** MODIS NDVI at 250 m is fine enough to resolve a single large clearing, and the 2000–2026 record is continuous and free. If the jury asks "where does NASA actually carry the analysis?", this is the case to point at.

---

## 7. What our pipeline would compute here

1. **Target series:** MODIS NDVI (dry-season mean, June–September), 2000–2026, per pixel and aggregated over the frontier box.
2. **Drivers:** IMERG dry-season rainfall, POWER temperature, GLDAS soil moisture.
3. **Residual:** NDVI ~ rainfall + temperature → MK on the residual, per pixel. The expected map is a negative residual over cleared land and near-zero over intact forest — a spatial fingerprint, not just a number.
4. **Second variable:** MOD11A2 dry-season LST, 2001–2026. Expect a positive Sen slope over the frontier and compare its magnitude with the published 0.71 K per 10 pp [4].
5. **Cross-check:** overlay the PRODES clearing mask [2]. If the residual NDVI decline is where the mask says the clearing is, the pipeline works.

---

## 8. Story beats (five screens)

1. **The fishbone.** Landsat, 1975 vs 2024: roads first, then the ribs of cleared land [1].
2. **A third of a state.** 67,708 km² cleared since 1988 [2]; 208,000 km² to begin with [1].
3. **The heat that stays.** +0.71 K per 10 pp of forest loss, up to 100 km away [4].
4. **The plot twist.** From 1,673 km² (2021) to 149 km² (2026 estimate) — a 91% fall [2].
5. **Verdict.** "Real? Yes. The climate? No — this is land use. And the last four years are a human trend in the right direction."

---

## 9. Caveats we should say before the jury does

- **2026 is an estimate**, published as "Estimativa da Taxa Estadual", not a consolidated rate [2][3]. Label it in the UI or leave it out of the trend fit.
- **PRODES measures clear-cut only.** It does not capture degradation, selective logging or fire [3]. A "forest intact" pixel in PRODES can be a burnt, thinned forest.
- **Cloud cover** in the wet season makes MODIS composites unreliable from December to April; use dry-season means and say so.
- **Drought years contaminate NDVI.** The 2005, 2010 and 2015–16 El Niño droughts brown the forest without any clearing. That is precisely what the residual regression is for.
- **The recent decline is policy, not climate.** Do not let the LLM narrate it as an environmental recovery — the forest that was cleared is still cleared.
- **Do not mix NASA's cumulative (from the 1970s) with INPE's (from 1988)**, as explained in §3.

---

## 10. Sources

| # | Source | Type | URL | Used for |
|---|---|---|---|---|
| 1 | NASA Earth Observatory — "World of Change: Amazon Deforestation" (Rondônia) | Agency article + MODIS/Landsat series | https://earthobservatory.nasa.gov/world-of-change/Deforestation | 208,000 km² original forest; 4,200 / 30,000 / 53,300 / 67,764 km² cumulative; fishbone pattern |
| 2 | INPE / TerraBrasilis — PRODES Legal Amazon deforestation rates, state series (rates2026.json, accessed 2026-11-14) | Official Brazilian monitoring data | https://terrabrasilis.dpi.inpe.br/app/prodes/dashboard/deforestation/files/rates2026.json?v=3.5.10 | full annual series 1988–2026 for Rondônia; 67,708 km² accumulated |
| 3 | INPE — "Apresentação coletiva PRODES 2026" (PDF, state estimates) | Official agency presentation | https://www.gov.br/inpe/pt-br/assuntos/ultimas-noticias/brasil-alcanca-menores-taxas-de-desmatamento-da-serie-historica-na-amazonia-e-no-cerrado/ApresentacaoColetivaPRODES2026_INPE.pdf | Rondônia 149 km² (4.5%) estimate; Legal Amazon 3,335 km² |
| 4 | Butt et al. (2023), *PNAS* 120(45) e2309123120 — "Amazon deforestation causes strong regional warming" | Peer-reviewed | https://pmc.ncbi.nlm.nih.gov/articles/PMC10636322 | 0.16 K → 0.71 K per 10 pp; 100 km; 2001–2020; 0.56 °C; 0.96 K scenario |
| 5 | De Sales et al. (2020), *JGR Atmospheres* — "Impacts of Protected Area Deforestation on Dry-Season Regional Climate in the Brazilian Amazon" | Peer-reviewed | https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2020JD033048 | dry-season rainfall down up to 30% in the agricultural region |
| 6 | IBGE — Cidades e Estados: Rondônia | Official statistics | https://www.ibge.gov.br/cidades-e-estados/ro.html | state area 237,753.439 km²; population 1,581,196 (2022) |
| 7 | TerraBrasilis — PRODES deforestation dashboard (rates view) | Official dashboard | https://terrabrasilis.dpi.inpe.br/app/dashboard/deforestation/biomes/legal_amazon/rates | accumulated 67,708 km² (13.37% of Legal Amazon total); per-year series display |
| 8 | NASA LP DAAC — MOD13Q1 | Data product | https://lpdaac.usgs.gov/products/mod13q1v061/ | 250 m NDVI/EVI, 16-day |
| 9 | NASA LP DAAC — MOD11A2 | Data product | https://lpdaac.usgs.gov/products/mod11a2v061/ | 1 km LST, 8-day |
| 10 | NASA Earthdata | Data portal | https://www.earthdata.nasa.gov/ | Landsat access |
| 11 | NASA GPM — IMERG | Data product | https://gpm.nasa.gov/data/imerg | precipitation |
| 12 | NASA LP DAAC — MOD16A2 | Data product | https://lpdaac.usgs.gov/products/mod16a2v061/ | evapotranspiration |
| 13 | NASA SMAP | Mission | https://smap.jpl.nasa.gov/ | soil moisture |
| 14 | NASA/JPL GRACE | Mission | https://grace.jpl.nasa.gov/ | total water storage |
| 15 | NASA POWER | Data portal | https://power.larc.nasa.gov/ | climate drivers |
