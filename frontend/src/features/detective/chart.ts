// Chart model for an evidence scene. Points come from tool results; the trend lines are drawn from the
// tool's slope and CI, so no figure is derived for printing. Pure module.
import type { Verdict, Direction } from "../../story/types";
import { verdictFor } from "./board.ts";
import type { Investigation, Scene } from "./scenes.ts";

export interface ChartPoint { year: number; value: number }
export interface TrendLines { line: [ChartPoint, ChartPoint]; low: [ChartPoint, ChartPoint]; high: [ChartPoint, ChartPoint] }
export interface ChartModel {
  label: string; unit: string | null; points: ChartPoint[]; years: [number, number]; trend: TrendLines | null;
  verdict: { verdict: Verdict; direction: Direction } | null;
}

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" && v ? v : null);

function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/** Lines through (median year, median value) with the given slopes, from the first to the last year. */
export function trendLines(points: ChartPoint[], slopePerDecade: number, ciLow: number | null, ciHigh: number | null): TrendLines {
  const x0 = points[0].year;
  const x1 = points[points.length - 1].year;
  const ax = median(points.map((p) => p.year));
  const ay = median(points.map((p) => p.value));
  const through = (perDecade: number): [ChartPoint, ChartPoint] => {
    const k = perDecade / 10;
    return [{ year: x0, value: ay + k * (x0 - ax) }, { year: x1, value: ay + k * (x1 - ax) }];
  };
  const line = through(slopePerDecade);
  const both = ciLow !== null && ciHigh !== null;
  return { line, low: both ? through(ciLow) : line, high: both ? through(ciHigh) : line };
}

function pointsOf(result: Record<string, unknown> | null): ChartPoint[] | null {
  const raw = result?.chart;
  if (!Array.isArray(raw)) return null;
  const out: ChartPoint[] = [];
  for (const r of raw) {
    const o = r as { year?: unknown; value?: unknown } | null;
    const year = num(o?.year);
    const value = num(o?.value);
    if (year !== null && value !== null) out.push({ year, value });
  }
  return out;
}

export function chartFor(inv: Investigation, scene: Scene): ChartModel | null {
  const tool = scene.tool;
  const result = tool?.result;
  if (!tool || !result || tool.tool === "compare") return null;

  let source: Record<string, unknown> = result;
  let points = pointsOf(result);
  if (points === null) {
    const sid = str(result.series_id);
    const at = inv.scenes.findIndex((s) => s.key === scene.key);
    if (!sid || at < 0) return null;
    for (let i = at - 1; i >= 0; i--) {
      const r = inv.scenes[i].tool?.result ?? null;
      if (r && r.series_id === sid && pointsOf(r) !== null) { source = r; points = pointsOf(r); break; }
    }
  }
  if (!points || points.length < 2) return null;
  points = [...points].sort((a, b) => a.year - b.year);

  const slope = num(result.slope_per_decade);
  const trend = slope !== null && result.too_short !== true
    ? trendLines(points, slope, num(result.ci_low), num(result.ci_high))
    : null;
  return {
    label: str(result.label) ?? str(source.label) ?? str(result.var_id) ?? str(source.var_id) ?? "",
    unit: str(source.unit),
    points,
    years: [points[0].year, points[points.length - 1].year],
    trend,
    verdict: verdictFor(str(result.test_id), inv.board, result),
  };
}
