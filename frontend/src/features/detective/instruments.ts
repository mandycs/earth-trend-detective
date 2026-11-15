// "Natural language → technical tools", made visible: for each step, the instrument or method the detective used,
// read from the step's own event payloads (tool name, args, result). Pure: no DOM, no React.
// Every figure printed here (years, counts) is copied from a tool result; nothing is computed for printing. The
// instrument names are fixed facts of the catalog (backend/catalog/variables.yaml `source` and `dataset`).
import type { Investigation, Scene } from "./scenes.ts";

/** The instrument behind each record, in words a student can say out loud. From variables.yaml `dataset`. */
export const VAR_INSTRUMENTS: Readonly<Record<string, string>> = {
  t2m: "NASA POWER · MERRA-2 weather model",
  precip: "NASA POWER · GPM rain satellites + MERRA-2",
  solar: "NASA POWER · CERES sunlight satellites",
  ndvi: "MODIS Terra satellite · greenness",
  lst_day: "MODIS Terra satellite · ground heat",
  et: "MODIS Terra satellite · water given off by plants",
  snow_cover: "MODIS Terra satellite · snow",
  lst_gibs: "MODIS Terra satellite · ground heat",
  ndvi_gibs: "MODIS Terra satellite · greenness",
  snow_gibs: "MODIS Terra satellite · snow",
  no2_omi: "OMI instrument on Aura · air pollution",
  co_airs: "AIRS instrument on Aqua · carbon monoxide",
  soil_moisture: "GLDAS land model (NASA)",
  runoff: "GLDAS land model (NASA)",
  grace_tws: "GRACE & GRACE-FO gravity satellites",
  water_area: "MODIS satellite pictures · open water",
  t2m_upstream: "NASA POWER · MERRA-2, upstream points",
  precip_upstream: "NASA POWER · GPM rain + MERRA-2, upstream points",
  degree_days: "NASA POWER · MERRA-2 weather model",
  winter_precip: "NASA POWER · GPM rain + MERRA-2",
  sst: "MUR sea temperature (several satellites)",
  chlorophyll: "MODIS Aqua satellite · ocean colour",
  dhw: "NOAA Coral Reef Watch",
};

/** The same, by source id, for a record this table does not name (`list_variables` gives each record's source). */
export const SOURCE_INSTRUMENTS: Readonly<Record<string, string>> = {
  power: "NASA POWER",
  grace: "GRACE & GRACE-FO gravity satellites",
  gldas: "GLDAS land model (NASA)",
  gibs: "MODIS satellite maps (NASA GIBS)",
  appeears: "MODIS satellite (NASA AppEEARS)",
  appeears_water: "MODIS satellite pictures",
  erddap: "Ocean satellites (ERDDAP)",
};

/** The method behind a step, for the disclosure only: never on the main line. */
export const METHODS: Readonly<Record<string, string>> = {
  trend_test:
    "Trend test: Mann-Kendall with the Hamed & Rao correction for months that follow each other, and the Sen slope (the median of all pairwise slopes) for its size.",
  climate_residual:
    "Climate check (RESTREND-style): a least-squares fit of the record on the measured climate, month by month, with no time term; the trend of what is left over is what the measured climate does not explain. A clue, not proof.",
  correlate: "Year-by-year match: Pearson correlation of year-on-year changes, also one year apart.",
  years_needed_for: "Record length: how many years the same test would need to tell a trend this size from noise.",
  years_needed: "Record length: how many years the same test would need to tell a trend this size from noise.",
  compare: "Two places: the same trend test run on each place.",
  trend_map: "Trend map: the trend test run on every pixel.",
  land_cover_change: "Land cover: MODIS yearly land cover classes (IGBP), compared between two years.",
};

export interface VarInfo { label: string | null; source: string | null }

const str = (x: unknown): string | null => (typeof x === "string" && x !== "" ? x : null);
const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
function years(x: unknown): [number, number] | null {
  return Array.isArray(x) && x.length === 2 && typeof x[0] === "number" && typeof x[1] === "number" ? [x[0], x[1]] : null;
}
const span = (y: [number, number] | null): string | null => (y ? (y[0] === y[1] ? `${y[0]}` : `${y[0]}–${y[1]}`) : null);

/** var id → label and source, from every list_variables and get_series result of the thread. */
export function varCatalog(scenes: readonly Scene[]): Map<string, VarInfo> {
  const out = new Map<string, VarInfo>();
  const put = (id: string, label: string | null, source: string | null) => {
    const prev = out.get(id);
    out.set(id, { label: label ?? prev?.label ?? null, source: source ?? prev?.source ?? null });
  };
  for (const s of scenes) {
    const t = s.tool;
    const r = t?.result;
    if (!t || !r) continue;
    if (t.tool === "list_variables" && Array.isArray(r.variables)) {
      for (const v of r.variables) if (isObj(v) && str(v.id)) put(v.id as string, str(v.label), str(v.source));
    } else if (t.tool === "get_series" && str(r.var_id)) {
      put(r.var_id as string, str(r.label), null);
    }
  }
  return out;
}

export function instrumentOf(varId: string, vars: Map<string, VarInfo>): string | null {
  if (Object.hasOwn(VAR_INSTRUMENTS, varId)) return VAR_INSTRUMENTS[varId];
  const src = vars.get(varId)?.source;
  return src && Object.hasOwn(SOURCE_INSTRUMENTS, src) ? SOURCE_INSTRUMENTS[src] : null;
}

/** "grace_tws:2003-2024" → "grace_tws". */
const varOfSeries = (id: unknown): string | null => {
  const s = str(id);
  return s ? s.split(":")[0] : null;
};

function labelOf(varId: string | null, vars: Map<string, VarInfo>, fallback?: unknown): string | null {
  return str(fallback) ?? (varId ? vars.get(varId)?.label ?? null : null);
}

/** A climate driver's label; "precip_12mo" is the residual model's past-12-months version of "precip". */
function driverLabel(id: string, vars: Map<string, VarInfo>): string | null {
  const own = vars.get(id)?.label;
  if (own) return own;
  const m = /^(.+)_12mo$/.exec(id);
  const base = m ? vars.get(m[1])?.label : null;
  return base ? `${base} over the past 12 months` : null;
}

const join = (parts: (string | null | undefined)[]): string | null => {
  const p = parts.filter((x): x is string => !!x);
  return p.length > 0 ? p.join(" · ") : null;
};

/**
 * The technical line of one step: the instrument or method, the record and its years. Null when the step used no
 * tool, or when the payload names nothing worth a line. Years come only from the event; none is guessed.
 */
export function toolLine(scene: Scene, vars: Map<string, VarInfo>): string | null {
  const t = scene.tool;
  if (!t) return null;
  const r = t.result ?? {};
  const a = t.args;
  const varId = str(r.var_id) ?? str(a.var_id) ?? varOfSeries(r.series_id ?? a.series_id);
  const label = labelOf(varId, vars, r.label);
  switch (t.tool) {
    case "profile_place":
      return join(["MODIS land cover map", typeof r.land_cover_year === "number" ? `${r.land_cover_year}` : null]);
    case "list_variables": {
      if (!Array.isArray(r.variables)) return "Catalogue of records";
      const n = r.variables.filter((v) => isObj(v) && v.available === true).length;
      return `Catalogue of records · ${n} usable here`;
    }
    case "solved_case":
      return join(["Solved case file", str(r.name)]);
    case "get_series":
      return join([varId ? instrumentOf(varId, vars) : null, label, span(years(r.years))]);
    case "trend_test": {
      const basis = str(r.basis);
      return join(["Trend test", label, span(years(r.years)), basis === "monthly" ? "month by month" : basis === "annual means" ? "year by year" : null]);
    }
    case "climate_residual": {
      const drivers = Array.isArray(r.drivers)
        ? r.drivers.map((d) => (typeof d === "string" ? driverLabel(d, vars) : null)).filter((x): x is string => !!x)
        : [];
      return join(["Climate check", label, drivers.length > 0 ? `against ${drivers.join(", ")}` : null]);
    }
    case "correlate": {
      const va = varOfSeries(r.series_a ?? a.series_a);
      const vb = varOfSeries(r.series_b ?? a.series_b);
      const la = labelOf(va, vars);
      const lb = labelOf(vb, vars);
      return join(["Year-by-year match", la && lb ? `${la} and ${lb}` : null]);
    }
    case "land_cover_change": {
      const ya = typeof r.year_a === "number" ? r.year_a : null;
      const yb = typeof r.year_b === "number" ? r.year_b : null;
      return join(["MODIS land cover", ya != null && yb != null ? `${ya} and ${yb}` : null]);
    }
    case "satellite_picture": {
      const ya = typeof r.year_a === "number" ? r.year_a : null;
      const yb = typeof r.year_b === "number" ? r.year_b : null;
      return join(["Satellite pictures", ya != null && yb != null ? `${ya} and ${yb}` : null]);
    }
    case "trend_map":
      return join(["Trend map", label, span(years(r.years))]);
    case "compare":
      return join(["Same test, two places", label]);
    case "years_needed":
    case "years_needed_for":
      return join(["Record length check", label]);
    default:
      return null;
  }
}

export interface RecordChoice { varId: string; label: string; instrument: string | null }
export interface QuestionReading { records: RecordChoice[]; methods: { tool: string; text: string }[] }

/**
 * How the detective read the question, for the current turn: the records it fetched (in order, once each) and the
 * methods it ran. Empty until the first record arrives.
 */
export function questionReading(inv: Investigation): QuestionReading {
  let from = 0;
  for (let i = inv.scenes.length - 1; i >= 0; i--) if (inv.scenes[i].kind === "opening") { from = i; break; }
  const vars = varCatalog(inv.scenes);
  const records: RecordChoice[] = [];
  const seen = new Set<string>();
  const methods: { tool: string; text: string }[] = [];
  const seenTools = new Set<string>();
  for (const s of inv.scenes.slice(from)) {
    const t = s.tool;
    if (!t) continue;
    if (t.tool === "get_series" && t.state === "done") {
      const varId = str(t.result?.var_id) ?? str(t.args.var_id);
      const label = varId ? labelOf(varId, vars, t.result?.label) : null;
      if (varId && label && !seen.has(varId)) {
        seen.add(varId);
        records.push({ varId, label, instrument: instrumentOf(varId, vars) });
      }
    }
    if (t.state === "done" && Object.hasOwn(METHODS, t.tool) && !seenTools.has(METHODS[t.tool])) {
      seenTools.add(METHODS[t.tool]);
      methods.push({ tool: t.tool, text: METHODS[t.tool] });
    }
  }
  return { records, methods };
}
