import type { SiteVariable } from './types'
import { fmt } from '../lib/cases'
import { PlayPauseIcon } from '../lib/Icons'

export interface TimelineProps {
  first: number
  last: number
  year: number
  playing: boolean
  variable: SiteVariable | null
  /** True when the map shows one picture per year, so the terrain follows too. */
  mapFollows: boolean
  onScrub: (year: number) => void
  onToggle: () => void
}

const W = 1000
const H = 120
const PAD_Y = 14

/**
 * The year scrubber is the chart: the selected record, year by year, with the
 * cursor on the current year. A real <input type=range> sits on top, so
 * keyboard, screen readers and thumbs all work.
 */
export function Timeline({ first, last, year, playing, variable, mapFollows, onScrub, onToggle }: TimelineProps) {
  const series = variable?.series ?? []
  const values = series.map((p) => p.value)
  const min = values.length ? Math.min(...values) : 0
  const max = values.length ? Math.max(...values) : 1
  const span = max - min || 1
  const x = (y: number) => ((y - first) / Math.max(last - first, 1)) * W
  const y = (v: number) => H - PAD_Y - ((v - min) / span) * (H - PAD_Y * 2)

  let line = ''
  let area = ''
  let previous: number | null = null
  for (const p of series) {
    const jump = previous == null || p.year - previous > 1
    line += `${jump ? 'M' : 'L'}${x(p.year).toFixed(1)},${y(p.value).toFixed(1)}`
    previous = p.year
  }
  if (series.length > 1) {
    const zero = min < 0 && max > 0 ? y(0) : H - PAD_Y
    area = `M${x(series[0].year)},${zero}` + series.map((p) => `L${x(p.year).toFixed(1)},${y(p.value).toFixed(1)}`).join('') + `L${x(series[series.length - 1].year)},${zero}Z`
  }
  const point = series.find((p) => p.year === year) ?? null
  const crossesZero = min < 0 && max > 0

  const readout = point
    ? `${fmt(point.value, crossesZero)} ${variable?.unit ?? ''}`
    : series.length > 1
      ? 'No data this year'
      : ''

  return (
    <div className="tl" aria-label="Timeline">
      <button
        type="button"
        className="tl-play"
        onClick={onToggle}
        aria-pressed={playing}
        aria-label={playing ? 'Pause the years' : 'Play the years'}
      >
        <PlayPauseIcon playing={playing} />
      </button>

      <output className="tl-year narrow" aria-live="off">
        {year}
      </output>

      <div className="tl-chart">
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
          {crossesZero ? <line x1={0} x2={W} y1={y(0)} y2={y(0)} className="tl-zero" /> : null}
          {area ? <path d={area} className="tl-area" /> : null}
          {line ? <path d={line} className="tl-line" /> : null}
          <line x1={x(year)} x2={x(year)} y1={0} y2={H} className="tl-cursor" />
          {point ? <circle cx={x(point.year)} cy={y(point.value)} r={7} className="tl-dot" /> : null}
        </svg>
        <input
          type="range"
          min={first}
          max={last}
          step={1}
          value={year}
          aria-label="Year"
          aria-valuetext={`${year}${point ? `, ${variable?.label}: ${readout}` : ''}`}
          onChange={(event) => onScrub(Number(event.target.value))}
        />
        <div className="tl-ends" aria-hidden="true">
          <span>{first}</span>
          <span>{last}</span>
        </div>
      </div>

      <div className="tl-readout">
        <span className="tl-value narrow">{readout}</span>
        <span className="tl-label">
          {variable ? variable.label : 'No record selected'}
          {mapFollows ? ' · map follows the year' : ''}
        </span>
      </div>
    </div>
  )
}
