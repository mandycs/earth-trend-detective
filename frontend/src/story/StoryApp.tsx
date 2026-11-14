'use client'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { mapLayers, useLegend, useSite, useStoryAssets } from './useSite'
import type { MapLayer } from './useSite'
import { StoryScene } from './StoryScene'
import { StoryPanel } from './StoryPanel'
import { Timeline } from './Timeline'
import type { SiteVariable } from './types'
import { CASE_IDS, leadVariable, shortName } from '../lib/cases'

const CASE_LABELS: Record<string, string> = {
  lake_mead: 'Lake Mead',
  aletsch: 'Aletsch',
  donana: 'Doñana',
}

const PLAY_SPEED = 1.6 // years per second

function layerName(layer: MapLayer, label: string | undefined, single: boolean): string {
  const how = layer.kind === 'year' ? 'Year by year' : 'Trend'
  if (single) return how
  return `${label ?? layer.variable.replace(/_/g, ' ')}: ${how.toLowerCase()}`
}

export default function StoryApp({ caseId }: { caseId: string }) {
  const { site, error } = useSite(caseId)
  const [variableId, setVariableId] = useState<string | null>(null)
  const [layerKey, setLayerKey] = useState<string>('none')
  const [step, setStep] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [displayYear, setDisplayYear] = useState(0)
  const [exaggeration, setExaggeration] = useState<number | null>(null)

  const layers = useMemo(() => mapLayers(site), [site])
  const singleVar = new Set(layers.map((l) => l.variable)).size <= 1
  const layer = layers.find((l) => l.key === layerKey) ?? null
  const assets = useStoryAssets(site, layer)
  const legend = useLegend(site?.id ?? null, layer?.legendFile ?? null)
  const yearLegend = useLegend(site?.id ?? null, layers.find((l) => l.kind === 'year')?.legendFile ?? null)

  const firstYear = site?.years[0] ?? 2003
  const lastYear = site?.years[1] ?? 2024
  const yearRef = useRef(firstYear)

  const variable: SiteVariable | null = useMemo(() => {
    if (!site || site.variables.length === 0) return null
    return site.variables.find((entry) => entry.id === variableId) ?? leadVariable(site)
  }, [site, variableId])

  // New case: lead record on the timeline, yearly map layer if there is one, play.
  useEffect(() => {
    if (!site) return
    setVariableId(leadVariable(site)?.id ?? null)
    const all = mapLayers(site)
    setLayerKey((all.find((l) => l.kind === 'year') ?? all[0])?.key ?? 'none')
    setExaggeration(null)
    yearRef.current = site.years[0]
    setDisplayYear(site.years[0])
    setStep(0)
    setPlaying(!window.matchMedia('(prefers-reduced-motion: reduce)').matches)
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
      if (yearRef.current > lastYear + 0.6) yearRef.current = firstYear
      setDisplayYear(Math.min(Math.floor(yearRef.current), lastYear))
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [playing, firstYear, lastYear])

  const yearProgress = useCallback(() => Math.min(yearRef.current, lastYear) - firstYear, [firstYear, lastYear])

  const handleScrub = (year: number) => {
    setPlaying(false)
    yearRef.current = year
    setDisplayYear(year)
  }

  const showYears = layer?.kind === 'year' && assets.years.length > 1
  const vx = exaggeration ?? site?.vertical_exaggeration ?? 3

  return (
    <div className="st">
      <header className="st-bar">
        <Link href="/" className="st-wordmark wide">
          Earth Trend Detective
        </Link>
        <nav className="st-cases" aria-label="Cases">
          {CASE_IDS.map((id) => (
            <Link key={id} href={`/story/${id}`} className={id === caseId ? 'st-case st-case-on' : 'st-case'} aria-current={id === caseId ? 'page' : undefined}>
              {CASE_LABELS[id] ?? id}
            </Link>
          ))}
        </nav>
        <Link href="/explore" className="st-explore">
          <span>
            Explore<span className="st-hide-sm"> any point</span>
          </span>
          <span aria-hidden="true">→</span>
        </Link>
      </header>

      <main className="st-stage">
        <section className="st-viewer" aria-label="3D terrain">
          <div className="st-canvas">
            {site && !error ? (
              <StoryScene site={site} assets={assets} yearProgress={yearProgress} showYears={showYears} exaggeration={vx} />
            ) : null}

            {!site && !error ? (
              <div className="st-message" role="status">
                <span className="spinner" aria-hidden="true" /> Loading the case…
              </div>
            ) : null}

            {error || assets.error ? (
              <div className="st-message" role="alert">
                <p>
                  <strong>This case could not load.</strong>
                </p>
                <p>Reload the page. If it keeps failing, open another case or explore a point on the map.</p>
                <Link href="/explore" className="btn">
                  Explore any point
                </Link>
              </div>
            ) : null}

            {site && !assets.error && assets.loading ? (
              <div className="st-loading" role="status">
                <span className="spinner" aria-hidden="true" /> Loading the terrain and satellite layers…
              </div>
            ) : null}

            {site ? (
              <div className="st-relief">
                <span>Heights ×{vx}</span>
                <button type="button" onClick={() => setExaggeration(Math.max(1, vx - 1))} aria-label="Flatten the relief" disabled={vx <= 1}>
                  −
                </button>
                <button type="button" onClick={() => setExaggeration(Math.min(12, vx + 1))} aria-label="Raise the relief" disabled={vx >= 12}>
                  +
                </button>
              </div>
            ) : null}
          </div>

          {site ? (
            <div className="st-layers">
              <div className="st-layer-pick" role="radiogroup" aria-label="What the map shows">
                <button
                  type="button"
                  role="radio"
                  aria-checked={layerKey === 'none'}
                  className={layerKey === 'none' ? 'st-chip st-chip-on' : 'st-chip'}
                  onClick={() => setLayerKey('none')}
                >
                  Satellite
                </button>
                {layers.map((l) => (
                  <button
                    key={l.key}
                    type="button"
                    role="radio"
                    aria-checked={layerKey === l.key}
                    className={layerKey === l.key ? 'st-chip st-chip-on' : 'st-chip'}
                    onClick={() => setLayerKey(l.key)}
                  >
                    {layerName(l, l.kind === 'year' ? yearLegend?.label : legend?.label ?? yearLegend?.label, singleVar)}
                  </button>
                ))}
              </div>
              {layer && legend ? (
                <div className="st-legend">
                  <span className="st-legend-title">
                    {legend.label}
                    {layer.kind === 'year' ? ', against its usual' : `, ${legend.unit}`}
                  </span>
                  <span className="st-ramp" aria-hidden="true">
                    {legend.stops.map((c) => (
                      <span key={c} style={{ background: c }} />
                    ))}
                  </span>
                  <span className="st-ramp-ends">
                    <span>{legend.legend.less}</span>
                    <span>{legend.legend.more}</span>
                  </span>
                  {layer.kind === 'trend' && legend.share_significant != null ? (
                    <span className="st-legend-note">
                      Faded areas: change too small to call. Clear trend on {Math.round(legend.share_significant * 100)}% of
                      the area.
                    </span>
                  ) : null}
                </div>
              ) : null}
              {layers.length === 0 ? (
                <p className="st-legend-note">
                  No per-pixel map for this case yet. The timeline shows the records for the whole area.
                </p>
              ) : null}
            </div>
          ) : null}

          <Timeline
            first={firstYear}
            last={lastYear}
            year={displayYear || firstYear}
            playing={playing}
            variable={variable}
            mapFollows={showYears}
            onScrub={handleScrub}
            onToggle={() => setPlaying((value) => !value)}
          />
        </section>

        {site && variable ? (
          <StoryPanel site={site} variable={variable} step={step} onSelectVariable={setVariableId} onStep={setStep} />
        ) : (
          <aside className="sp sp-empty" aria-label="Case details">
            <p>{error ? 'Pick another case above.' : `Opening ${CASE_LABELS[caseId] ?? shortName(caseId)}…`}</p>
          </aside>
        )}
      </main>
    </div>
  )
}
