import type { SiteVariable } from '../story/types'
import { fmt, pct } from './cases'

/**
 * The 95% range of the trend on a line that always shows zero. If the range
 * crosses zero, "no change" is still possible, and the picture says so.
 */
export function RangeBar({ variable }: { variable: SiteVariable }) {
  const { ci_low: lo, ci_high: hi, sen_slope_per_decade: mid, unit } = variable
  if (lo == null || hi == null || mid == null) {
    return <p className="ev-empty">There is no reliable range for this record yet.</p>
  }
  const extent = Math.max(Math.abs(lo), Math.abs(hi), Math.abs(mid)) * 1.25 || 1
  const x = (v: number) => ((v + extent) / (2 * extent)) * 100
  const crosses = lo <= 0 && hi >= 0
  return (
    <figure className="ev-range">
      <div
        className="ev-range-track"
        role="img"
        aria-label={`Most likely change ${fmt(mid, true)} ${unit} per decade, range ${fmt(lo, true)} to ${fmt(hi, true)}.${crosses ? ' The range includes no change.' : ' The range does not include zero.'}`}
      >
        <span className="ev-range-zero" style={{ left: `${x(0)}%` }} />
        <span className="ev-range-band" style={{ left: `${x(lo)}%`, width: `${x(hi) - x(lo)}%` }} />
        <span className="ev-range-mid" style={{ left: `${x(mid)}%` }} />
      </div>
      <figcaption className="ev-range-caption">
        <span className="ev-range-zero-label" style={{ left: `${x(0)}%` }}>
          no change
        </span>
        <span className="ev-range-value">
          <strong className="narrow">
            {fmt(mid, true)} {unit}
          </strong>{' '}
          per decade, most likely between {fmt(lo, true)} and {fmt(hi, true)}
        </span>
      </figcaption>
    </figure>
  )
}

/** Share of the change the climate drivers leave unexplained, as one bar. */
export function SplitBar({ value }: { value: number }) {
  const rounded = Math.round(value)
  return (
    <figure className="ev-split">
      <p className="ev-split-number narrow">{pct(value)}</p>
      <div
        className="ev-split-bar"
        role="img"
        aria-label={`${rounded}% not explained by rain, heat or sunlight; ${100 - rounded}% consistent with them`}
      >
        <span className="ev-split-left" style={{ width: `${rounded}%` }} />
        <span className="ev-split-right" />
      </div>
      <figcaption className="ev-split-legend">
        <span>
          <span className="ev-key ev-key-left" aria-hidden="true" /> {rounded}% the climate does not explain
        </span>
        <span>
          <span className="ev-key ev-key-right" aria-hidden="true" /> {100 - rounded}% matches rain, heat and sunlight
        </span>
      </figcaption>
    </figure>
  )
}
