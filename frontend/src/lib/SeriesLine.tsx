import type { SeriesPoint } from '../story/types'

export interface SeriesLineProps {
  series: SeriesPoint[]
  /** Full year range, so gaps in the series stay gaps. */
  years: [number, number]
  width?: number
  height?: number
  className?: string
  label: string
}

/** Small yearly line, for lists and cards. Gaps in the data break the line. */
export function SeriesLine({ series, years, width = 120, height = 36, className, label }: SeriesLineProps) {
  if (series.length < 2) return null
  const [first, last] = years
  const values = series.map((p) => p.value)
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
      <path d={d} fill="none" stroke="currentColor" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      <circle cx={x(end.year)} cy={y(end.value)} r={3} fill="currentColor" />
    </svg>
  )
}
