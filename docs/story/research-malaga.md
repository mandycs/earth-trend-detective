# Case file 05 — Málaga / Axarquía water system (Spain)

> Research dossier for **Earth Trend Detective** · NASA Space Apps Challenge 2026 · compiled 2026-11-14.
> Every number carries a bracketed source id that maps to the URL table in §10.
>
> **Labels:** **[P]** published / measured · **[E]** estimate, model or projection · **[press]** media reporting of official data · **(computed)** our own arithmetic on published values · **not found** = we looked and could not source it.

---

## 1. Pitch (EN — usable as `site.json` copy)

> Málaga's reservoirs went from 17% to 96% in eighteen months. Was that a drought — or a demand problem that a wet winter papered over? The science says both: two severe droughts hit a system that was already taking 90 hm³ a year for irrigation against 79 hm³ of rights. In 2024 the Axarquía's only reservoir fell below its 8% outlet threshold. In 2026 it is full again. The trend is in the demand, not in the rain.

**Verdict this case must land:** *us, amplified by drought — and the drought just ended, which is the most interesting part.*

---

## 2. Site

| Item | Value | Source |
|---|---|---|
| Region | Axarquía (eastern Málaga province) + Guadalhorce-Limonero system (Málaga city) | [1], [4] |
| Approx. centroid (La Viñuela) | 36.87 N, −4.18 W | (site location) |
| Suggested bbox (data pull) | lon −4.45 … −3.85 ; lat 36.65 … 36.95 | (our choice, approximate) |
| Main reservoir | La Viñuela — the Axarquía's only reservoir | [4] |
| La Viñuela capacity | ≈165 hm³ (press, 2026); the same article reports 141 hm³ as 85.45% | [press] [6] |
| Province regulated capacity | 616 hm³ across the province's reservoirs | [press] [6] |
| Provincial reservoirs | La Viñuela, Guadalhorce, Guadalteba, Conde de Guadalhorce, Casasola, El Limonero, La Concepción | [press] [5] |

---

## 3. The headline change (published numbers)

**The crash (2022–2024)** — all figures from the Andalusian water agency SAIH Hidrosur as reported by the press:

| Metric | Value | Date | Type | Source |
|---|---|---|---|---|
| Guadalhorce reservoir | **11.6 hm³ = 9.2%** — new record low (previous 11.9 hm³, Sept 2008) | 24 Sep 2024 | [press] | [5] |
| Guadalhorce a year earlier | 28.3 hm³ | Sep 2023 | [press] | [5] |
| La Viñuela | **12.2 hm³ = 7%** — record low | 15 Jan 2024 | [press] | [5] |
| Province total (7 reservoirs) | **104.9 hm³ = 17.1%** | 24 Sep 2024 | [press] | [5] |
| Axarquía reservoir level vs outlet threshold | **below the 8% outlet threshold** | 2024 | [P] | [1] |
| Main aquifer | groundwater "dropped to sea level in several locations, risking seawater intrusion" | 2024 | [P] | [1] |
| Restrictions | 200 L/person/day in the Axarquía; later a 20% cut in urban supply | Oct 2022 / 2023 | [press] | [7] |

**The recovery (2025–2026):**

| Metric | Value | Date | Type | Source |
|---|---|---|---|---|
| Province total | **576.95 hm³ = 95.66%** | 23 Apr 2026 | [press] | [7] |
| La Viñuela | 152.11 hm³ = 92.54% | 23 Apr 2026 | [press] | [7] |
| Guadalteba | 152.03 hm³ = 99.17% | 23 Apr 2026 | [press] | [7] |
| Drought status | emergency decree lifted, "normalidad hidrológica" published in the BOJA | 23 Apr 2026 | [press] | [7] |
| Province total | **494 hm³ = 80.19%** of 616 hm³ (262 hm³ / 42.53% a year earlier) | 21 Sep 2026 | [press] | [6] |
| La Viñuela | **141 hm³ = 85.45%** of 165 hm³ (24 hm³ / 14.54% a year earlier) | 21 Sep 2026 | [press] | [6] |
| Guadalhorce–Guadalteba system | 255 hm³ = 91.40% of 279 hm³ | 21 Sep 2026 | [press] | [6] |

**This is the case's defining fact, and it is uncomfortable:** the same reservoirs that were at 17% in September 2024 were at 96% in April 2026 [5][7]. Any product that points at a Málaga reservoir and says "it is emptying" will be *wrong* in front of a local jury in November 2026. That is not a reason to drop the case — it is the reason the case is interesting.

---

## 4. Is the change statistically real?

| Question | Answer | Type | Source |
|---|---|---|---|
| Is Spain warming? | **+1.75 °C between 1961 and 2025**, statistically significant | [P] | [2] |
| Is rainfall declining? | Yes, and **statistically significant in eastern Andalucía** between 1961 and 2025 (one of the few Spanish regions where the decline is significant) | [P] | [2] |
| Is there a published MK/Sen trend on La Viñuela storage? | **not found** | — | — |
| Would a Sen slope on 2015–2026 storage be meaningful? | **No** — it would be dominated by the 2026 refill and by the start date. The honest output is "no trend detectable in this window" | (our analysis) | — |
| Is the *demand* trend real? | Published: "an increasing trend in dam water use for irrigation in 2000–2022 associated with increasing irrigated area" | [P] | [1] |

**The methodological lesson this case teaches** (and the reason to keep it in the product): a dramatic episode is not a trend. 2022–2024 looked like a collapse; 2026 looks like abundance. A trend detector that cannot tell those apart is a random-number generator with a colour scheme. Málaga is the case where our app has to say *"can't tell yet"* — and the challenge statement explicitly rewards that.

---

## 5. Climate vs not-climate: what the literature separates

| Claim | Number / statement | Type | Source |
|---|---|---|---|
| Immediate cause of the 2019–2024 crisis | "two severe meteorological droughts in close succession" | [P] | [1] |
| Immediate vs underlying cause, stated explicitly | "an unusual meteorological drought was the immediate cause … but the underlying cause was a chronic and structural long-term imbalance between water demand and resources" | [P] | [3] |
| Underlying cause | "a long-term structural imbalance between water demand and availability attributable to governance shortcomings" | [P] | [1] |
| Governance failures listed | underestimation of availability and extraction; increase in demand; ineffective control measures; lack of integrated land and water management | [P] | [1] |
| Irrigation demand vs allocated rights | **90 hm³/yr estimated demand vs 79 hm³/yr allocated** for 2022–2027 | [P] | [4] |
| Distribution-network losses | **above 24%** | [P] | [4] |
| Demand drivers | population growth, tourism on the Costa del Sol, expansion of irrigated export subtropical crops (avocado, mango) | [P] | [4] |
| Emergency measures | "delayed dam depletion but likely exacerbated groundwater extraction" | [P] | [1] |
| Planning inconsistency | "important inconsistencies within and between plans" since 1998; "aquifer overdraft even during nondrought periods" | [P] | [1] |
| Regional warming | +1.75 °C (Spain, 1961–2025) | [P] | [2] |
| Regional rainfall | significant decline in eastern Andalucía, 1961–2025 | [P] | [2] |

**The clean two-layer attribution, in the authors' own words:** the drought was the trigger; the imbalance was the cause. That is *exactly* the narrative our residual is meant to expose, and it is published, peer-reviewed, and about Málaga [1]. A local jury does not need to be told why Doñana matters; they need to be told why their own reservoir ran dry.

**Computed reality check (ours, indicative).** 90 hm³ of estimated irrigation demand against 79 hm³ of rights is a **14% overshoot** before any drought [4]; network losses above 24% add roughly another quarter of urban supply [4]. Neither number depends on rainfall. That is the "us" part, quantified.

---

## 6. NASA data available for this site

| Variable | NASA product | Resolution / cadence | Period | Access |
|---|---|---|---|---|
| Precipitation, temperature, radiation, wind | **NASA POWER** | 0.5° × 0.625°, daily | 1981–present | power.larc.nasa.gov [8] |
| Vegetation index (irrigated area, crop phenology) | MODIS MOD13Q1 | 250 m, 16-day | 2000–present | LP DAAC [9] |
| Land surface temperature | MODIS MOD11A2 | 1 km, 8-day | 2000–present | LP DAAC [10] |
| Evapotranspiration (the actual water use of the orchards) | MODIS MOD16A2 | 500 m, 8-day | 2000–present | LP DAAC [11] |
| Soil moisture | SMAP L4 | 9 km | 2015–present | smap.jpl.nasa.gov [12] |
| Reservoir surface area | Landsat 8/9 + Sentinel-2 | 30 m / 10 m | 2013–present (Landsat 1984–) | Earthdata [13] |
| Total water storage (regional only) | GRACE/GRACE-FO | monthly, ~300 km | 2002–present | grace.jpl.nasa.gov [14] |

**Be blunt about the limits.** GRACE's ~300 km footprint is far too coarse to resolve La Viñuela (165 hm³) or the Axarquía aquifer; for a site this small, GRACE gives regional context and nothing more. No published GRACE validation specific to this reservoir was found (**not found**). The reservoir *level* is **SAIH Hidrosur (Junta de Andalucía), not a NASA product** [5][6] — the same honesty rule as Lake Mead, and here it matters more, because the dramatic number on screen is not ours.

**What NASA genuinely adds here:** 45 years of daily precipitation and temperature at 0.5° (POWER) to test whether the rainfall trend explains the reservoir, plus MODIS evapotranspiration at 500 m to estimate what the avocado and mango orchards actually consume. That is the residual.

---

## 7. What our pipeline would compute here

1. **Target series:** La Viñuela storage (% of capacity) — **non-NASA, SAIH** — 2010–2026, plus Landsat/Sentinel-2 surface area as an independent check.
2. **Drivers:** POWER water-year precipitation and summer temperature over the catchment; IMERG as a second rainfall estimate.
3. **Residual:** storage ~ precipitation + temperature. Expect a large negative residual for 2021–2024 that **does not** persist into 2026 — the residual is an episode, not a trend.
4. **Second target (the real trend):** MODIS ET / irrigated-area change 2000–2026, or simply the published irrigated-area series [1][4]. Expect a positive trend that is independent of rainfall.
5. **Output language:** for storage → "can't tell yet (episode)"; for irrigated demand → "real, and not explained by climate". Showing both on one screen is the best demo of the product's honesty we can build.

---

## 8. Story beats (five screens)

1. **17%.** September 2024: the province's reservoirs at 104.9 hm³ [5]; Guadalhorce at a record 11.6 hm³ [5].
2. **The 8% threshold.** La Viñuela below the outlet threshold; the aquifer at sea level; seawater intrusion risk [1].
3. **90 vs 79.** Estimated irrigation demand against allocated rights, before the drought is counted [4].
4. **96%.** April 2026: the drought decree lifted [7]. "So was it the climate?" — "Two droughts, yes. But the system was already overdrawn."
5. **Verdict.** "The rain came back. The orchards didn't shrink." (Our copy — the land-use fact is [1], the phrasing is ours.)

---

## 9. Caveats we should say before the jury does

- **The signal reversed.** Storage is not a trend in this window [5][6][7]. If the deck shows the 2022–2024 collapse without the 2026 refill, a local judge will (rightly) stop listening.
- **The headline numbers are not NASA.** SAIH Hidrosur is the Junta de Andalucía's network [5][6]. Attribute it on screen.
- **GRACE cannot see this.** ~300 km resolution vs a 165 hm³ reservoir [14]. Do not pretend otherwise; the Lake Mead case has the same rule.
- **Drought and demand are not independent.** Emergency measures "likely exacerbated groundwater extraction" [1]; the residual is a joint effect, not a clean human fingerprint.
- **Press-sourced reservoir figures** are second-hand reports of official SAIH data [5][6][7]. For the final build, pull SAIH directly (https://www.redhidrosurmedioambiente.es/saih/ [15]) and label the series "SAIH Hidrosur (Junta de Andalucía)".
- **Tourism and agriculture are both drivers** [4]; a story that blames only avocado farmers is incomplete and politically loaded.

---

## 10. Sources

| # | Source | Type | URL | Used for |
|---|---|---|---|---|
| 1 | Junquera, Hormaza, Rubenstein, Levin, Vadillo Pérez & Jiménez Gavilán (2025), *PNAS* 122(39) e2508055122 — "Severe water crisis in southern Spain under expanding irrigated agriculture: A multidimensional drought analysis" | Peer-reviewed | https://europepmc.org/article/MED/40986348 | 2019–2024 crisis, 8% outlet threshold, aquifer to sea level, irrigation trend 2000–2022, governance framing |
| 2 | AEMET — "Informe sobre el estado del clima de España 2025. Resumen ejecutivo" (PDF) | Official agency report | https://www.aemet.es/documentos/es/conocermas/recursos_en_linea/publicaciones_y_estudios/publicaciones/Informes_estado_clima/IECLI2025_ResumenEjecutivo.pdf | +1.75 °C 1961–2025; significant rainfall decline in eastern Andalucía; 2025 wet year |
| 3 | Junquera et al. (2024), arXiv:2408.00683 — "Hydrological collapse in southern Spain under expanding irrigated agriculture" (preprint of [1]) | Preprint | https://arxiv.org/abs/2408.00683 | immediate (meteorological) vs underlying (structural) cause; governance shortcomings |
| 4 | Hurtado et al. (2024), *Science of the Total Environment* — "The paradox of success: Water resources closure in Axarquia (southern Spain)" | Peer-reviewed | https://www.sciencedirect.com/science/article/pii/S0048969724044668 | 90 vs 79 hm³/yr; network losses >24%; population/tourism/subtropical crops; DPSIR |
| 5 | El Español (Málaga), 25 Sep 2024 — "Situación crítica en el pantano de Guadalhorce: nuevo mínimo histórico con 11,6 hm³" (citing Red Hidrosur) | Press (official data) | https://www.elespanol.com/malaga/20240925/situacion-critica-pantano-guadalhorce-registra-nuevo-minimo-historico-hectometros/888411651_0.html | Guadalhorce 11.6 hm³ / 9.2%; previous 11.9 hm³ (2008); La Viñuela 12.2 hm³ / 7%; province 104.9 hm³ / 17.1% |
| 6 | Málaga Hoy, 22 Sep 2026 — "Los embalses de Málaga acaban el verano al 80%…" (citing SAIH Hidrosur, 21 Sep 2026) | Press (official data) | https://malagahoy.es/provincia/embalses-malaga-acaban-verano-80-capacidad-aseguran-agua-mas-dos-anos_0_2008034475.html | 494/616 hm³ = 80.19%; La Viñuela 141/165 = 85.45%; Guadalhorce-Guadalteba 255/279 |
| 7 | El Español (Málaga), 24 Apr 2026 — "De los embalses secos a rozar el lleno: la Junta entierra la sequía…" | Press (official data, BOJA) | https://www.elespanol.com/malaga/20260424/embalses-secos-rozar-lleno-junta-entierra-sequia-malaga-pantanos/1003744218764_0.html | 576.95 hm³ / 95.66%; La Viñuela 152.11 hm³ / 92.54%; decree; 2022–2023 restrictions |
| 8 | NASA POWER | Data portal | https://power.larc.nasa.gov/ | 0.5° daily climate drivers, 1981– |
| 9 | NASA LP DAAC — MOD13Q1 | Data product | https://lpdaac.usgs.gov/products/mod13q1v061/ | 250 m NDVI/EVI |
| 10 | NASA LP DAAC — MOD11A2 | Data product | https://lpdaac.usgs.gov/products/mod11a2v061/ | 1 km LST |
| 11 | NASA LP DAAC — MOD16A2 | Data product | https://lpdaac.usgs.gov/products/mod16a2v061/ | 500 m evapotranspiration |
| 12 | NASA SMAP | Mission | https://smap.jpl.nasa.gov/ | soil moisture |
| 13 | NASA Earthdata | Data portal | https://www.earthdata.nasa.gov/ | Landsat access |
| 14 | NASA/JPL GRACE | Mission | https://grace.jpl.nasa.gov/ | TWS at ~300 km — regional context only |
| 15 | Red Hidrosur / SAIH, Junta de Andalucía | Official operational network | https://www.redhidrosurmedioambiente.es/saih/ | primary source for reservoir levels (to be pulled directly in the build) |
