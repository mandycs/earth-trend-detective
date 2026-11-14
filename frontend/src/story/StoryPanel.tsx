import { useEffect, useState } from 'react'
import { BeforeAfter } from '../lib/BeforeAfter'
import { pairFromLayers } from '../lib/beforeAfterPair'
import type { BeforeAfterPair } from '../lib/beforeAfterPair'
import type { Site, SiteVariable } from './types'
import { Stamp } from '../lib/Stamp'
import { SeriesLine } from '../lib/SeriesLine'
import { RangeBar, SplitBar } from '../lib/Evidence'
import { fmt, leadVariable, residualText, shortName, slopeText, stampFor } from '../lib/cases'
import { API_URL } from '../features/explore/api'

export interface StoryPanelProps {
  site: Site
  variable: SiteVariable
  step: number
  onSelectVariable: (id: string) => void
  onStep: (step: number) => void
}

export const STEPS = ['What changed?', 'Is it real?', 'Is it the climate?'] as const

function chanceSentence(pValue: number | null): string {
  if (pValue === null) return 'There are not enough years of data to test this yet.'
  if (pValue < 0.001) return 'A pattern this steady would almost never happen by chance.'
  const oneIn = Math.max(1, Math.round(1 / Math.max(pValue, 0.0001)))
  if (oneIn <= 3) return 'A pattern like this turns up by chance quite often, so we do not call it.'
  return `A pattern this steady would turn up by chance about once in ${oneIn} tries.`
}

function leadSentence(site: Site, lead: SiteVariable): string {
  if (site.headline) return site.headline
  const slope = slopeText(lead)
  return lead.verdict === 'unknown'
      ? `${lead.label}: we can't tell yet whether it is changing.`
      : `${lead.label} is ${lead.direction === 'down' ? 'going down' : 'going up'}${lead.verdict === 'real' ? ' for real' : ', probably'}${slope ? ` (${slope} per decade)` : ''}.`
}

function usePair(siteId: string): BeforeAfterPair | null {
  const [pair, setPair] = useState<{ id: string; value: BeforeAfterPair | null }>({ id: '', value: null })
  useEffect(() => {
    let alive = true
    fetch(`/sites/${siteId}/layers.json`)
      .then((r) => (r.ok ? r.json() : null))
      .then((file) => alive && setPair({ id: siteId, value: pairFromLayers(siteId, file) }))
      .catch(() => alive && setPair({ id: siteId, value: null }))
    return () => {
      alive = false
    }
  }, [siteId])
  return pair.id === siteId ? pair.value : null
}

function Changing({ site, variable, onSelectVariable }: { site: Site; variable: SiteVariable; onSelectVariable: (id: string) => void }) {
  const pair = usePair(site.id)
  return (
    <>
      {pair ? <BeforeAfter pair={pair} alt={`Satellite picture of ${shortName(site.name)}`} /> : null}
      <p className="sp-lede">
        Every NASA record we could get for this place, {site.years[0]} to {site.years[1]}. Pick one to put it on the
        timeline.
      </p>
      <ul className="sp-vars">
        {site.variables.map((entry) => {
          const slope = slopeText(entry)
          const selected = entry.id === variable.id
          return (
            <li key={entry.id}>
              <button
                type="button"
                className={selected ? 'sp-var sp-var-on' : 'sp-var'}
                aria-pressed={selected}
                onClick={() => onSelectVariable(entry.id)}
              >
                <span className="sp-var-name">{entry.label}</span>
                <span className="sp-var-slope">{slope ? `${slope} / decade` : 'no trend estimate'}</span>
                {entry.series && entry.series.length > 1 ? (
                  <SeriesLine
                    series={entry.series}
                    years={site.years}
                    width={96}
                    height={34}
                    className="sp-var-line"
                    label={`${entry.label}, yearly`}
                  />
                ) : (
                  <span className="sp-var-line" />
                )}
                <Stamp verdict={entry.verdict} direction={entry.direction} className="sp-var-stamp" />
              </button>
            </li>
          )
        })}
      </ul>
      {site.missing && Object.keys(site.missing).length > 0 ? (
        <div className="sp-missing">
          <h3>Still on its way</h3>
          <ul>
            {Object.entries(site.missing).map(([id, why]) => (
              <li key={id}>
                <strong>{id.replace(/_/g, ' ')}</strong>: {why}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </>
  )
}

function Real({ site, variable }: { site: Site; variable: SiteVariable }) {
  const s = stampFor(variable.verdict, variable.direction)
  const lead = leadVariable(site)
  const validation = site.validation
  return (
    <>
      <div className="sp-verdict">
        <Stamp verdict={variable.verdict} direction={variable.direction} />
        <p>
          <strong>{variable.label}.</strong> {s.meaning}
        </p>
      </div>
      <RangeBar variable={variable} />
      <p>{chanceSentence(variable.p_value)}</p>
      {variable.years_needed ? (
        <p className="sp-note">
          About {variable.years_needed} more years of data would be needed before this record could support a verdict,
          if the trend keeps going.
        </p>
      ) : null}
      {variable.verdict === 'unknown' ? (
        <p className="sp-note">We would rather say “can’t tell yet” than turn noise into a headline.</p>
      ) : null}
      {variable.note ? <p className="sp-note">{variable.note}</p> : null}
      {validation && lead && variable.id === lead.id && validation.r != null ? (
        <div className="sp-check">
          <h3>Checked against the ground</h3>
          <p>
            <strong className="narrow sp-check-r">r = {validation.r.toFixed(2)}</strong>
            <span>
              between our satellite record and the measured water level
              {validation.n_months ? `, over ${validation.n_months} months` : ''}.
              {validation.elevation_trend_m_per_decade != null
                ? ` The measured level itself changed ${fmt(validation.elevation_trend_m_per_decade, true)} m per decade.`
                : ''}
            </span>
          </p>
          {validation.url ? (
            <a href={validation.url} target="_blank" rel="noreferrer noopener">
              {validation.source}
            </a>
          ) : (
            <p className="sp-note">{validation.source}</p>
          )}
        </div>
      ) : null}
      <details className="sp-how">
        <summary>How we know</summary>
        <p>
          Monthly records, with the normal seasons removed. Mann-Kendall trend test (Hamed-Rao correction for
          autocorrelation), Theil-Sen slope with a 95% range, and a Benjamini-Hochberg correction because we test
          several records at once.
        </p>
        <dl>
          <div>
            <dt>p-value</dt>
            <dd>{variable.p_value == null ? 'n/a' : fmt(variable.p_value)}</dd>
          </div>
          <div>
            <dt>q-value (FDR)</dt>
            <dd>{variable.q_value == null ? 'n/a' : fmt(variable.q_value)}</dd>
          </div>
        </dl>
      </details>
    </>
  )
}

interface Narrative {
  text: string
  checked: boolean
}

function NarratorButton({ siteId }: { siteId: string }) {
  const [state, setState] = useState<{ kind: 'idle' } | { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'done'; value: Narrative }>({ kind: 'idle' })

  const ask = async () => {
    setState({ kind: 'loading' })
    try {
      const response = await fetch(`${API_URL}/explain/narrative`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ site_id: siteId }),
        signal: AbortSignal.timeout(60_000),
      })
      if (!response.ok) throw new Error(String(response.status))
      const body = (await response.json()) as { text?: string; validation?: { ok?: boolean } }
      if (!body.text) throw new Error('empty')
      setState({ kind: 'done', value: { text: body.text, checked: Boolean(body.validation?.ok) } })
    } catch {
      setState({ kind: 'error', message: 'The narrator did not answer. Check that the backend is running and try again.' })
    }
  }

  if (state.kind === 'done') {
    return (
      <figure className="sp-narrative">
        <blockquote>{state.value.text}</blockquote>
        <figcaption>
          Written by an AI narrator from this case’s numbers.
          {state.value.checked ? ' Every figure was checked against the data before showing it.' : ''}
        </figcaption>
      </figure>
    )
  }
  return (
    <div className="sp-narrator">
      <button type="button" className="btn" onClick={ask} disabled={state.kind === 'loading'}>
        {state.kind === 'loading' ? (
          <>
            <span className="spinner" aria-hidden="true" /> Writing the case summary…
          </>
        ) : (
          'Tell me the whole case'
        )}
      </button>
      {state.kind === 'error' ? (
        <p className="sp-note" role="alert">
          {state.message}
        </p>
      ) : null}
    </div>
  )
}

function Climate({ site, variable, onSelectVariable }: { site: Site; variable: SiteVariable; onSelectVariable: (id: string) => void }) {
  const withSplit = site.variables.find((v) => v.residual_pct_non_climate != null) ?? null
  const caveats = site.caveats ?? []
  return (
    <>
      {variable.residual_pct_non_climate != null ? (
        <>
          <p className="sp-lede">
            How much of the change in {variable.label.toLowerCase()} rain, heat and sunlight do not explain.
          </p>
          <SplitBar variable={variable} />
          <p>
            {variable.residual_pct_range
              ? `Between ${residualText(variable)} is left over once the climate is accounted for, depending on the climate model: local climate at the site, or adding the climate of the upstream basin.`
              : `About ${residualText(variable)} is left over once the climate is accounted for.`}{' '}
            That is a clue worth following, not an attribution.
          </p>
        </>
      ) : withSplit ? (
        <>
          <p className="sp-lede">
            We only split climate from the rest for records the climate acts on. Here that is{' '}
            {withSplit.label.toLowerCase()}.
          </p>
          <button type="button" className="btn btn-primary" onClick={() => onSelectVariable(withSplit.id)}>
            Show {withSplit.label.toLowerCase()}
          </button>
        </>
      ) : (
        <p className="sp-lede">
          For this place we do not show a climate split: the caveats below explain why. The trends themselves still
          stand.
        </p>
      )}
      {caveats.length > 0 ? (
        <div className="sp-caveats">
          <h3>Read it right</h3>
          <ul>
            {caveats.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <NarratorButton siteId={site.id} />
    </>
  )
}

export function StoryPanel({ site, variable, step, onSelectVariable, onStep }: StoryPanelProps) {
  const lead = leadVariable(site)
  const sources = site.sources ?? []

  return (
    <aside className="sp" aria-label={`Case: ${shortName(site.name)}`}>
      <header className="sp-head">
        <h1 className="sp-title narrow">{shortName(site.name)}</h1>
        <p className="sp-where">
          {site.country} · {site.years[0]}–{site.years[1]}
        </p>
        {lead ? (
          <div className="sp-lead">
            <Stamp verdict={lead.verdict} direction={lead.direction} big />
            <p>{leadSentence(site, lead)}</p>
          </div>
        ) : null}
      </header>

      <div className="sp-tabs" role="tablist" aria-label="The three questions">
        {STEPS.map((title, index) => (
          <button
            key={title}
            type="button"
            role="tab"
            id={`tab-${index}`}
            aria-selected={index === step}
            aria-controls="sp-body"
            className={index === step ? 'sp-tab sp-tab-on' : 'sp-tab'}
            onClick={() => onStep(index)}
          >
            {title}
          </button>
        ))}
      </div>

      <div className="sp-body" id="sp-body" role="tabpanel" aria-labelledby={`tab-${step}`} key={step}>
        {step === 0 ? <Changing site={site} variable={variable} onSelectVariable={onSelectVariable} /> : null}
        {step === 1 ? <Real site={site} variable={variable} /> : null}
        {step === 2 ? <Climate site={site} variable={variable} onSelectVariable={onSelectVariable} /> : null}
      </div>

      <footer className="sp-foot">
        {step < 2 ? (
          <button type="button" className="btn btn-primary" onClick={() => onStep(step + 1)}>
            Next: {STEPS[step + 1].replace(/\?$/, '').toLowerCase()} <span aria-hidden="true">→</span>
          </button>
        ) : (
          <button type="button" className="btn" onClick={() => onStep(0)}>
            <span aria-hidden="true">←</span> Start the case again
          </button>
        )}
        {sources.length > 0 ? (
          <details className="sp-sources">
            <summary>Data sources</summary>
            <ul>
              {sources.map((source) => (
                <li key={source.url}>
                  <a href={source.url} target="_blank" rel="noreferrer noopener">
                    {source.title}
                  </a>
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </footer>
    </aside>
  )
}
