# Case file 02 — Great Aletsch Glacier, Valais (Switzerland)

> Research dossier for **Earth Trend Detective** · NASA Space Apps Challenge 2026 · compiled 2026-11-14.
> Every number carries a bracketed source id that maps to the URL table in §10.
>
> **Labels:** **[P]** published / measured · **[E]** estimate, model or projection · **[press]** media reporting of official data · **(computed)** our own arithmetic on published values · **not found** = we looked and could not source it.

---

## 1. Pitch (EN — usable as `site.json` copy)

> The largest glacier in the Alps has retreated 3.4 km since 1870 — and the rate is not constant: about 16 m a year before 1950, about 51 m a year in the 2000s. Switzerland has warmed 2.8 °C since pre-industrial times. Here, for once, the climate explains almost all of it.

**Verdict this case must land:** *it's the climate.* This is the control case — the one that proves the detector is not a machine for blaming humans.

---

## 2. Site

| Item | Value | Source |
|---|---|---|
| Glacier | Grosser Aletschgletscher (Great Aletsch Glacier), Valais, Switzerland | [1] |
| Approx. centroid (Konkordiaplatz) | 46.50 N, 8.03 E | (site location) |
| Suggested bbox (data pull) | lon 7.85 … 8.15 ; lat 46.35 … 46.60 | (our choice, approximate) |
| Length | 23.6 km (2011) | [1] |
| Area | 86.8 km² (1973) → 78.4 km² (2011) | [1] |
| Elevation range | 1,649 – 4,126 m (2011) | [1] |
| Status | largest ice mass in the Alps | [1], [6] |

---

## 3. The headline change (published numbers)

**Length (the tongue), measured every year since 1870 — 133 observations** [2]:

| Metric | Value | Type | Source |
|---|---|---|---|
| Cumulative length change, 1870–2024 | **−3,387.3 m** | (computed from [2]) | [2] |
| Mean rate quoted by the monitoring network | **−23.52 m/yr** (1870–2024 average) | [P] | [1] |
| 1900–1950 total | −779.0 m ≈ **−15.6 m/yr** | (computed from [2]) | [2] |
| 1950–2000 total | −1,359.4 m ≈ **−27.2 m/yr** | (computed from [2]) | [2] |
| 2000–2010 total | −507.8 m ≈ **−50.8 m/yr** | (computed from [2]) | [2] |
| 2010–2020 total | −358.6 m ≈ **−35.9 m/yr** | (computed from [2]) | [2] |
| 2020–2024 total | −122.5 m ≈ **−30.9 m/yr** | (computed from [2]) | [2] |

**The last ten measurements, so nobody can accuse us of hiding the noise** [2]:

| Period | Length change |
|---|---|
| 2014-08-22 → 2015-08-26 | −49.30 m |
| 2015-08-26 → 2016-08-08 | −49.50 m |
| 2016-08-08 → 2017-08-07 | −80.40 m |
| 2017-08-07 → 2018-09-27 | −62.80 m |
| 2018-09-27 → 2019-09-04 | **+5.50 m** |
| 2019-09-04 → 2020-09-14 | −9.00 m |
| 2020-09-14 → 2021-07-29 | −4.90 m |
| 2021-07-29 → 2022-07-13 | −17.10 m |
| 2022-07-13 → 2023-08-10 | −36.50 m |
| 2023-08-10 → 2024-08-30 | −64.00 m |

Note the **+5.50 m in 2019**: the tongue advanced in a single year while the glacier was still losing mass. Length is a lagged, noisy proxy — this is the caveat that makes the case teachable rather than simplistic.

**Mass balance (the physically meaningful variable)** [1]:

| Metric | Value | Type | Source |
|---|---|---|---|
| Mean mass balance, 1940–2025 | **−0.55 m water equivalent/yr** | [P] | [1] |
| Swiss glaciers, 2022 | **−6%** of national ice volume | [P] | [3] |
| Swiss glaciers, 2023 | **−4%** of national ice volume | [P] | [3] |
| Two-year total, 2022–2023 | **−10%** — as much ice as was lost between 1960 and 1990 | [P] | [3] |
| Swiss glaciers, hydrological year 2024/25 | **−1.6 m w.e. = −3.0%** of volume | [P] | [4] |
| Swiss volume lost since 2015 | **one quarter** | [P] | [4] |
| Aletsch, summer 2025: local ice loss at the lowest stake (1,980 m) | **~12 m** | [P] | [4] |
| Aletsch 2025 relative to the 2010–2020 mean | "moderately below" the mean (i.e. less severe than most Swiss glaciers) | [P] | [4] |

**Regional climate context** [5]:

| Metric | Value | Type | Source |
|---|---|---|---|
| Switzerland warming vs pre-industrial | **+2.8 °C** | [P] | [5] |

---

## 4. Is the change statistically real?

- A published Mann–Kendall test *on the Aletsch length series*: **not found.** What is published is 133 annual measurements with a monotone negative cumulative curve [2] and an official mean rate [1].
- The series is close to monotone by construction: of 133 intervals, the overwhelming majority are negative (the single positive year visible in the recent record is 2019, +5.5 m) [2]. A MK test on annual length change 1870–2024 would be dominated by the acceleration, not by sign flips; our pipeline should report **Sen slope on the cumulative curve** and MK on annual increments separately.
- Published significance language we can borrow: the monitoring network describes the acceleration as "dramatic" and states that as much ice was lost in two years as in the three decades 1960–1990 [3]. That is a quantitative comparison, not a p-value — do not dress it as one.

---

## 5. Climate vs not-climate: what the literature separates

This is the case where the separation is **physical and uncontested**, which is exactly why it is in the deck.

| Claim | Number / statement | Type | Source |
|---|---|---|---|
| What drives winter mass gain | snow accumulation, "determined by variations in solid precipitation" | [P] | [4] |
| What drives mass loss | "snow/firn/ice melt (determined by variations in air temperature and solar radiation)" | [P] | [4] |
| Why seasonal decomposition matters | it is what allows scientists "to disentangle the effects of snow accumulation … and snow/firn/ice melt" | [P] | [4] |
| Regional warming | +2.8 °C vs pre-industrial | [P] | [5] |
| Land-cover / land-use explanation at this site | **none identified** — no published study attributes Aletsch's retreat to local land use | not found | — |
| Non-climatic contributors (debris cover, glacier geometry, pro-glacial lake calving) | real in glaciology, but **not quantified for Aletsch in the sources we verified** | not found | — |

**The honest framing.** Alpine glacier retreat is the one case in this set where a competent glaciologist will say "it's the climate, essentially all of it". There is no competing land-use story at 3,000 m in the Bernese Alps. That is the point of including it: when our detector says "the climate does not explain this", the jury should believe it *because* we also show a case where the climate explains everything.

**Residual expectation for our app:** near zero. If our pipeline reports a large non-climatic residual at Aletsch, the pipeline is wrong, not the glacier. Use it as an internal unit test.

---

## 6. NASA data available for this site

| Variable | NASA product | Resolution / cadence | Period | Access |
|---|---|---|---|---|
| Glacier extent / length / width | Landsat 5 TM, 7 ETM+, 8/9 OLI | 30 m, 16-day | 1984–present | Earthdata [9] |
| Snow cover | MODIS MOD10A1 | 500 m, daily | 2000–present | NSIDC [7] |
| Surface elevation change / thinning | ICESat-2 ATL06 | along-track, ~70 cm range precision | 2018–present | icesat-2.gsfc.nasa.gov [10] |
| Topography / DEM | NASADEM (SRTM re-archive) | 30 m | 2000 baseline | LP DAAC [11] |
| Land surface temperature (context) | MODIS MOD11A2 | 1 km, 8-day | 2000–present | LP DAAC [12] |
| Climate drivers (T, precip) | NASA POWER | 0.5° × 0.625°, daily | 1981–present | power.larc.nasa.gov [8] |
| Regional precipitation | GPM IMERG | 0.1° | 2000–present | gpm.nasa.gov [13] |

**Imagery already published by NASA for this exact site:** a Landsat 5 (2 Sep 1984) vs Landsat 8 (6 Aug 2024) pair showing four decades of retreat and narrowing — free to reuse with credit, and the fastest possible way to make the 3D scene credible [6].

**Honesty requirement.** Length and mass-balance numbers are **GLAMOS/WGMS field measurements**, not satellite products [1][2][3][4]. NASA's contribution here is the *visual* record and the elevation-change record, plus the climate drivers. Say that plainly; the Swiss data is the gold standard and pretending otherwise would be silly.

---

## 7. What our pipeline would compute here

1. **Target series:** Landsat-derived glacier area (or snow-cover days from MOD10A1 as a proxy where cloud cover allows), annual, 1984–2026.
2. **Drivers:** POWER summer mean temperature (JJA), IMERG winter accumulation.
3. **Residual:** area ~ summer T + winter precip → MK on the residual. Expected: small residual, i.e. "the climate explains this".
4. **Cross-check:** compare the Landsat area loss with GLAMOS's measured cumulative −3,387 m [2]. If our independent estimate lands in the same order of magnitude, the pipeline is trustworthy.
5. **Teaching moment:** show the 2019 advance (+5.5 m) next to the 2019 mass balance. "One good year does not reverse a glacier."

---

## 8. Story beats (five screens)

1. **1870 → today.** 3.4 km of ice gone; the tongue now ends where the maps used to show ice [2].
2. **The acceleration.** ~16 m/yr before 1950, ~51 m/yr in the 2000s, ~31 m/yr in the last four years [2] (computed rates). Not a straight line — a step change.
3. **The two years that cost a tenth of a country's ice.** 2022 and 2023 [3].
4. **The 2.8 degrees.** Switzerland's warming, and the physical reason the ice responds to it [5].
5. **Verdict.** "Real? Yes. The climate? Yes — and this is what that looks like."

---

## 9. Caveats we should say before the jury does

- **Length ≠ mass.** The tongue can advance for a year (2019: +5.5 m) while the glacier loses mass [2]. Always show both.
- **Response time.** A glacier tongue integrates years to decades of mass balance (standard glaciology; **not sourced here** — label it as interpretation if used on screen).
- **The recent slowdown is not recovery.** 2020–2024 retreat (~31 m/yr) is slower than the 2000s (~51 m/yr) but the mass balance stayed strongly negative [4].
- **Aletsch is not representative of all glaciers.** In 2025 it was *less* severely affected than most Swiss glaciers because of its high accumulation area [4]. Say so — it is a good example of why single-site stories need context.
- **The −0.55 m w.e./yr figure is an 85-year mean** [1]; it hides the acceleration entirely.

---

## 10. Sources

| # | Source | Type | URL | Used for |
|---|---|---|---|---|
| 1 | WGMS — Grosser Aletschgletscher glacier profile (ID 360) | Official monitoring database | https://wgms.ch/data/glacier-profiles/360.html | length 23.6 km, area 86.8→78.4 km², −23.52 m/yr 1870–2024, −0.55 m w.e./yr 1940–2025 |
| 2 | GLAMOS — Swiss Glacier Length Change, release 2025 (CSV) | Official measurement series | https://doi.glamos.ch/data/lengthchange/lengthchange.csv | 133 annual observations 1870–2024; all cumulative/decadal figures computed from it |
| 3 | SCNAT / Swiss Commission for Cryosphere Observation — "Two catastrophic years obliterate 10% of Swiss glacier volume" (28 Sep 2023) | Official press release | https://www.scnat.ch/en/uuid/i/b8d5798e-a75e-5a7d-a858-f7a6613524ed-Two_catastrophic_years_obliterate_10_of_Swiss_glacier_volume | −6% (2022), −4% (2023), 10% in two years, 1960–1990 comparison |
| 4 | GLAMOS — "Annual mass balance of Swiss glaciers in 2024/2025" (26 Sep 2025, doi:10.18752/annualrep_2025) | Official annual report | https://doi.glamos.ch/pubs/annualrep/annualrep_2025.pdf | −1.6 m w.e. / −3.0%, quarter lost since 2015, Aletsch 12 m local loss, driver decomposition |
| 5 | FOEN/BAFU — "Klima: Das Wichtigste in Kürze" (3 Nov 2026) | Federal agency | https://www.bafu.admin.ch/de/zustand-klima | +2.8 °C vs pre-industrial |
| 6 | NASA Earth Observatory — "Glacial Losses in the Swiss Alps" (14 Mar 2025) | Agency article + Landsat imagery | https://science.nasa.gov/earth/earth-observatory/glacial-losses-in-the-swiss-alps-154043/ | 1984 vs 2024 Landsat pair; "largest in the Alps" |
| 7 | NASA NSIDC — MOD10A1 | Data product | https://nsidc.org/data/mod10a1 | daily snow cover |
| 8 | NASA POWER | Data portal | https://power.larc.nasa.gov/ | temperature/precipitation drivers |
| 9 | NASA Earthdata | Data portal | https://www.earthdata.nasa.gov/ | Landsat access |
| 10 | NASA ICESat-2 | Mission | https://icesat-2.gsfc.nasa.gov/ | elevation change 2018– |
| 11 | NASA LP DAAC — NASADEM | Data product | https://lpdaac.usgs.gov/products/nasadem_hgtv001/ | 30 m DEM |
| 12 | NASA LP DAAC — MOD11A2 | Data product | https://lpdaac.usgs.gov/products/mod11a2v061/ | 1 km land surface temperature |
| 13 | NASA GPM — IMERG | Data product | https://gpm.nasa.gov/data/imerg | precipitation |
