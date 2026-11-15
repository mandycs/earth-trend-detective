// Screen geometry for SceneChart. Pure. It places tool values on the canvas; it never makes a figure
// that is printed: the printed labels are the first/last year and the min/max point values as given.
import type { ChartModel, ChartPoint } from "./chart.ts";

export interface ChartView {
  width: number; height: number;
  path: string; // annual line
  dots: { x: number; y: number }[];
  trend: string | null; // dashed trend line
  band: string | null; // polygon points between low and high
  min: { point: ChartPoint; topPct: number; leftPct: number };
  max: { point: ChartPoint; topPct: number; leftPct: number } | null; // null when min and max are the same value
}

const f = (n: number): string => n.toFixed(1);

export function chartView(model: ChartModel, width = 560, height = 220, pad = 16, padY = pad): ChartView {
  const pts = model.points;
  const [x0, x1] = model.years;
  const ys = pts.map((p) => p.value);
  if (model.trend) {
    for (const pair of [model.trend.line, model.trend.low, model.trend.high]) for (const p of pair) ys.push(p.value);
  }
  let lo = Math.min(...ys);
  let hi = Math.max(...ys);
  if (!(hi - lo > 0)) {
    // Zero y-range: center the flat line with an arbitrary margin (geometry only, never printed).
    const m = Math.abs(lo) > 0 ? Math.abs(lo) * 0.1 : 1;
    lo -= m;
    hi += m;
  }
  const xSpan = x1 - x0 > 0 ? x1 - x0 : 1;
  const x = (year: number): number => (x1 - x0 > 0 ? pad + ((year - x0) / xSpan) * (width - 2 * pad) : width / 2);
  const y = (v: number): number => padY + (1 - (v - lo) / (hi - lo)) * (height - 2 * padY);
  const xy = (p: ChartPoint): string => `${f(x(p.year))},${f(y(p.value))}`;

  const path = pts.map((p, i) => `${i ? "L" : "M"}${xy(p)}`).join("");
  const dots = pts.map((p) => ({ x: x(p.year), y: y(p.value) }));
  const t = model.trend;
  const trend = t ? `M${xy(t.line[0])}L${xy(t.line[1])}` : null;
  const band = t ? [t.low[0], t.low[1], t.high[1], t.high[0]].map(xy).join(" ") : null;

  let minP = pts[0];
  let maxP = pts[0];
  for (const p of pts) {
    if (p.value < minP.value) minP = p;
    if (p.value > maxP.value) maxP = p;
  }
  const at = (p: ChartPoint) => ({ point: p, topPct: (y(p.value) / height) * 100, leftPct: (x(p.year) / width) * 100 });
  return {
    width, height, path, dots, trend, band,
    min: at(minP),
    max: maxP.value === minP.value ? null : at(maxP),
  };
}
