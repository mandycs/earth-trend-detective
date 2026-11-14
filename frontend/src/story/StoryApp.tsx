'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSite, useStoryAssets } from './useSite'
import { StoryScene } from './StoryScene'
import { StoryPanel } from './StoryPanel'
import { Timeline } from './Timeline'
import type { SiteVariable } from './types'

interface CaseEntry {
  id: string
  label: string
  where: string
}

/**
 * The three story-mode cases. `_example` is the fixture with placeholder art,
 * kept first while the pipeline is still generating the real ones.
 */
const CASES: CaseEntry[] = [
  { id: '_example', label: 'Preview case', where: 'sample assets' },
  { id: 'lake_mead', label: 'Lake Mead', where: 'United States' },
  { id: 'aletsch', label: 'Aletsch', where: 'Switzerland' },
  { id: 'donana', label: 'Doñana', where: 'Spain' },
]

const PLAY_SPEED = 2.4 // years per second

export default function StoryApp() {
  const [caseId, setCaseId] = useState(CASES[0].id)
  const [variableId, setVariableId] = useState<string | null>(null)
  const [step, setStep] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [displayYear, setDisplayYear] = useState(0)

  const { site, error } = useSite(caseId)
  const assets = useStoryAssets(site, variableId)

  const firstYear = site?.years[0] ?? 2003
  const lastYear = site?.years[1] ?? 2024
  const yearRef = useRef(firstYear)

  const variable: SiteVariable | null = useMemo(() => {
    if (!site || site.variables.length === 0) return null
    return site.variables.find((entry) => entry.id === variableId) ?? site.variables[0]
  }, [site, variableId])

  // Pick a sensible default variable when a site loads (biggest change first).
  useEffect(() => {
    if (!site) return
    const preferred =
      [...site.variables].sort(
        (a, b) => Math.abs(b.sen_slope_per_decade ?? 0) - Math.abs(a.sen_slope_per_decade ?? 0),
      )[0] ?? null
    setVariableId(preferred ? preferred.id : null)
    yearRef.current = site.years[0]
    setDisplayYear(site.years[0])
    setStep(0)
    setPlaying(true)
  }, [site])

  // Year playback. The 3D layer reads the float through a ref, so React only
  // re-renders when the whole year changes.
  useEffect(() => {
    if (!playing) return
    let frame = 0
    let previous = performance.now()
    const tick = (now: number) => {
      const delta = Math.min((now - previous) / 1000, 0.1)
      previous = now
      yearRef.current += delta * PLAY_SPEED
      if (yearRef.current >= lastYear) yearRef.current = firstYear
      setDisplayYear(Math.floor(yearRef.current))
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [playing, firstYear, lastYear])

  const yearProgress = useCallback(() => yearRef.current - firstYear, [firstYear])

  const handleScrub = (year: number) => {
    setPlaying(false)
    yearRef.current = year
    setDisplayYear(year)
  }

  const hasFrames = assets.years.length > 1

  return (
    <div className="app">
      <header className="topbar">
        <div className="wordmark">
          <span className="mark" aria-hidden="true">
            ◎
          </span>
          <span className="wordmark-text">
            Earth Trend Detective
            <small>Is it the climate, or is it us?</small>
          </span>
        </div>
        <nav className="cases" aria-label="Case studies">
          {CASES.map((entry) => (
            <button
              key={entry.id}
              type="button"
              className={entry.id === caseId ? 'case case-active' : 'case'}
              aria-current={entry.id === caseId ? 'true' : undefined}
              onClick={() => setCaseId(entry.id)}
            >
              <span className="case-label">{entry.label}</span>
              <span className="case-where">{entry.where}</span>
            </button>
          ))}
        </nav>
      </header>

      <main className="stage">
        <section className="viewer" aria-label="Terrain view">
          <div className="viewer-canvas">
            {site && !error ? (
              <StoryScene
                site={site}
                assets={assets}
                yearProgress={yearProgress}
                showTrend={step >= 1}
              />
            ) : null}

            {!site && !error ? (
              <div className="viewer-message" role="status">
                <span className="spinner" aria-hidden="true" />
                <p>Loading the case…</p>
              </div>
            ) : null}

            {error ? (
              <div className="viewer-message viewer-error" role="alert">
                <p>
                  <strong>This case has no assets yet.</strong>
                </p>
                <p className="muted">
                  The data pipeline has to generate <code>sites/{caseId}/</code> first. Until
                  then, open the preview case.
                </p>
                <button type="button" className="primary" onClick={() => setCaseId('_example')}>
                  Open the preview case
                </button>
              </div>
            ) : null}

            {site && assets.loading && assets.base ? (
              <div className="loading-pill" role="status">
                <span className="spinner" aria-hidden="true" /> Loading layers…
              </div>
            ) : null}

            {site && assets.error ? (
              <div className="loading-pill loading-error" role="alert">
                {assets.error}
              </div>
            ) : null}
          </div>

          <div className="viewer-hud">
            <Timeline
              first={firstYear}
              last={lastYear}
              year={displayYear || firstYear}
              playing={playing}
              hasFrames={hasFrames}
              onScrub={handleScrub}
              onToggle={() => setPlaying((value) => !value)}
            />
            <ul className="legend" aria-label="Map legend">
              <li>
                <span className="swatch swatch-loss" aria-hidden="true" /> Losing
              </li>
              <li>
                <span className="swatch swatch-gain" aria-hidden="true" /> Gaining
              </li>
              <li>
                <span className="swatch swatch-nodata" aria-hidden="true" /> Not significant
              </li>
            </ul>
          </div>
        </section>

        {site && variable ? (
          <StoryPanel
            site={site}
            variable={variable}
            step={step}
            onSelectVariable={setVariableId}
            onStep={setStep}
          />
        ) : (
          <aside className="panel panel-empty" aria-label="Case details">
            <h1>Pick a case</h1>
            <p className="lede">
              Each case walks the same three questions: what is changing, is it real, and is it
              the climate?
            </p>
          </aside>
        )}
      </main>
    </div>
  )
}
