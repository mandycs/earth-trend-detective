# Case file 03 — Doñana National Park / Almonte-Marismas aquifer (Spain)

> Research dossier for **Earth Trend Detective** · NASA Space Apps Challenge 2026 · compiled 2026-11-14.
> Every number carries a bracketed source id that maps to the URL table in §10.
>
> **Labels:** **[P]** published / measured · **[E]** estimate, model or projection · **[press]** media reporting of official data · **(computed)** our own arithmetic on published values · **not found** = we looked and could not source it.

---

## 1. Pitch (EN — usable as `site.json` copy)

> Doñana is Europe's most important wetland, and its ponds are disappearing. Rain and temperature decide how much a pond floods — but 83% of the park's ponds now flood less than the climate alone would allow. The missing water is being pumped out from under them, for strawberries and for a beach resort. Thirty-four years of Landsat make the case visible pond by pond.

**Verdict this case must land:** *mostly us, amplified by drought.* Same family as Lake Mead, but the evidence is finer-grained and it is 2.5 hours from Málaga.

---

## 2. Site

| Item | Value | Source |
|---|---|---|
| Protected area | Doñana Natural Space, including Doñana National Park (created 1969) and Natural Park | [3] |
| Total surface of the Natural Space | **1,225 km²** | [3] |
| Approx. centroid | 36.99 N, −6.44 W | (site location) |
| Suggested bbox (data pull) | lon −6.60 … −6.25 ; lat 36.85 … 37.15 | (our choice, approximate) |
| Designations | UNESCO World Heritage Site, Biosphere Reserve, Ramsar wetland, Natura 2000 | [3], [5] |
| Aquifer | Almonte-Marismas, divided into 6 groundwater bodies across 2 hydrographic districts | [3] |
| Aquifer footprint vs protected area | **about 5× larger** than the park | [2] |
| Wintering waterfowl | more than 500,000 birds each year; 5 threatened bird species | [8] |

**Why the footprint matters:** the park is protected; the aquifer that feeds it is not. That single sentence is the whole case.

---

## 3. The headline change (published numbers)

| Metric | Value | Period | Type | Source |
|---|---|---|---|---|
| Landsat images analysed | **442** | 1985–2018 | [P] | [1] |
| Ponds analysed | **316** | 1985–2018 | [P] | [1] |
| Ponds desiccated ("currently desiccated" at end of study) | **59%** (≈186 of 316, computed) | to 2018 | [P] | [1] |
| Ponds that "have not flooded since at least 2013" | **59%** | to 2018 | [P] | [2] |
| Ponds flooding less extensively and for less time **than climate explains** | **83%** (≈262 of 316, computed) | 1985–2018 | [P] | [2] |
| Ponds flooding **more** than climate explains | **8 ponds**, in the north of the park | 1985–2018 | [P] | [2] |
| Groundwater drawdown, deep aquifer | **up to 20 m** | since the 1970s | [P] | [4] |
| Water-table lowering, phreatic level | **0.5 – 2 m** in some areas | — | [P] | [4] |
| Summer groundwater users at Matalascañas | **~100,000 people** | current | [P] | [4] |
| Wetland-dependent species in the park | **>600** | — | [P] | [1] |

**The Santa Olalla sequence** — the emotional hook, and it must be told precisely [6][7]:

| Year | Event | Type | Source |
|---|---|---|---|
| 1983 | Santa Olalla (largest permanent lagoon, last to hold water in August) dries | [P] | [6] |
| 1995 | Dries again | [P] | [6] |
| 2022 | Dries for the **third time since records began**; reduced to "a small puddle at its centre" | [P] | [6] |
| 2023 | Dries for the **second consecutive year** — unprecedented in the record | [P] | [7] |
| 2024 | Dries for the **third consecutive year** | [P] | [7] |

Before 2022 the lagoon had dried twice in ~50 years of records. It then dried three years running. That comparison — *twice in fifty years, then three years in a row* — is the cleanest public statement of the case, and every element of it is sourced.

---

## 4. Is the change statistically real?

This is the strongest statistical case in the set, because the published study is explicitly a **climate-vs-not-climate attribution design**, not just a trend:

| Element of the published method | Detail | Source |
|---|---|---|
| Data | 442 Landsat images, 316 ponds, 1985–2018 | [1] |
| Response variable | date of desiccation and maximum flooded area per pond | [1] |
| Climate covariates | inter-annual variation in **rainfall and temperature** — found to be "the most important factors determining pond flooding" | [1] |
| Anthropogenic covariates | intensive agriculture and the nearby tourist resort | [1] |
| Model | Generalized Additive Mixed Models (GAMMs) | [1] |
| Key result | "the strongest negative flooding anomalies (i.e. ponds flooding less than explained by climate alone) were located in proximity to pumping areas" | [1] |

That last sentence is, in effect, the RESTREND logic our product automates — residual of flooding after climate, mapped in space, and it lands on the wells. **Use this paper as the methodological precedent for the whole app.**

- A published Mann–Kendall / Sen slope per pond: **not found** (the authors used GAMMs, not MK). We can compute MK/Sen ourselves on the same Landsat series and present it as *our* analysis, clearly labelled.
- The 83% figure is reported by NASA's Earth Observatory summary of the study [2]; the paper's own abstract reports 59% desiccated and the anomaly-near-pumping result [1]. Cite each to its own source.

---

## 5. Climate vs not-climate: what the literature separates

| Claim | Number / statement | Type | Source |
|---|---|---|---|
| Rainfall and temperature are the dominant *inter-annual* drivers of pond flooding | "the most important factors determining pond flooding" | [P] | [1] |
| Anthropogenic signal | agriculture and the tourist resort "related to the desiccation or shrinking of ponds all over Doñana" | [P] | [1] |
| Spatial fingerprint | strongest negative anomalies **next to pumping areas** | [P] | [1] |
| Share of ponds beyond climate | 83% | [P] | [2] |
| Deep-aquifer drawdown | up to 20 m | [P] | [4] |
| Vertical hydraulic gradient | "inverted the formerly ascending vertical hydraulic gradient in discharge areas" | [P] | [4] |
| Scientific disagreement on magnitude | Acreman et al. reported drawdown "up to 10 m" and questioned impacts on the marsh; Green et al. reply that drawdowns are "actually up to 20 m" and that impacts are documented | [P] | [4], [5] |
| Scale of the evidence review | 374 publications screened, **87** with quantitative eco-hydrological evidence | [P] | [5] |
| Legal finding | CJEU, Case C-559/19 (24 Jun 2021): Spain failed its obligations on Doñana's groundwater bodies and habitats; the Court found "excessive water abstraction for urban supply for the tourist area of Matalascañas has caused significant disturbance to the protected habitats" | [P] | [9] |
| Non-climatic pressure | abstraction for red fruit, rice and urban supply remains the dominant pressure in the 2024 review, which calls for it to be "urgently reduced" | [P] | [4] |

**How to present the disagreement.** Do not hide it — it is a feature. The two camps agree that abstraction is a driver and that the aquifer is depleted; they disagree on how much ecological damage is attributable, and on how many aquifer units behave independently [5]. For a "trend detective" product, the correct on-screen sentence is: *"scientists agree the water is being pumped faster than it refills; they still argue about how much damage that has done to each wetland."*

**Computed cross-check (ours, indicative):** the aquifer footprint is ~5× the protected area [2] and the deep aquifer has dropped up to 20 m [4]. A 20 m head loss over a 1,225 km² park implies a very large stored-volume deficit — which is why this is a *groundwater* story, not a rainfall story. Do not put a km³ number on screen without a storage-coefficient assumption we cannot source.

---

## 6. NASA data available for this site

| Variable | NASA product | Resolution / cadence | Period | Access |
|---|---|---|---|---|
| Pond extent & flooding duration | Landsat 5 TM / 7 ETM+ / 8 OLI / 9 | 30 m, 16-day | 1984–present | Earthdata [12] |
| Vegetation condition | MODIS MOD13Q1 NDVI | 250 m, 16-day | 2000–present | LP DAAC [10] |
| Land surface temperature | MODIS MOD11A2 | 1 km, 8-day | 2000–present | LP DAAC [13] |
| Evapotranspiration | MODIS MOD16A2 | 500 m, 8-day | 2000–present | LP DAAC [14] |
| Soil moisture | SMAP L4 | 9 km, 3-hourly | 2015–present | smap.jpl.nasa.gov [15] |
| Groundwater storage anomaly | GRACE/GRACE-FO **+ GLDAS-2.2** | monthly, ~300 km | 2002–present | grace.jpl.nasa.gov [11] |
| Precipitation | GPM IMERG | 0.1°, 30-min | 2000–present | gpm.nasa.gov [16] |
| Climate drivers | NASA POWER | 0.5° × 0.625°, daily | 1981–present | power.larc.nasa.gov [17] |

**This site has something almost no other case has: a peer-reviewed validation that GRACE-derived groundwater storage works at this specific aquifer.** Guardiola-Albert et al. (2024) derived groundwater storage anomalies from GRACE + GLDAS-2.2 for the Almonte-Marismas aquifer and validated them against piezometers and precipitation, reporting "strong agreement between GLDAS-2.2-derived GWS anomalies and in-situ measurements" and proposing the series as a calibration input for groundwater flow models [11]. That single paper removes the biggest objection a technical judge could raise ("GRACE is too coarse for a 1,225 km² site").

**And NASA has already told this story:** Earth Observatory's "Water Woes in Doñana National Park" (26 Jun 2023) walks through the 316-pond study with before/after imagery of the Zahillo pond [2]. Use it as the narrative spine and cite it.

---

## 7. What our pipeline would compute here

1. **Target series:** Landsat-derived flooded-area / water-presence per pond (or park-aggregated flooded area), annual dry-season, 1984–2026.
2. **Drivers:** IMERG rainfall (water year), POWER temperature, GLDAS soil moisture.
3. **Residual:** flooded area ~ rainfall + temperature → MK on the residual. Expect a significant negative residual concentrated near Matalascañas and the greenhouse belt — the spatial pattern *is* the evidence [1].
4. **Cross-check:** GRACE+GLDAS groundwater storage anomaly for the aquifer box, validated as in [11].
5. **Second variable for the sweep:** MODIS NDVI of the marsh (2000–2026). Expect a decline in flooding-dependent macrophyte greenness; if it does not appear, report that honestly rather than forcing it.

---

## 8. Story beats (five screens)

1. **The last permanent lagoon.** Santa Olalla, 2011 vs 2022 [2][6]; twice in fifty years, then three years running [6][7].
2. **316 ponds, 34 years.** What 442 Landsat images show when you stack them [1].
3. **The 83%.** Flooding that the rain and the heat cannot explain [2].
4. **The footprint.** A park of 1,225 km² sitting on an aquifer five times larger, with 100,000 summer users at Matalascañas and greenhouses on the western fringe [2][3][4].
5. **Verdict.** "Real? Yes — and the climate doesn't explain most of it."

---

## 9. Caveats we should say before the jury does

- **The key study ends in 2018** [1]. The 2022–2024 lagoon collapse is documented by CSIC bulletins [6][7], not by that paper. Do not merge the two into one series without saying so.
- **Wet years happen.** 2025 rainfall gave the peridunal lagoons a respite; a wet year does not undo a 34-year structural decline, and our UI must show the wet years rather than truncate at 2022.
- **The attribution is contested in detail** (Acreman vs Green on drawdown magnitude and ecological impact) [4][5]. Present the range, not one number.
- **Drought and pumping are coupled:** in dry years farmers pump more, so "climate" and "us" are not independent regressors. Any residual is a *joint* effect. This is the deepest methodological caveat in the whole project — say it.
- **Political sensitivity.** Irrigation rights around Doñana are a live Andalusian policy fight. Our copy must describe water-balance facts, never take a side on the proposed laws.
- **GRACE alone is coarse**; the credibility here rests on the GLDAS-2.2 downscaling being validated locally [11] — cite that, don't hand-wave it.

---

## 10. Sources

| # | Source | Type | URL | Used for |
|---|---|---|---|---|
| 1 | de Felipe, Aragonés & Díaz-Paniagua (2023), *Science of the Total Environment* — "Thirty-four years of Landsat monitoring reveal long-term effects of groundwater abstractions on a World Heritage Site wetland" | Peer-reviewed | https://doi.org/10.1016/j.scitotenv.2023.163329 | 442 images, 316 ponds, 1985–2018, 59%, GAMM design, anomalies near pumping, >600 species |
| 2 | NASA Earth Observatory — "Water Woes in Doñana National Park" (26 Jun 2023) | Agency article + Landsat imagery | https://science.nasa.gov/earth/earth-observatory/water-woes-in-donana-national-park-151492 | 83% beyond climate, 59% since 2013, 8 ponds wetter, 5× footprint, Zahillo imagery |
| 3 | Olías, Basallote, Cánovas & Pérez-Carral (2025), *Environmental Monitoring and Assessment* 197:526 | Peer-reviewed (open access) | https://pmc.ncbi.nlm.nih.gov/articles/PMC11982081/ | 1,225 km², park created 1969, 6 groundwater bodies, designations, pumping cone |
| 4 | Green et al. (2024), *Wetlands* — "Groundwater Abstraction has Caused Extensive Ecological Damage to the Doñana World Heritage Site, Spain" (repository PDF) | Peer-reviewed | https://ccamachosite.wordpress.com/wp-content/uploads/2024/01/2024-groundwater-abstraction-has-caused-extensive-ecological-damage-to-the-donana-world-heritage-site-wetlands-2023.pdf | 20 m drawdown, 0.5–2 m phreatic, 100,000 summer users, gradient inversion, reply to Acreman |
| 5 | Acreman & Salathé (2022), *Nature Ecology & Evolution* — "A complex story of groundwater abstraction and ecological threats to the Doñana National Park World Heritage Site" | Peer-reviewed correspondence | https://www.nature.com/articles/s41559-022-01836-6 | 374 publications / 87 quantitative, "up to 10 m", multiple aquifer units, contested reading |
| 6 | Estación Biológica de Doñana–CSIC — "Drought and overexploitation of aquifers dry up the last permanent lagoon…" (3 Sep 2022) | Research institute | https://www.ebd.csic.es/en/outreach/news/drought-and-overexploitation-aquifers-dry-last-permanent-lagoon-spains-donana | 2022 drying, 1983 and 1995 precedents, ten years below-average rainfall, rice area ÷3 |
| 7 | Estación Biológica de Doñana–CSIC — "Doñana loses its last permanent pond: Santa Olalla dries up for the third year in a row" | Research institute | https://www.ebd.csic.es/en/outreach/news/donana-loses-its-last-permanent-pond-santa-olalla-dries-third-year-row | 2023 second consecutive, 2024 third consecutive |
| 8 | UNESCO World Heritage Centre — Doñana National Park (ref. 685) | Official listing | https://whc.unesco.org/en/list/685/ | 500,000 wintering waterfowl, 5 threatened bird species, lagoon/marsh/dune description |
| 9 | Court of Justice of the European Union — Judgment, Case C-559/19, Commission v Spain (24 Jun 2021) | Court judgment | https://infocuria.curia.europa.eu/tabs/redirect/juris/document/document.jsf?docid=243362&doclang=EN&text | infringement; Matalascañas abstraction and protected habitats (¶137–138) |
| 10 | NASA LP DAAC — MOD13Q1 NDVI | Data product | https://lpdaac.usgs.gov/products/mod13q1v061/ | 250 m vegetation index |
| 11 | Guardiola-Albert et al. (2024), *Hydrogeology Journal* — "Enhancing groundwater management with GRACE-based groundwater estimates from GLDAS-2.2: a case study of the Almonte-Marismas aquifer" | Peer-reviewed (open access) | https://link.springer.com/10.1007/s10040-024-02838-3 | local validation of GRACE+GLDAS groundwater storage |
| 12 | NASA Earthdata | Data portal | https://www.earthdata.nasa.gov/ | Landsat access |
| 13 | NASA LP DAAC — MOD11A2 | Data product | https://lpdaac.usgs.gov/products/mod11a2v061/ | 1 km land surface temperature |
| 14 | NASA LP DAAC — MOD16A2 | Data product | https://lpdaac.usgs.gov/products/mod16a2v061/ | 500 m evapotranspiration |
| 15 | NASA SMAP | Mission | https://smap.jpl.nasa.gov/ | soil moisture |
| 16 | NASA GPM — IMERG | Data product | https://gpm.nasa.gov/data/imerg | precipitation |
| 17 | NASA POWER | Data portal | https://power.larc.nasa.gov/ | climate drivers |
