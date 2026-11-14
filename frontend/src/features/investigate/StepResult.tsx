import type { SiteVariable } from '../../story/types'
import { Stamp } from '../../lib/Stamp'
import { SeriesLine } from '../../lib/SeriesLine'
import { SplitBar } from '../../lib/Evidence'
import { BeforeAfter } from '../../lib/BeforeAfter'
import { residualText, slopeText } from '../../lib/cases'
import type { ExplainResult, LandCoverResult, ThenNowResult, VariablesResult } from './types'
import styles from './investigate.module.css'

function Variables({ result, years }: { result: VariablesResult; years: [number, number] }) {
  const vars: SiteVariable[] = result.variables ?? []
  const split = vars.find((v) => v.residual_pct_non_climate != null)
  return (
    <div className={styles.result}>
      <ul className={styles.vars}>
        {vars.map((v) => (
          <li key={v.id} className={styles.var}>
            <span className={styles.varName}>{v.label}</span>
            <span className={styles.varSlope}>{slopeText(v) ? `${slopeText(v)} / decade` : 'no trend estimate'}</span>
            {v.series && v.series.length > 1 ? (
              <SeriesLine series={v.series} years={years} width={96} height={32} className={styles.varLine} label={`${v.label}, yearly`} />
            ) : (
              <span className={styles.varLine} />
            )}
            <Stamp verdict={v.verdict} direction={v.direction} className={styles.varStamp} />
          </li>
        ))}
      </ul>
      {split && split.residual_pct_non_climate != null ? (
        <div className={styles.split}>
          <p>
            Of the change in {split.label.toLowerCase()}, the climate leaves {split.residual_pct_range ? 'between ' : 'about '}
            {residualText(split)} unexplained{split.residual_pct_range ? ', depending on the climate model' : ''}. A clue, not
            an attribution.
          </p>
          <SplitBar variable={split} />
        </div>
      ) : null}
      {result.missing && Object.keys(result.missing).length > 0 ? (
        <ul className={styles.missing}>
          {Object.entries(result.missing).map(([id, why]) => (
            <li key={id}>
              <strong>{id.replace(/_/g, ' ')}</strong>: {why}
            </li>
          ))}
        </ul>
      ) : null}
      {result.sources && result.sources.length > 0 ? (
        <p className={styles.source}>
          Source:{' '}
          {result.sources.map((s, i) => (
            <span key={s.url ?? i}>
              {i > 0 ? ', ' : ''}
              {s.url ? (
                <a href={s.url} target="_blank" rel="noreferrer noopener">
                  {s.title ?? s.name}
                </a>
              ) : (
                (s.title ?? s.name)
              )}
            </span>
          ))}
        </p>
      ) : null}
    </div>
  )
}

function share(value: number): string {
  if (value > 0 && value < 0.005) return '<1%'
  return `${Math.round(value * 100)}%`
}

function LandCover({ result }: { result: LandCoverResult }) {
  const { before, after, changes } = result
  return (
    <div className={styles.result}>
      {before && after ? (
        <p className={styles.cover}>
          <span>
            <strong className="narrow">{before.year}</strong> {before.dominant}
          </span>
          <span aria-hidden="true">→</span>
          <span>
            <strong className="narrow">{after.year}</strong> {after.dominant}
          </span>
        </p>
      ) : null}
      {changes.length > 0 ? (
        <ul className={styles.changes}>
          {changes.map((c) => (
            <li key={c.class}>
              <span>{c.class}</span>
              <span>
                {share(c.before)} → {share(c.after)}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className={styles.note}>No land-cover class changed its share in this area.</p>
      )}
      {result.source ? (
        <p className={styles.source}>
          Source:{' '}
          {result.source.url ? (
            <a href={result.source.url} target="_blank" rel="noreferrer noopener">
              {result.source.name}
            </a>
          ) : (
            result.source.name
          )}
        </p>
      ) : null}
    </div>
  )
}

function ThenNow({ result, name }: { result: ThenNowResult; name: string }) {
  const { before, after } = result
  if (before && after) {
    return (
      <div className={styles.result}>
        <BeforeAfter
          pair={{
            before: { src: before.url, year: before.year },
            after: { src: after.url, year: after.year },
            note: `Two pictures of the same season (${before.date} and ${after.date}). Pictures, not a measurement.`,
            source: 'MODIS Terra true colour, NASA GIBS',
          }}
          alt={`Satellite picture of ${name}`}
        />
      </div>
    )
  }
  const one = before ?? after
  return (
    <div className={styles.result}>
      {one ? (
        <figure className={styles.single}>
          <img src={one.url} alt={`Satellite picture of ${name}, ${one.date}`} />
          <figcaption>
            {one.date}. No clear picture was found for the {before ? 'end' : 'start'} of the period, so there is
            nothing to compare against. A picture, not a measurement.
          </figcaption>
        </figure>
      ) : (
        <p className={styles.note}>No clear picture was found for either end of the period.</p>
      )}
    </div>
  )
}

function Explain({ result }: { result: ExplainResult }) {
  if (!result.text) {
    return <p className={styles.note}>{result.note ?? 'No summary could be written for this place.'}</p>
  }
  return (
    <figure className={styles.narrative}>
      <blockquote>{result.text}</blockquote>
      <figcaption>
        {result.source === 'llm' ? 'Written by an AI narrator from the numbers above.' : 'Written from the numbers above.'}
        {result.validation?.ok ? ' Every figure was checked against the data before showing it.' : ''}
      </figcaption>
    </figure>
  )
}

export function StepResult({ id, result, years, name }: { id: string; result: unknown; years: [number, number]; name: string }) {
  if (!result || typeof result !== 'object') return null
  if (id === 'land_cover') return <LandCover result={result as LandCoverResult} />
  if (id === 'then_and_now') return <ThenNow result={result as ThenNowResult} name={name} />
  if (id === 'explain') return <Explain result={result as ExplainResult} />
  if ('variables' in result) return <Variables result={result as VariablesResult} years={years} />
  return null
}
