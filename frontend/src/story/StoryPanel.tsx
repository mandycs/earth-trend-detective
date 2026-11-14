import type { Site, SiteVariable } from './types'
import { VerdictBadge } from './VerdictBadge'
import { Sparkline, formatNumber } from './Sparkline'

export interface StoryPanelProps {
  site: Site
  variable: SiteVariable
  step: number
  hasTrendLayer: boolean
  onSelectVariable: (id: string) => void
  onStep: (step: number) => void
}

const STEP_TITLES = [
  'What is changing here?',
  'Is it real, or is it chance?',
  'Is it the climate?',
]

const DEFAULT_BODIES = [
  'We swept every NASA variable that applies to this place and kept the ones that moved. Press play on the timeline to watch the years go by.',
  'A trend can appear out of noise. This step asks whether the change is bigger than the year-to-year wobble, and whether it survives the fact that we tested several variables at once.',
  'Rain, heat and sunlight explain part of what is happening here. What they fail to explain is the interesting part.',
]

function stepTitle(site: Site, index: number): string {
  const entry = site.steps[index]
  if (typeof entry === 'string' && entry.trim()) return entry
  if (entry && typeof entry === 'object' && entry.title) return entry.title
  return STEP_TITLES[index] ?? STEP_TITLES[0]
}

function stepBody(site: Site, index: number): string {
  const entry = site.steps[index]
  if (entry && typeof entry === 'object' && entry.body) return entry.body
  return DEFAULT_BODIES[index] ?? ''
}

function chanceSentence(pValue: number | null): string {
  if (pValue === null) return 'There are not enough years of data to test this yet.'
  if (pValue < 0.001) return 'A pattern this steady would almost never happen by chance.'
  const oneIn = Math.max(1, Math.round(1 / Math.max(pValue, 0.0001)))
  return `A pattern this steady would show up by chance roughly once in ${oneIn} tries.`
}

function slopeSentence(variable: SiteVariable): string {
  if (variable.sen_slope_per_decade === null) return 'No slope can be estimated from this series.'
  const sign = variable.sen_slope_per_decade > 0 ? '+' : ''
  return `${sign}${formatNumber(variable.sen_slope_per_decade)} ${variable.unit} per decade`
}

export function StoryPanel({ site, variable, step, hasTrendLayer, onSelectVariable, onStep }: StoryPanelProps) {
  const [firstYear, lastYear] = site.years
  const isPreview = site.id.startsWith('_')
  const sources = site.sources ?? []
  const narrative = site.narrative ?? site.headline ?? ''

  return (
    <aside className="panel" aria-label={`Story: ${site.name}`}>
      <div className="panel-head">
        <p className="eyebrow">
          Case study · {firstYear}–{lastYear}
        </p>
        <h1>{site.name}</h1>
        {site.country ? <p className="country">{site.country}</p> : null}
        {isPreview ? (
          <p className="preview-flag" role="note">
            Preview case. The images and numbers here are placeholders while the data
            pipeline runs — do not read them as measurements.
          </p>
        ) : null}
      </div>

      <ol className="steps" aria-label="Investigation steps">
        {STEP_TITLES.map((title, index) => (
          <li key={title}>
            <button
              type="button"
              className={index === step ? 'step step-current' : index < step ? 'step step-done' : 'step'}
              aria-current={index === step ? 'step' : undefined}
              onClick={() => onStep(index)}
            >
              <span className="step-number" aria-hidden="true">
                {index < step ? '✓' : index + 1}
              </span>
              <span className="step-text">{title}</span>
            </button>
          </li>
        ))}
      </ol>

      <div className="panel-body">
        <h2>{stepTitle(site, step)}</h2>
        <p className="lede">{stepBody(site, step)}</p>

        {step === 0 ? (
          <ul className="variables">
            {site.variables.map((entry) => (
              <li key={entry.id}>
                <button
                  type="button"
                  className={entry.id === variable.id ? 'variable variable-selected' : 'variable'}
                  onClick={() => onSelectVariable(entry.id)}
                  aria-pressed={entry.id === variable.id}
                >
                  <span className="variable-name">{entry.label}</span>
                  <span className="variable-slope">{slopeSentence(entry)}</span>
                  <VerdictBadge verdict={entry.verdict} direction={entry.direction} />
                </button>
              </li>
            ))}
          </ul>
        ) : null}

        {step === 1 ? (
          <div className="evidence">
            <Sparkline variable={variable} />
            <dl className="stats">
              <div>
                <dt>Change</dt>
                <dd>{slopeSentence(variable)}</dd>
              </div>
              <div>
                <dt>Chance of this being noise</dt>
                <dd>
                  {variable.p_value === null ? 'not testable' : `p = ${variable.p_value.toFixed(3)}`}
                </dd>
              </div>
              <div>
                <dt>Verdict</dt>
                <dd>
                  <VerdictBadge verdict={variable.verdict} direction={variable.direction} />
                </dd>
              </div>
            </dl>
            {!hasTrendLayer ? (
              <p className="callout">
                No per-pixel trend map for this case yet. The numbers below come from the
                regional series, which is what the pipeline has computed so far.
              </p>
            ) : null}
            <p>{chanceSentence(variable.p_value)}</p>
            {variable.years_needed ? (
              <p className="callout">
                About {variable.years_needed} more years of data would be needed before this
                series could support a verdict.
              </p>
            ) : null}
            {variable.verdict === 'unknown' ? (
              <p className="muted">
                We would rather show “can’t tell yet” than turn noise into a headline.
              </p>
            ) : null}
          </div>
        ) : null}

        {step === 2 ? (
          <div className="evidence">
            {variable.residual_pct_non_climate !== null ? (
              <>
                <div
                  className="split"
                  role="img"
                  aria-label={`${variable.residual_pct_non_climate}% of the trend is not explained by climate drivers, ${100 - variable.residual_pct_non_climate}% is`}
                >
                  <span
                    className="split-nonclimate"
                    style={{ width: `${variable.residual_pct_non_climate}%` }}
                  />
                  <span className="split-climate" />
                </div>
                <ul className="split-legend">
                  <li>
                    <span className="swatch swatch-nonclimate" aria-hidden="true" />
                    {variable.residual_pct_non_climate}% not explained by rain, heat or sunlight
                  </li>
                  <li>
                    <span className="swatch swatch-climate" aria-hidden="true" />
                    {100 - variable.residual_pct_non_climate}% consistent with the climate
                    drivers we tested
                  </li>
                </ul>
                <p>{narrative}</p>
              </>
            ) : (
              <p>{narrative}</p>
            )}
            <p className="callout callout-warn">
              This is a clue, not a verdict on who is responsible. Factors we did not measure
              end up in the leftover share.
            </p>
          </div>
        ) : null}
      </div>

      <footer className="panel-footer">
        {step < 2 ? (
          <button type="button" className="primary" onClick={() => onStep(step + 1)}>
            Next: {STEP_TITLES[step + 1].replace(/\?$/, '').toLowerCase()} →
          </button>
        ) : (
          <button type="button" className="primary" onClick={() => onStep(0)}>
            ← Run the case again
          </button>
        )}
        {sources.length > 0 ? (
          <ul className="sources">
            {sources.map((source) => (
              <li key={source.url}>
                <a href={source.url} target="_blank" rel="noreferrer noopener">
                  {source.title}
                </a>
              </li>
            ))}
          </ul>
        ) : null}
      </footer>
    </aside>
  )
}
