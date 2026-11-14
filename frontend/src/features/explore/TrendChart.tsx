import type { SeriesPoint, VariableResult } from "./types";
import { fmtNumber } from "./format";
import styles from "./explore.module.css";

const W = 320;
const H = 110;
const PAD = 6;

function rollingMean(values: (number | null)[], window: number): (number | null)[] {
  return values.map((_, i) => {
    const slice = values.slice(Math.max(0, i - window + 1), i + 1).filter((x): x is number => x != null);
    return slice.length >= window / 2 ? slice.reduce((a, b) => a + b, 0) / slice.length : null;
  });
}

function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function pathFor(values: (number | null)[], x: (i: number) => number, y: (v: number) => number): string {
  let d = "";
  let pen = false;
  values.forEach((v, i) => {
    if (v == null) {
      pen = false;
      return;
    }
    d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
    pen = true;
  });
  return d;
}

interface Props {
  variable: VariableResult;
  points: SeriesPoint[] | undefined;
}

/** Monthly difference from normal, a 12-month average and the fitted trend. */
export default function TrendChart({ variable, points }: Props) {
  if (!points || points.length < 2) return null;
  const anomalies = points.map((p) => p.anomaly);
  const valid = anomalies.filter((x): x is number => x != null);
  if (valid.length < 2) return null;

  const smooth = rollingMean(anomalies, 12);
  const lo = Math.min(...valid);
  const hi = Math.max(...valid);
  const span = hi - lo || 1;
  const n = points.length;
  const x = (i: number) => PAD + (i / (n - 1)) * (W - 2 * PAD);
  const y = (v: number) => PAD + (1 - (v - lo) / span) * (H - 2 * PAD);

  const slope = variable.sen_slope_per_decade;
  const showTrend = slope != null && variable.verdict !== "unknown";
  let trend: string | null = null;
  if (showTrend) {
    const perMonth = slope / 120;
    const offsets = anomalies.flatMap((a, i) => (a == null ? [] : [a - perMonth * i]));
    const b = median(offsets);
    trend = `M${x(0)},${y(b)}L${x(n - 1)},${y(b + perMonth * (n - 1))}`;
  }

  const first = points[0].date.slice(0, 4);
  const last = points[n - 1].date.slice(0, 4);
  const tone = variable.direction === "up" ? styles.trendUp : styles.trendDown;
  const label =
    `${variable.label}: monthly difference from normal, ${first} to ${last}, ` +
    `ranging from ${fmtNumber(lo, true)} to ${fmtNumber(hi, true)} ${variable.unit}.` +
    (showTrend ? ` Trend line ${fmtNumber(slope, true)} ${variable.unit} per decade.` : "");

  return (
    <figure className={styles.chart}>
      <figcaption className={styles.chartCaption}>Difference from a normal month ({variable.unit})</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} className={styles.chartSvg}>
        {lo < 0 && hi > 0 && (
          <line x1={PAD} x2={W - PAD} y1={y(0)} y2={y(0)} className={styles.zeroLine} />
        )}
        <path d={pathFor(anomalies, x, y)} className={styles.rawLine} />
        <path d={pathFor(smooth, x, y)} className={styles.smoothLine} />
        {trend && <path d={trend} className={`${styles.trendLine} ${tone}`} />}
      </svg>
      <div className={styles.chartAxis} aria-hidden="true">
        <span>{first}</span>
        <span className={styles.chartLegend}>
          <span className={styles.keySmooth} /> 12-month average
          {trend && (
            <>
              <span className={`${styles.keyTrend} ${tone}`} /> trend
            </>
          )}
        </span>
        <span>{last}</span>
      </div>
    </figure>
  );
}
