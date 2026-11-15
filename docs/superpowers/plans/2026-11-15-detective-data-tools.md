# Detective agent — new data tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the detective variables that depend on the zone everywhere on Earth: sea (temperature, chlorophyll, heat stress), land at any point from GIBS yearly layers, atmosphere over cities (OMI / AIRS), reservoir water extent, and per-pixel "where" maps.

**Architecture:** Every new dataset becomes a catalog variable with a new `source` key (`erddap`, `gibs`) and a fetcher registered in `app/gather.py:FETCHERS`, so the core plan's `get_series` / `trend_test` reach it unchanged. Annual-only sources get an annual trend path. Grid sources feed a `trend_map` tool that writes a PNG overlay served by the backend.

**Tech Stack:** Python 3.12, httpx, numpy, pandas, pymannkendall (already used), FastAPI static files.

**Spec:** `docs/superpowers/specs/2026-11-15-detective-agent-design.md` (§5.3 rows `sea_series`, `water_extent`, `get_series` GIBS; §5.5d; §5.7 items 1 and 4; §6.1 GIBS annual path).

**Depends on:** `docs/superpowers/plans/2026-11-15-detective-core.md` Tasks 3–4 merged (`Session`, `Ledger`, `TOOLS`, `get_series` dispatching on `Variable.source` via `gather.FETCHERS`).

## Global Constraints

- All Global Constraints of the core plan apply (branch `mandy/detective`, venv, offline tests, no invented figures, English UI strings, commit style).
- ERDDAP facts from the reef scout (2026-11-15, tested live): brackets in griddap queries must be URL-encoded (`%5B`/`%5D`) or the answer is empty; long time ranges return 502/503, so request **one year per call, sequentially** (parallel calls get 408). Heat stress comes from `https://coastwatch.noaa.gov/erddap/griddap/noaacrwdhwDaily`, variable `degree_heating_week` (≈11 s per half-year request) — `NOAA_DHW_monthly` has **no** DHW (only `sea_surface_temperature`, its anomaly and a mask). Chlorophyll: `erdMH1chlamday_R2022SQ`, `chlor_a` (trend on log10; ends 2024-10 plus one 2025-01 month — clip to the study period). Bathymetry: `GEBCO_2020`, `elevation` (public domain, attribution "GEBCO Compilation Group, GEBCO 2020 Grid"). MUR and CRW SST trends differ (+0.22–0.26 vs +0.25–0.39 °C/decade on the reef): MUR is the primary product; CRW SST is never mixed into the same verdict.
- Ruling on spec §5.3 `sea_series`: sea variables are catalog variables reached through `get_series`; no separate `sea_series` tool (one path for every variable keeps the FDR ledger and the model's tool list simple).
- Sources and labels: MUR SST = NASA JPL (via NOAA ERDDAP, dataset `jplMURSST41mday`, variable `sst`); chlorophyll-a = NASA MODIS Aqua (ERDDAP dataset id found in Task 1); degree heating weeks = NOAA Coral Reef Watch (`NOAA_DHW_monthly` or the daily product reduced to yearly max), **labelled non-NASA**. ERDDAP base `https://coastwatch.pfeg.noaa.gov/erddap/griddap/`.
- GIBS yearly values are `status: "observed"`, annual seasonal means decoded from colours; trend-tested only on the annual path (≥ 10 years), never mixed with monthly-anomaly tests in one verdict; result carries `"precision": "palette step ≈ <value> <unit>"`.
- OMI results carry the caveat "OMI has a known sensor defect since 2007 (row anomaly); gaps are filled by neighbouring rows."
- Every new variable has `definition`, `units`, `resolution` and `applies_to` tags among: `ocean`, `coast`, `reef`, `city`, `atmosphere`, `vegetated`, `agriculture`, `water`, `snow`, `glacier`, `any`.

## Review Focus

1. **Point on land asked for sea temperature / point at sea asked for NDVI** → `not_available` with "This place is on land/at sea; this variable is measured over sea/land." Test in Task 2.
2. **ERDDAP returns an HTML error page or times out** → `not_available` with the source named; no exception leaks. Test in Task 1 (`test_erddap_error_page_is_not_available`).
3. **GIBS returns transparent tiles (no data) for some years** → those years are dropped; fewer than 10 years left → `too_short` with `years_needed`. Test in Task 3.
4. **Coastal pixel masked in MUR** (the Townsville failure) → the fetcher retries the nearest valid cell within 0.1° and reports the cell actually used. Test in Task 1.
5. **`trend_map` on a variable without a grid source** → `{"status": "not_available", "reason": "no gridded source for this variable"}`. Test in Task 5.

---

### Task 1: ERDDAP fetcher and sea variables

**Files:**
- Create: `backend/app/extractors/erddap.py`
- Modify: `backend/app/gather.py` (`SOURCES["erddap"]`, `FETCHERS["erddap"]`), `backend/catalog/variables.yaml` (`sst`, `chlorophyll`, `dhw`)
- Test: `backend/tests/test_erddap.py`

**Interfaces:**
- Produces: `fetch_point_monthly(dataset: str, variable: str, lat: float, lon: float, start: int, end: int, client: httpx.Client | None = None) -> tuple[pd.Series, tuple[float, float]]` (monthly series indexed by month start; returns the grid cell used) and `fetch_grid(dataset, variable, bbox, start, end, stride: int) -> xr.DataArray`.

- [ ] **Step 1: Find the chlorophyll and DHW dataset ids once** (`curl "https://coastwatch.pfeg.noaa.gov/erddap/search/index.csv?searchFor=chlorophyll+aqua+monthly"`; same for `degree heating`), record them in the catalog entries with a comment naming the query.
- [ ] **Step 2: Failing tests** with recorded CSV fixtures in `backend/tests/fixtures/erddap/`: `test_parses_monthly_csv` (units row skipped, index monthly); `test_erddap_error_page_is_not_available` (HTML body → the gather layer reports the source failure reason); `test_masked_cell_falls_back_to_nearest_valid` (first response all NaN → second request offset ≤ 0.1°, returned cell differs from the asked point).
- [ ] **Step 3–4:** implement; run `python -m pytest tests/test_erddap.py -q` → PASS; full suite green.
- [ ] **Step 5: Commit** — `feat: sea temperature, chlorophyll and heat stress from ERDDAP`.

### Task 2: Zone tags for sea, coast, reef and city

**Files:**
- Modify: `backend/app/detective/tools/data.py` (`profile_place`), `backend/app/investigate/landcover.py` (`tags_for`)
- Test: `backend/tests/detective/test_zones.py`

**Interfaces:**
- Produces: `zone_tags(shares: Mapping[str, float], lat: float) -> tuple[str, ...]` — `ocean` when Water ≥ 0.5 or no classified pixels; `coast` when 0.05 ≤ Water < 0.5; `reef` when `ocean|coast` and |lat| ≤ 30; `city` when Urban ≥ 0.15 (adds `atmosphere`). `profile_place` merges these with existing tags.

- [ ] **Step 1: Failing tests:** `test_open_sea_is_ocean`, `test_reef_latitude`, `test_city_gets_atmosphere`, `test_sea_variable_off_land_not_available` (tags `("vegetated",)` → `list_variables` marks `sst` `available=False` with the land/sea reason).
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5: Commit** — `feat: the place profile knows sea, coast, reef and city`.

### Task 3: GIBS yearly values at any point, and the annual trend path

**Files:**
- Modify: `backend/app/assets/gibs_layers.py` (extract `yearly_values(layer: GibsLayer, bbox, years, client) -> dict[int, np.ndarray]` from `build_layer`; `build_layer` calls it)
- Create: `backend/app/extractors/gibs_values.py` (fetcher: box mean per year → annual series), `backend/app/stats/annual.py`
- Modify: `backend/app/gather.py` (`FETCHERS["gibs"]`), `backend/catalog/variables.yaml` (`ndvi_gibs`, `lst_gibs`, `snow_gibs`), `backend/app/detective/tools/data.py` (`list_variables` swaps `appeears` variables for their `*_gibs` twin off-case; `trend_test` routes annual series to `annual_trend`)
- Test: `backend/tests/test_gibs_values.py`, `backend/tests/test_annual.py`

**Interfaces:**
- Produces: `annual_trend(series: pd.Series) -> TrendResult` (plain MK + Sen on one value per year; `too_short` when < 10 years; `years_needed` via `stats/years.py`); series from the `gibs` fetcher carry `attrs["temporal"] = "annual"` and `attrs["precision"]`.

- [ ] **Step 1: Failing tests:** `test_build_layer_unchanged_after_refactor` (existing site output byte-identical on a fixture tile); `test_transparent_years_are_dropped`; `test_annual_trend_too_short_under_ten_years`; `test_off_case_ndvi_becomes_ndvi_gibs`.
- [ ] **Step 2–4:** FAIL → implement → PASS; full suite green. **Step 5: Commit** — `feat: yearly NDVI, ground temperature and snow anywhere, tested on an annual path`.

### Task 4: Atmosphere over cities (OMI NO₂, AIRS)

**Files:**
- Modify: `backend/catalog/variables.yaml` (`no2_omi`, one AIRS variable), `backend/catalog/map_layers.yaml`
- Test: `backend/tests/test_atmosphere.py`

**Interfaces:**
- Produces: two catalog variables with `applies_to: [city, atmosphere]`, reached through the `gibs` fetcher of Task 3 if GIBS serves a monthly layer with a published colormap; otherwise a GES DISC OPeNDAP fetcher following `app/extractors/gldas.py` (Earthdata token from env, never logged).

- [ ] **Step 1: Spike (no commit):** list GIBS capabilities for OMI NO₂ and AIRS monthly layers with colormaps; if found, use Task 3's path. Record the decision in the plan's Run notes.
- [ ] **Step 2: Failing tests:** `test_no2_variable_applies_to_cities`; `test_omi_result_carries_row_anomaly_caveat`; fetcher fixture test for the chosen path.
- [ ] **Step 3–4:** implement → PASS. **Step 5: Commit** — `feat: air over cities from OMI and AIRS`.

### Task 5: Per-pixel "where" maps

**Files:**
- Create: `backend/app/detective/tools/where.py`, `backend/app/detective/maps.py` (static route `GET /detective/maps/{name}.png`)
- Modify: `backend/app/main.py`
- Test: `backend/tests/detective/test_where.py`

**Interfaces:**
- Consumes: `fetch_grid` (Task 1), `yearly_values` (Task 3), `assets/maps.sen_mk_grid`, `colorize`, `save_png`.
- Produces: tool `trend_map(var_id: str)` → `{"status": "ok", "url": "/detective/maps/<uuid>.png", "bounds": bbox, "legend": {...}, "share_significant": float, "median_slope_per_decade": float}` and a `map` op `{"op": "overlay", "url", "bounds", "legend"}`. Logs **one** `TestRecord(kind="trend")` for the median pixel series (pixel-level significance is shown faded, not FDR-claimed); the answer may quote `share_significant` only as "share of the area with a clear trend".

- [ ] **Step 1: Failing tests:** `test_trend_map_writes_png_and_overlay_op`; `test_no_grid_source_not_available`; `test_png_name_is_unguessable_uuid` and the route rejects `..` paths.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5: Commit** — `feat: where it changes — per-pixel trend maps for the detective`.

### Task 6: Reservoir water extent

**Files:**
- Create: `backend/app/extractors/water_extent.py`, `backend/app/detective/tools/water.py`
- Test: `backend/tests/test_water_extent.py`

**Interfaces:**
- Produces: tool `water_extent(year_a: int | None = None, year_b: int | None = None)` → yearly open-water area (km²) for `session.place.bbox`, `source`, `resolution: "30 m"`, `years`; series stored for `trend_test` (annual path).

- [ ] **Step 1: Spike (no commit), pick one and record it in Run notes:** (a) OPERA DSWx-HLS through the Earthdata GIS image service (`exportImage` for bbox + time, classes 1–2 = water) — check the earliest year available; (b) HLS true-colour from GIBS (`HLS_L30_Nadir_BRDF_Adjusted_Reflectance`, as in `assets/composite.py`) with a dark-blue water rule, labelled "estimated from true colour". Prefer (a) if it starts ≤ 2016.
- [ ] **Step 2: Failing tests** on fixtures: `test_water_area_from_class_raster`; `test_cloudy_scene_skipped`; `test_la_vinuela_bbox_area_in_plausible_range` (fixture raster → between 0.5 and 6 km², the reservoir is 5.65 km² full per iAgua).
- [ ] **Step 3–4:** implement → PASS. **Step 5: Commit** — `feat: reservoir water extent at 30 m for the detective`.

## Run notes

- **Task 4 (2026-11-15, GIBS capabilities read live once).** AIRS: GIBS serves the monthly
  layer `AIRS_L3_Carbon_Monoxide_500hPa_Volume_Mixing_Ratio_Monthly_Day` (AIRS3STM v006, 1°,
  2002-09 to now, gap 2025-05/06) with colormap `AIRS_Carbon_Monoxide_Volume_Mixing_Ratio`
  (ppbv) → Task 3's annual path, variable `co_airs`, a year needs all 12 months. OMI NO₂:
  GIBS has only the **daily** `OMI_Nitrogen_Dioxide_Tropo_Column` (OMNO2d v004, 0.25°, colormap
  of the same name, molecules/cm²); GES DISC has no monthly OMI NO₂ either (OMNO2d is daily, so
  OPeNDAP would also be one request per day, plus auth). Decision: GIBS daily layer read on
  4 days a month (1, 9, 17, 25 → 48 pictures a year, ≈ 7 s per year uncached), a year needs
  half of them seen; variable `no2_omi`, label "annual mean of daily values on 4 days a
  month". Colormap parser now reads `1.06e+14` exponents (MODIS colormaps parse unchanged).
