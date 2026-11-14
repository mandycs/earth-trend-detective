export type Verdict = "real" | "likely" | "unknown";
export type Direction = "up" | "down" | "flat";

/** One row of `GET /sweep` (mirrors backend `VariableResult`). */
export interface VariableResult {
  id: string;
  label: string;
  unit: string;
  sen_slope_per_decade: number | null;
  ci_low: number | null;
  ci_high: number | null;
  sigma_per_decade: number | null;
  p_value: number | null;
  q_value: number | null;
  verdict: Verdict;
  direction: Direction;
  n_months: number;
  years_span: number;
  too_short: boolean;
  years_needed: number | null;
  residual_pct_non_climate: number | null;
  residual_pct_range: [number, number] | null;
}

export interface SeriesPoint {
  date: string; // YYYY-MM
  value: number | null;
  anomaly: number | null;
}

export interface SweepResponse {
  lat: number;
  lon: number;
  start: number;
  end: number;
  source: string;
  variables: VariableResult[];
  series?: Record<string, SeriesPoint[]>;
}

export interface Site {
  id: string;
  name: string;
  bbox: [number, number, number, number];
  point: [number, number]; // [lon, lat]
  tags: string[];
}

export interface Place {
  lat: number;
  lon: number;
  name?: string;
}
