import type { SeriesPoint, SiteVariable } from './types'

const WIDTH = 260
const HEIGHT = 56

/** Yearly series as an inline SVG line: no chart library, no extra latency. */
export function Sparkline({ variable }: { variable: SiteVariable }) {
  const points: SeriesPoint[] = variable.series ?? []
  if (points.length < 2) {
    return <p className="sparkline-empty">No yearly series supplied for this variable yet.</p>
  }
  const values = points.map((point) => point.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const step = WIDTH / (points.length - 1)
  const path = points
    .map((point, index) => {
      const x = index * step
      const y = HEIGHT - ((point.value - min) / span) * (HEIGHT - 8) - 4
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')

  const first = points[0]
  const last = points[points.length - 1]
  const tone = variable.direction === 'down' ? 'down' : variable.direction === 'up' ? 'up' : 'flat'

  return (
    <figure className="sparkline">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`${variable.label}, ${first.year} to ${last.year}: ${first.value} to ${last.value} ${variable.unit}`}
        preserveAspectRatio="none"
      >
        <line x1="0" y1={HEIGHT - 4} x2={WIDTH} y2={HEIGHT - 4} className="sparkline-axis" />
        <path d={path} className={`sparkline-line sparkline-${tone}`} />
      </svg>
      <figcaption>
        <span>
          {first.year} · {formatNumber(first.value)} {variable.unit}
        </span>
        <span>
          {last.year} · {formatNumber(last.value)} {variable.unit}
        </span>
      </figcaption>
    </figure>
  )
}

export function formatNumber(value: number): string {
  const abs = Math.abs(value)
  if (abs >= 1000) return value.toFixed(0)
  if (abs >= 10) return value.toFixed(1)
  if (abs >= 0.1) return value.toFixed(2)
  return value.toFixed(3)
}
