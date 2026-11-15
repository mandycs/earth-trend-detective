// The dataset or product id behind each record, copied from backend/catalog/variables.yaml `dataset` (15 Nov 2026),
// and who serves it. For the "Under the hood" tier only: never on the main line. No figure lives here; resolutions
// and periods come from the run's own events (list_variables, get_series).

export const VAR_DATASETS: Readonly<Record<string, string>> = {
  t2m: "NASA POWER (MERRA-2)",
  precip: "NASA POWER (MERRA-2 + IMERG corrected)",
  solar: "NASA POWER (CERES SYN1deg)",
  ndvi: "MOD13A3.061",
  lst_day: "MOD11A2.061",
  et: "MOD16A2GF.061",
  snow_cover: "MOD10A1.061",
  ndvi_gibs: "MODIS_Terra_L3_NDVI_Monthly (MOD13A3)",
  lst_gibs: "MODIS_Terra_L3_Land_Surface_Temp_Monthly_Day (MOD11C3)",
  snow_gibs: "MODIS_Terra_L3_Snow_Cover_Monthly_Average_Pct (MOD10CM)",
  no2_omi: "OMI_Nitrogen_Dioxide_Tropo_Column (OMNO2d v004)",
  co_airs: "AIRS_L3_Carbon_Monoxide_500hPa_Volume_Mixing_Ratio_Monthly_Day (AIRS3STM v006)",
  soil_moisture: "GLDAS_NOAH025_M.2.1",
  runoff: "GLDAS_NOAH025_M.2.1",
  grace_tws: "TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4",
  water_area: "MOD09A1.061",
  t2m_upstream: "NASA POWER (MERRA-2), mean of the upstream points",
  precip_upstream: "NASA POWER (MERRA-2 + IMERG corrected), mean of the upstream points",
  degree_days: "NASA POWER (MERRA-2), derived from monthly T2M",
  winter_precip: "NASA POWER (MERRA-2 + IMERG corrected), Oct–Apr water-year total",
  sst: "jplMURSST41mday (NASA JPL MUR SST)",
  chlorophyll: "erdMH1chlamday_R2022SQ (MODIS Aqua)",
  dhw: "noaacrwdhwDaily (NOAA Coral Reef Watch)",
};

/** Who serves the data, by source id (variables.yaml `source`). Non-NASA servers say so. */
export const PROVIDERS: Readonly<Record<string, string>> = {
  power: "NASA POWER (Langley)",
  grace: "NASA JPL GRACE Tellus (via PO.DAAC)",
  gldas: "NASA GES DISC (GLDAS)",
  gibs: "NASA GIBS (map tiles)",
  appeears: "NASA AppEEARS (LP DAAC)",
  appeears_water: "NASA AppEEARS (LP DAAC)",
  erddap: "NOAA CoastWatch ERDDAP (a NOAA data server, not NASA)",
};

/** Who serves a drawn layer, read from its own source line. Null when the line names no known server. */
export function providerOfSource(source: string): string | null {
  if (/gibs/i.test(source)) return PROVIDERS.gibs;
  if (/appeears/i.test(source)) return PROVIDERS.appeears;
  if (/erddap/i.test(source)) return PROVIDERS.erddap;
  if (/coral reef watch|noaa/i.test(source)) return "NOAA (not NASA)";
  if (/^grace$|grace/i.test(source)) return PROVIDERS.grace;
  if (/power/i.test(source)) return PROVIDERS.power;
  if (/lp daac|nasadem/i.test(source)) return "NASA LP DAAC";
  return null;
}
