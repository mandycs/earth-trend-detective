import type { SiteVariable } from '../story/types'
import { fmt, residualBounds } from './cases'

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

/**
 * Share of the change the climate drivers leave unexplained. When the climate
 * models disagree it is a range: solid up to the low end, lighter up to the high end.
 */
export function SplitBar({ variable }: { variable: Pick<SiteVariable, 'residual_pct_non_climate' | 'residual_pct_range'> }) {
  const bounds = residualBounds(variable)
  if (!bounds) return null
  const [lo, hi] = bounds
  const isRange = hi > lo
  const left = isRange ? `${lo}–${hi}%` : `${lo}%`
  const right = isRange ? `${100 - hi}–${100 - lo}%` : `${100 - lo}%`
  return (
    <figure className="ev-split">
      <p className="ev-split-number narrow">{left}</p>
      <div
        className="ev-split-bar"
        role="img"
        aria-label={`${left} not explained by rain, heat or sunlight${isRange ? ', depending on the climate model' : ''}; ${right} consistent with them`}
      >
        <span className="ev-split-left" style={{ width: `${lo}%` }} />
        {isRange ? <span className="ev-split-maybe" style={{ width: `${hi - lo}%` }} /> : null}
        <span className="ev-split-right" />
      </div>
      <figcaption className="ev-split-legend">
        <span>
          <span className="ev-key ev-key-left" aria-hidden="true" /> the climate does not explain
        </span>
        {isRange ? (
          <span>
            <span className="ev-key ev-key-maybe" aria-hidden="true" /> depends on the climate model
          </span>
        ) : null}
        <span>
          <span className="ev-key ev-key-right" aria-hidden="true" /> {right} matches rain, heat and sunlight
        </span>
      </figcaption>
    </figure>
  )
}
