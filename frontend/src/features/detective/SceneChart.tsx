import { fmt } from '../../lib/cases'
import type { ChartModel } from './chart'
import { chartView } from './chartView'
import styles from './detective.module.css'

const W = 560
const H = 220

/** Annual points, the trend line and its likely range. Prints only tool values: years and min/max. */
export function SceneChart({ model }: { model: ChartModel }) {
  const v = chartView(model, W, H, 16, 36) // room above and below for the max/min labels
  const [first, last] = model.years
  const unit = model.unit ? ` ${model.unit}` : ''
  const label = `${model.label || 'Yearly values'}, ${first}–${last}`
  return (
    <figure className={styles.chart}>
      <div className={styles.chartCanvas} style={{ aspectRatio: `${W} / ${H}` }}>
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} className={styles.chartSvg}>
          {v.band && <polygon points={v.band} className={styles.chartBand} />}
          {v.trend && <path d={v.trend} className={styles.chartTrend} />}
          <path d={v.path} className={styles.chartLine} />
          {v.dots.map((d, i) => (
            <circle key={i} cx={d.x} cy={d.y} r={3.5} className={styles.chartDot} />
          ))}
        </svg>
        {[v.max, v.min].map((m) =>
          m ? (
            <span
              key={m === v.min ? 'min' : 'max'}
              className={styles.chartValue}
              aria-hidden="true"
              style={{
                top: `${m.topPct}%`,
                left: `${m.leftPct}%`,
                transform: `translate(${m.leftPct > 60 ? '-100%' : '0'}, ${m === v.min ? '4px' : 'calc(-100% - 4px)'})`,
              }}
            >
              {fmt(m.point.value)}
              {unit}
            </span>
          ) : null,
        )}
      </div>
      <div className={styles.chartAxis} aria-hidden="true">
        <span>{first}</span>
        <span>{last}</span>
      </div>
      <figcaption className={styles.chartLegend}>
        {model.trend ? 'Dots: yearly values · dashed line: the trend · shaded band: its likely range' : 'Dots: yearly values'}
      </figcaption>
    </figure>
  )
}
