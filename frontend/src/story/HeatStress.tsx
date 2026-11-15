import type { HeatStress, SiteVariable } from './types'

/**
 * Heat stress is an event record (NOAA Coral Reef Watch degree heating weeks), not a
 * trend test: it gets a neutral tag, never a verdict stamp, and its counts come from
 * `site.json` `heat_stress` only.
 */

/** "4" for 4.0, as the pipeline keys `reef_years_at_or_above` and `years_at_or_above`. */
export function thresholdKey(value: number): string {
  return String(value)
}

export function thresholdText(value: number, unit: string): string {
  return `${value} ${unit}`
}

function reefYears(n: number): string {
  return n === 1 ? `${n} reef-year` : `${n} reef-years`
}

/** The neutral tag an events row shows where a trend row shows its verdict stamp. */
export function EventsTag({ variable, big = false, className = '' }: { variable: SiteVariable; big?: boolean; className?: string }) {
  return (
    <span className={`stamp stamp-unknown${big ? ' stamp-big' : ''} ${className}`} title="An event record: counted, not tested for a trend.">
      <span aria-hidden="true">▲</span>
      <span>{variable.badge ?? 'Event record'}</span>
    </span>
  )
}

export function HeatStressRecord({ heat }: { heat: HeatStress }) {
  const first = heat.thresholds[0]
  const firstKey = first ? thresholdKey(first.value) : null
  const source = 'title' in heat.source ? heat.source.title : heat.source.name
  return (
    <>
      <div className="sp-caveats">
        <h3>{heat.label}</h3>
        <ul>
          {heat.periods.map((period) => {
            const [y0, y1] = period.years
            return (
              <li key={`${y0}-${y1}`}>
                {heat.thresholds.map((t) => {
                  const n = period.reef_years_at_or_above[thresholdKey(t.value)]
                  return n == null ? null : (
                    <span key={t.value}>
                      {reefYears(n)} at or above {thresholdText(t.value, heat.unit)}, {y0}–{y1}.{' '}
                    </span>
                  )
                })}
                {period.reef_years_missing > 0 ? <span>{reefYears(period.reef_years_missing)} without data.</span> : null}
              </li>
            )
          })}
        </ul>
      </div>
      {first && firstKey ? (
        <div className="sp-caveats">
          <h3>Years at or above {thresholdText(first.value, heat.unit)}, reef by reef</h3>
          <ul>
            {heat.points.map((point) => {
              const years = point.years_at_or_above[firstKey] ?? []
              return (
                <li key={point.id}>
                  <strong>{point.name}</strong>: {years.length > 0 ? years.join(', ') : 'no measured year'}
                </li>
              )
            })}
          </ul>
        </div>
      ) : null}
      <details className="sp-how">
        <summary>How we know</summary>
        <p>{heat.method}</p>
        <dl>
          {heat.thresholds.map((t) => (
            <div key={t.value}>
              <dt>{thresholdText(t.value, heat.unit)}</dt>
              <dd>{t.label}</dd>
            </div>
          ))}
        </dl>
        <p>
          {heat.source.url ? (
            <a href={heat.source.url} target="_blank" rel="noreferrer noopener">
              {source}
            </a>
          ) : (
            source
          )}
        </p>
      </details>
    </>
  )
}
