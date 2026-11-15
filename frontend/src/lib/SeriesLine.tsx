import type { SeriesPoint } from '../story/types'

export interface SeriesLineProps {
  series: SeriesPoint[]
  /** Full year range, so gaps in the series stay gaps. */
  years: [number, number]
  width?: number
  height?: number
  className?: string
  label: string
  /**
   * Sen's slope per decade. When given, the trend is drawn as the bold line and the
   * yearly values sit behind it, faint: the row reads as "where it is heading".
   */
  slopePerDecade?: number | null
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
}

/** Small yearly line, for lists and cards. Gaps in the data break the line. */
export function SeriesLine({ series, years, width = 120, height = 36, className, label, slopePerDecade = null }: SeriesLineProps) {
  if (series.length < 2) return null
  const [first, last] = years
  // Trend through the data with the pipeline's own slope; the intercept is the median
  // offset of the points from that slope (the Theil-Sen way), so the line sits in them.
  const perYear = slopePerDecade == null ? null : slopePerDecade / 10
  const offset = perYear == null ? 0 : median(series.map((p) => p.value - perYear * (p.year - first)))
  const trendAt = (year: number) => offset + (perYear ?? 0) * (year - first)
  const trendYears: [number, number] = [series[0].year, series[series.length - 1].year]
  const values = [...series.map((p) => p.value), ...(perYear == null ? [] : trendYears.map(trendAt))]
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const x = (year: number) => ((year - first) / Math.max(last - first, 1)) * width
  const y = (v: number) => height - 3 - ((v - min) / span) * (height - 6)
  let d = ''
  let previous: number | null = null
  for (const p of series) {
    const jump = previous == null || p.year - previous > 1
    d += `${jump ? 'M' : 'L'}${x(p.year).toFixed(1)},${y(p.value).toFixed(1)}`
    previous = p.year
  }
  const end = series[series.length - 1]
  const hasTrend = perYear != null
  return (
    <svg
      className={className}
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      role="img"
      aria-label={label}
      preserveAspectRatio="none"
    >
      <path
        d={d}
        fill="none"
        stroke="currentColor"
        strokeOpacity={hasTrend ? 0.45 : 1}
        strokeWidth={hasTrend ? 1.25 : 2}
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
      {hasTrend ? (
        <line
          x1={x(trendYears[0])}
          y1={y(trendAt(trendYears[0]))}
          x2={x(trendYears[1])}
          y2={y(trendAt(trendYears[1]))}
          stroke="currentColor"
          strokeWidth={2.5}
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      ) : (
        <circle cx={x(end.year)} cy={y(end.value)} r={3} fill="currentColor" />
      )}
    </svg>
  )
}
