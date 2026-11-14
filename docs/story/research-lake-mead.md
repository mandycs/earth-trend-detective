# Case file 01 — Lake Mead / Colorado River Basin (USA)

> Research dossier for **Earth Trend Detective** · NASA Space Apps Challenge 2026 · compiled 2026-11-14.
> Every number carries a bracketed source id that maps to the URL table in §10.
>
> **Labels used throughout:** **[P]** published / measured (peer-reviewed or official agency data) · **[E]** estimate, model or projection · **[press]** figure reported by media from official data · **(computed)** our own arithmetic on published values · **not found** = we looked and could not source it.

---

## 1. Pitch (EN — usable as `site.json` copy)

> America's largest reservoir is at its lowest level since it first filled. Is the Colorado drying out — or are we taking more water than the river carries? NASA's gravity satellites say the basin lost 65 km³ of water in nine years, most of it from underground. Warming explains about a tenth of the flow loss. The rest is arithmetic: 16.5 million acre-feet of legal rights on a river that now averages 12.4.

**Verdict this case must land:** *mostly us, partly the climate.* It is the "non-climatic dominant" case of the three.

---

## 2. Site

| Item | Value | Source |
|---|---|---|
| Reservoir | Lake Mead, Hoover Dam, Nevada/Arizona, USA | [1] |
| Approx. centroid | 36.15 N, −114.40 W | (site location, for extraction) |
| Suggested bbox (data pull) | lon −114.85 … −113.75 ; lat 35.95 … 36.55 | (our choice, approximate) |
| Full pool elevation | 1,229.0 ft above mean sea level | [1] |
| Dead storage elevation | 895.0 ft | [1] |
| Basin population served | ~40 million people | [3] |
| Irrigated farmland in basin | ~4 million acres (NASA 2014) / "4 to 5 million acres" (NASA EO 2022) | [3], [6] |

---

## 3. The headline change (published numbers)

| Metric | Value | Date | Type | Source |
|---|---|---|---|---|
| Reservoir elevation | **1,039.66 ft** | 8 Nov 2026 | [P] | [2] |
| Reservoir content | 6,954 thousand acre-feet = **27% full** | 8 Nov 2026 | [P] | [2] |
| Projected end-of-calendar-year 2026 elevation | 1,034.52 ft | Oct 2026 24-Month Study | [E] | [2] |
| Previous record annual minimum | **1,040.50 ft** | 28 Jul 2022 | [P] | [1] |
| Annual minimum 2025 | 1,054.03 ft | 8 Aug 2025 | [P] | [1] |
| Annual minimum 2024 | 1,060.79 ft | 27 Nov 2024 | [P] | [1] |
| Annual maximum 2024 (post-2023 recovery) | 1,076.66 ft | 27 Feb 2024 | [P] | [1] |
| Annual minimum 2023 | 1,044.82 ft | 1 Jan 2023 | [P] | [1] |
| Total Colorado River system storage | 19,925 kaf = 34% (21,862 kaf = 37% a year earlier) | 8 Nov 2026 | [P] | [2] |
| Lake Powell elevation / content | 3,538.84 ft / 6,376 kaf = 27% | 8 Nov 2026 | [P] | [2] |

**How to read it without lying on stage.** The November 2026 reading is below the 2022 minimum, so it is the lowest level since the reservoir first filled. It is **not** the lowest water level in the table: the annual minima of 1935–1937 (673.50 ft, 905.20 ft, 1,021.90 ft) are lower, but those occur while the reservoir was still being filled [1]. NASA's own wording for the 2022 record was "lowest since April 1937, when the reservoir was still being filled" [6]. Use that phrasing.

**The recovery that wasn't.** The wet winter of 2023 lifted Mead from 1,044.82 ft (1 Jan 2023) to 1,076.66 ft (27 Feb 2024) [1] — a 31.84 ft rebound (computed). By 8 Aug 2025 it was back to 1,054.03 ft [1], and by 8 Nov 2026 to 1,039.66 ft [2]. Two years of rain bought roughly two years of storage. This is the single most important honest beat in the case: *a wet year is not a trend reversal*, and our app should be able to say so.

---

## 4. Is the change statistically real?

- A published Mann–Kendall / Sen slope for Lake Mead's monthly or annual elevation series: **not found.** Reclamation publishes the series [1] but not a trend test.
- Published framing of the decline: NASA Earth Observatory describes "a 22-year downward trend" as of July 2022 [6]. That is a descriptive statement, not a significance test.
- What our pipeline should do (design, not a published result): run MK (Hamed–Rao corrected) + Sen on **water-year mean elevation**, not on annual minima. Minima are single-day samples and are dominated by summer operations; the 2023–24 rebound would flip a short-window test on minima. With 2000–2026 annual means the expected sign is negative; the p-value must be computed, not asserted.

---

## 5. Climate vs not-climate: what the literature actually separates

| Claim | Number | Type | Source |
|---|---|---|---|
| Anthropogenic warming share of present-day natural flow | **10.3%** reduction (since 1880, temperature + CO₂) | [P] | [4] |
| Runoff sensitivity to warming | **8.1% per °C** ; **6.8% per °C** when vegetation response to CO₂ is included | [P] | [4] |
| Share of basin runoff decline coming from snowpack regions | **86%**, although snowpack regions are only **~30%** of the basin area | [P] | [4] |
| Natural flow reduction 2000–2021 attributable to warming | "roughly the storage of Lake Mead" | [P] | [4] |
| Precipitation trend over the historical period | climate models show **little agreement**, "no trend in the mean" of CMIP6 | [P] | [4] |
| Water lost from the basin, Dec 2004 – Nov 2013 (GRACE) | **65 km³** (53 million acre-feet) | [P] | [3] |
| Groundwater share of that loss | **50 km³** (41 MAF), "more than 75 percent" | [P] | [3] |
| Legal allocation under the 1922 Compact + 1944 Treaty | **16.5 MAF/yr** (7.5 upper + 7.5 lower + 1.5 Mexico) | [P] | [5] |
| Flow assumed when the Compact was written | 16.4 MAF/yr | [P] | [5] |
| Actual flow, 1906–2024 | **14.6 MAF/yr** | [P] | [5] |
| Actual flow, 2000–2024 | **12.43 MAF/yr** | [P] | [5] |
| Consumptive use, 2021 → 2024 | 13.8 → 13.3 MAF/yr | [P] | [5] |
| Flow over 2021–2024 | **~11.9 MAF/yr** | [P] | [5] |
| Agriculture share of consumptive use, 2000–2019 | **52%** | [P] | [5] |

**The arithmetic that makes the story (computed, indicative — label it as our reading, not a published attribution):**

- Paper rights minus recent flow: 16.5 − 12.43 = **≈4.1 MAF/yr** structural gap.
- Warming's share of natural flow: 10.3% of ~12.4 MAF = **≈1.3 MAF/yr**.
- So of the roughly 4 MAF gap, the climate explains on the order of a third and the entitlement structure explains the rest.

That is exactly the "residual" our product is built to show: take the climate signal out of the water record, and what is left is a demand and allocation problem. The Congressional Research Service calls the same condition "the Colorado River Basin's structural deficit" [5] — use their phrase, it is the neutral one.

**Why this matters for the demo:** it is the cleanest public example where "it's the climate" is *partly* true and *mostly insufficient*. Warming removed ~10% of the flow; the Compact wrote cheques for 33% more water than the river has delivered since 2000.

---

## 6. NASA data available for this site

| Variable | NASA product | Resolution / cadence | Period | Access |
|---|---|---|---|---|
| Terrestrial water storage anomaly | GRACE / GRACE-FO (JPL mascons, CSR/JPL solutions) | monthly, ~300 km | 2002–2017, 2018–present | grace.jpl.nasa.gov [12] |
| Reservoir surface area | Landsat 5/7/8/9 | 30 m, 16-day | 1984–present | Earthdata [13] |
| Snow cover | MODIS MOD10A1 | 500 m, daily | 2000–present | NSIDC [8] |
| Precipitation | GPM IMERG | 0.1°, 30-min → monthly | 2000–present | gpm.nasa.gov [9] |
| Land surface water balance (soil moisture, snow, ET) | GLDAS-2.2 | 0.25°, monthly | 2003–present | ldas.gsfc.nasa.gov [10] |
| Soil moisture | SMAP L4 | 9 km, 3-hourly | 2015–present | smap.jpl.nasa.gov [11] |
| Climate drivers (T, precip, radiation) | NASA POWER | 0.5° × 0.625°, daily | 1981–present | power.larc.nasa.gov [7] |

**Honesty requirement for the "NASA Data" judging criterion.** The headline elevation and storage figures are **Reclamation gauge data, not a NASA product** [1][2]. NASA supplies (a) the basin-scale water-mass loss from GRACE [3], (b) the snowpack and precipitation drivers [8][9], and (c) the Landsat imagery of the shrinking lake surface [6]. The UI must attribute them separately, or a judge who knows the field will catch it.

---

## 7. What our pipeline would compute here

1. **Target series:** GRACE/GRACE-FO terrestrial water storage anomaly over the Upper+Lower basin mask, monthly, 2002–2026; deseasonalised; MK (Hamed–Rao) + Sen.
2. **Drivers:** IMERG precipitation (basin mean), POWER 2 m temperature, MODIS snow-cover days.
3. **Residual:** TWS ~ precipitation + snow cover + temperature → MK on the residual. The expected result is a strongly negative residual: the part of the water loss that the weather does not explain.
4. **Cross-check (the punchline):** compare the residual trend with 16.5 MAF of rights vs 12.43 MAF of actual flow [5]. If both point the same way, the case is closed without any causal claim.
5. **Uncertainty flag:** GRACE has ~300 km resolution and cannot resolve the reservoir. Say "the basin", never "Lake Mead's groundwater".

---

## 8. Story beats (five screens)

1. **The bathtub ring.** Landsat, July 2000 vs July 2022 — the white mineral band is the shoreline we used to fill [6].
2. **The river we were promised.** 16.4 MAF assumed in 1922; 12.43 MAF delivered 2000–2024 [5].
3. **The water you can't see.** 65 km³ lost in nine years, 50 km³ of it groundwater, measured by a satellite that weighs the landscape [3].
4. **The 10% that is climate.** Warming takes 10.3% of the flow, and 86% of the decline comes from the 30% of the basin that holds snow [4].
5. **Verdict.** "Real? Yes. The climate? Partly — about a third of the gap. The rest is us."

---

## 9. Caveats we should say before the jury does

- **"Lowest ever" is wrong.** Lowest *since filling*; the 1935–37 minima are lower because the lake was still filling [1][6].
- **The 2023–24 rebound is real** and our series must show it [1]. Any trend statement that hides it is cherry-picking the period.
- **10.3% is a modelled attribution** [4], not a measurement. It has an uncertainty range we are not quoting because the abstract does not give one; say "about a tenth, modelled".
- **GRACE resolution** (~300 km) means the groundwater number is a basin-scale integral [3], not a well field.
- **Period dependence:** 2000–2026 vs 1906–2024 give different slopes for the same river [5].

---

## 10. Sources

| # | Source | Type | URL | Used for |
|---|---|---|---|---|
| 1 | U.S. Bureau of Reclamation — Lake Mead annual high and low elevations, 1935–2025 (PDF table) | Agency data | https://www.usbr.gov/lc/region/g4000/lakemead_line.pdf | annual minima/maxima, full pool 1,229 ft, dead storage 895 ft |
| 2 | U.S. Bureau of Reclamation — Lower Colorado Weekly Hydrologic Update, 8 Nov 2026 (PDF) | Agency data (current) | https://www.usbr.gov/lc/region/g4000/weekly.pdf | 1,039.66 ft, 6,954 kaf, 27%, system 34%, 2026 projection |
| 3 | NASA — "Satellite Study Reveals Parched U.S. West Using Up Underground Water" (24 Jul 2014) | Agency press release (peer-reviewed study) | https://www.nasa.gov/news-release/satellite-study-reveals-parched-u-s-west-using-up-underground-water/ | 65 km³ lost, 50 km³ groundwater, 40 M people, 4 M acres, "most over-allocated" |
| 4 | Bass, Goldenson, Rahimi & Hall (2023), *Water Resources Research* 59 — "Aridification of Colorado River Basin's Snowpack Regions…" | Peer-reviewed | https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2022WR033454 | 10.3%, 8.1%/°C, 6.8%/°C, 86% from 30% of area, no CMIP6 precip trend |
| 5 | Congressional Research Service R45546 — "Management of the Colorado River" (updated 1 Oct 2026) | Official report | https://www.congress.gov/crs-product/R45546 | 16.5 MAF allocation, 16.4 assumed, 14.6 / 12.43 actual, 13.8→13.3 use, 11.9 flow, 52% ag |
| 6 | NASA Earth Observatory — "Lake Mead Keeps Dropping" (22 Jul 2022) | Agency article + Landsat imagery | https://earthobservatory.nasa.gov/images/150111/lake-mead-keeps-dropping | 27% capacity Jul 2022, 1,041.30 ft, "lowest since April 1937", 22-year trend |
| 7 | NASA POWER (prediction Of Worldwide Energy Resources) | Data portal | https://power.larc.nasa.gov/ | climate driver series 1981–present |
| 8 | NASA NSIDC — MODIS MOD10A1 snow cover | Data product | https://nsidc.org/data/mod10a1 | daily snow cover, 500 m |
| 9 | NASA GPM — IMERG | Data product | https://gpm.nasa.gov/data/imerg | precipitation 0.1°, 2000– |
| 10 | NASA GLDAS-2.2 | Data product | https://ldas.gsfc.nasa.gov/gldas | land surface water balance, 0.25° |
| 11 | NASA SMAP | Mission | https://smap.jpl.nasa.gov/ | soil moisture, 9 km |
| 12 | NASA/JPL GRACE | Mission + data | https://grace.jpl.nasa.gov/ | TWS mascons, 2002– |
| 13 | NASA Earthdata | Data portal | https://www.earthdata.nasa.gov/ | Landsat and product access |
