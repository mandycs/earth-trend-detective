'use client'

import dynamic from 'next/dynamic'
import Link from 'next/link'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { fetchSites } from '../explore/api'
import type { Site as ApiSite } from '../explore/types'
import { fmtPlace } from '../explore/format'
import { shortName } from '../../lib/cases'
import { CloseIcon } from '../../lib/Icons'
import { investigate } from './stream'
import type { InvEvent, InvPlace, Plan, StepLayer, StepState, ThenNowResult } from './types'
import type { MapLayerSpec } from './InvestigateMap'
import { StepResult } from './StepResult'
import styles from './investigate.module.css'

const InvestigateMap = dynamic(() => import('./InvestigateMap'), {
  ssr: false,
  loading: () => (
    <div className={styles.mapWrap}>
      <p className={styles.mapLoading}>Loading the map…</p>
    </div>
  ),
})

type Target = { kind: 'site'; id: string; name: string; lat: number; lon: number } | { kind: 'point'; lat: number; lon: number }

interface Run {
  place: InvPlace | null
  plan: Plan | null
  steps: StepState[]
  results: Record<string, unknown>
  error: string | null
  done: boolean
}

const SUGGESTIONS = [
  'Is the water here going down, and is it the climate?',
  'Is it getting hotter here?',
  'Has the land changed since 2003?',
]

interface LayerControl {
  visible: boolean
  opacity: number
  year?: number
}

interface StackEntry {
  spec: MapLayerSpec
  title: string
  source: string
  pictureOnly: boolean
  years?: number[]
}

function stepLayer(result: unknown): StepLayer | undefined {
  if (result && typeof result === 'object' && 'layer' in result) {
    const layer = (result as { layer: unknown }).layer
    if (layer && typeof layer === 'object' && 'kind' in layer) return layer as StepLayer
  }
  return undefined
}

export default function InvestigateView({ initialSite }: { initialSite?: string }) {
  const [sites, setSites] = useState<ApiSite[]>([])
  const [target, setTarget] = useState<Target | null>(null)
  const [question, setQuestion] = useState(SUGGESTIONS[0])
  const [run, setRun] = useState<Run | null>(null)
  const [controls, setControls] = useState<Record<string, LayerControl>>({})
  const [clock, setClock] = useState(0)
  const controller = useRef<AbortController | null>(null)
  const caseRef = useRef<HTMLElement>(null)
  const hasPlan = Boolean(run?.plan)

  // Bring the live plan into view as soon as it exists.
  useEffect(() => {
    if (hasPlan) caseRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [hasPlan])

  useEffect(() => {
    const c = new AbortController()
    fetchSites(c.signal).then((list) => {
      setSites(list)
      const first = list.find((s) => s.id === initialSite)
      if (first) setTarget({ kind: 'site', id: first.id, name: first.name, lat: first.point[1], lon: first.point[0] })
    })
    return () => c.abort()
  }, [initialSite])

  // Ticks once a second while a step runs, for the elapsed-time counter.
  const running = run?.steps.some((s) => s.status === 'running') ?? false
  useEffect(() => {
    if (!running) return
    const id = window.setInterval(() => setClock(performance.now()), 1000)
    return () => window.clearInterval(id)
  }, [running])

  const onEvent = useCallback((e: InvEvent) => {
    setRun((prev) => {
      if (!prev) return prev
      switch (e.event) {
        case 'place':
          return { ...prev, place: e.data }
        case 'plan':
          return { ...prev, plan: e.data, steps: e.data.steps.map(() => ({ status: 'pending' as const })) }
        case 'step_start': {
          const steps = [...prev.steps]
          steps[e.data.index] = { status: 'running', startedAt: performance.now() }
          return { ...prev, steps }
        }
        case 'step_done': {
          const steps = [...prev.steps]
          steps[e.data.index] = { status: 'done', seconds: e.data.seconds, result: e.data.result }
          return { ...prev, steps, results: { ...prev.results, [e.data.id]: e.data.result } }
        }
        case 'step_failed': {
          const steps = [...prev.steps]
          steps[e.data.index] = { status: 'failed', message: e.data.message }
          return { ...prev, steps }
        }
        case 'done':
          return { ...prev, done: true }
        default:
          return prev
      }
    })
  }, [])

  const start = async () => {
    if (!target || !question.trim()) return
    controller.current?.abort()
    const c = new AbortController()
    controller.current = c
    setControls({})
    setRun({ place: null, plan: null, steps: [], results: {}, error: null, done: false })
    const body =
      target.kind === 'site'
        ? { question: question.trim(), site_id: target.id }
        : { question: question.trim(), lat: Number(target.lat.toFixed(4)), lon: Number(target.lon.toFixed(4)) }
    try {
      await investigate(body, onEvent, c.signal)
      setRun((prev) => (prev && !prev.done && !c.signal.aborted ? { ...prev, done: true } : prev))
    } catch (cause) {
      if (c.signal.aborted) return
      setRun((prev) =>
        prev ? { ...prev, error: cause instanceof Error ? cause.message : 'The investigation stopped. Try again.' } : prev,
      )
    }
  }

  const pickPoint = useCallback((lat: number, lon: number) => {
    setTarget({ kind: 'point', lat, lon })
  }, [])

  // Map layers, one per step that returned something drawable.
  const stack: StackEntry[] = useMemo(() => {
    if (!run) return []
    const out: StackEntry[] = []
    const water = stepLayer(run.results.water_storage)
    if (water?.kind === 'footprint') {
      out.push({
        spec: { id: 'grace', kind: 'footprint', center: water.center, widthKm: water.width_km, visible: true, opacity: 1 },
        title: `What GRACE sees: about ${water.width_km} km across`,
        source: 'GRACE/GRACE-FO, NASA JPL',
        pictureOnly: false,
      })
    }
    const cover = stepLayer(run.results.land_cover)
    if (cover?.kind === 'wms') {
      const years = cover.years
      out.push({
        spec: { id: 'landcover', kind: 'wms', layer: cover.layer, year: years[years.length - 1], visible: true, opacity: 0.75 },
        title: 'Land cover',
        source: 'MODIS MCD12Q1, NASA GIBS',
        pictureOnly: false,
        years,
      })
    }
    const pictures = run.results.then_and_now as ThenNowResult | undefined
    const side = pictures?.after ?? pictures?.before
    if (pictures && side) {
      const years = [pictures.before?.year, pictures.after?.year].filter((y): y is number => y != null)
      out.push({
        spec: { id: 'thennow', kind: 'image', url: side.url, bbox: pictures.bbox, visible: true, opacity: 1 },
        title: 'Satellite picture',
        source: 'MODIS Terra true colour, NASA GIBS',
        pictureOnly: true,
        years,
      })
    }
    return out.map((entry) => {
      const ctl = controls[entry.spec.id]
      if (!ctl) return entry
      let spec = { ...entry.spec, visible: ctl.visible, opacity: ctl.opacity } as MapLayerSpec
      if (ctl.year != null && spec.kind === 'wms') spec = { ...spec, year: ctl.year }
      if (ctl.year != null && spec.kind === 'image' && pictures) {
        const pick = pictures.before?.year === ctl.year ? pictures.before : pictures.after
        if (pick) spec = { ...spec, url: pick.url }
      }
      return { ...entry, spec }
    })
  }, [run, controls])

  const focusBbox = useMemo(() => {
    const pictures = run?.results.then_and_now as ThenNowResult | undefined
    if (pictures?.bbox) return pictures.bbox
    const cover = stepLayer(run?.results.land_cover)
    return cover?.kind === 'wms' ? cover.bbox : null
  }, [run])

  const setControl = (id: string, patch: Partial<LayerControl>, base: MapLayerSpec) =>
    setControls((prev) => {
      const current = prev[id] ?? { visible: base.visible, opacity: base.opacity }
      return { ...prev, [id]: { ...current, ...patch } }
    })

  const place = run?.place ?? null
  const years: [number, number] = place?.years ?? [2003, 2024]
  const markerPlace = target ? { lat: target.lat, lon: target.lon } : null
  const busy = Boolean(run && !run.done && !run.error)

  return (
    <div className={styles.shell}>
      <header className={styles.bar}>
        <Link href="/" className={`${styles.wordmark} wide`}>
          Earth Trend Detective
        </Link>
        <nav className={styles.nav} aria-label="Main">
          <Link href="/story/lake_mead">Solved cases</Link>
          <Link href="/explore">Explore</Link>
        </nav>
      </header>

      <div className={styles.layout}>
        <div className={styles.mapCol}>
          <InvestigateMap place={markerPlace} layers={stack.map((s) => s.spec)} onPick={pickPoint} focusBbox={focusBbox} />
          {stack.length > 0 ? (
            <section className={styles.stack} aria-label="Map layers">
              {stack.map((entry) => (
                <div key={entry.spec.id} className={styles.layerRow}>
                  <label className={styles.layerToggle}>
                    <input
                      type="checkbox"
                      checked={entry.spec.visible}
                      onChange={(e) => setControl(entry.spec.id, { visible: e.target.checked }, entry.spec)}
                    />
                    <span>
                      <strong>{entry.title}</strong>
                      <span className={styles.layerSource}>
                        {entry.source}
                        {entry.pictureOnly ? ' · a picture, not a measurement' : ''}
                      </span>
                    </span>
                  </label>
                  <div className={styles.layerTools}>
                    {entry.years && entry.years.length > 1 ? (
                      <div className={styles.years} role="radiogroup" aria-label={`${entry.title} year`}>
                        {entry.years.map((y) => {
                          const current =
                            entry.spec.kind === 'wms'
                              ? entry.spec.year === y
                              : (controls[entry.spec.id]?.year ?? entry.years?.[entry.years.length - 1]) === y
                          return (
                            <button
                              key={y}
                              type="button"
                              role="radio"
                              aria-checked={current}
                              className={current ? styles.yearOn : styles.year}
                              onClick={() => setControl(entry.spec.id, { year: y }, entry.spec)}
                            >
                              {y}
                            </button>
                          )
                        })}
                      </div>
                    ) : null}
                    <label className={styles.opacity}>
                      <span className="sr-only">{entry.title} opacity</span>
                      <input
                        type="range"
                        min={0}
                        max={1}
                        step={0.05}
                        value={entry.spec.opacity}
                        onChange={(e) => setControl(entry.spec.id, { opacity: Number(e.target.value) }, entry.spec)}
                      />
                    </label>
                  </div>
                </div>
              ))}
            </section>
          ) : null}
        </div>

        <aside className={styles.panel} aria-label="Investigation">
          <div className={styles.ask}>
            <h1 className={`${styles.title} narrow`}>Ask the detective</h1>
            <p className={styles.lede}>
              Pick a place and ask a question. The detective plans its checks from a fixed list of NASA data, runs
              them one by one, and shows each answer on the map.
            </p>

            <div className={styles.where}>
              <h2 className={styles.label}>Where</h2>
              {target ? (
                <div className={styles.targetRow}>
                  <div>
                    <p className={`${styles.targetName} narrow`}>
                      {target.kind === 'site' ? shortName(target.name) : 'A point on the map'}
                    </p>
                    <p className={styles.coords}>{fmtPlace(target.lat, target.lon)}</p>
                  </div>
                  <button type="button" className={styles.iconButton} onClick={() => setTarget(null)} aria-label="Clear the place">
                    <CloseIcon />
                  </button>
                </div>
              ) : (
                <p className={styles.note}>Click the map, or start with a solved case:</p>
              )}
              {sites.length > 0 ? (
                <div className={styles.sites}>
                  {sites.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      aria-pressed={target?.kind === 'site' && target.id === s.id}
                      className={target?.kind === 'site' && target.id === s.id ? styles.siteOn : styles.site}
                      onClick={() => setTarget({ kind: 'site', id: s.id, name: s.name, lat: s.point[1], lon: s.point[0] })}
                    >
                      {shortName(s.name)}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>

            <form
              className={styles.form}
              onSubmit={(e) => {
                e.preventDefault()
                void start()
              }}
            >
              <label htmlFor="question" className={styles.label}>
                Your question
              </label>
              <textarea
                id="question"
                rows={2}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                maxLength={300}
              />
              <div className={styles.suggestions}>
                {SUGGESTIONS.map((s) => (
                  <button key={s} type="button" className={styles.suggestion} onClick={() => setQuestion(s)}>
                    {s}
                  </button>
                ))}
              </div>
              <button type="submit" className="btn btn-primary" disabled={!target || !question.trim() || busy}>
                {busy ? (
                  <>
                    <span className="spinner" aria-hidden="true" /> Investigating…
                  </>
                ) : (
                  'Investigate'
                )}
              </button>
              {!target ? <p className={styles.note}>Pick a place first: click the map or a solved case.</p> : null}
            </form>
          </div>

          {run ? (
            <section ref={caseRef} className={styles.case} aria-live="polite" aria-label="Investigation progress">
              {run.place ? (
                <h2 className={`${styles.caseTitle} narrow`}>{run.place.id === 'point' ? fmtPlace(run.place.lat, run.place.lon) : shortName(run.place.name)}</h2>
              ) : null}
              {!run.plan && !run.error ? (
                <p className={styles.thinking}>
                  <span className="spinner" aria-hidden="true" /> Planning the investigation…
                </p>
              ) : null}
              {run.plan ? (
                <>
                  <p className={styles.note}>
                    {run.plan.source === 'llm'
                      ? 'Plan chosen by an AI from a fixed menu of NASA checks.'
                      : 'Standard plan for this kind of place.'}
                  </p>
                  <ol className={styles.steps}>
                    {run.plan.steps.map((step, index) => {
                      const state = run.steps[index] ?? { status: 'pending' }
                      const elapsed =
                        state.status === 'running' ? Math.max(0, Math.round(((clock || performance.now()) - state.startedAt) / 1000)) : null
                      return (
                        <li key={`${step.id}-${index}`} className={`${styles.step} ${styles[`step_${state.status}`] ?? ''}`}>
                          <div className={styles.stepHead}>
                            <span className={styles.stepMark} aria-hidden="true">
                              {state.status === 'running' ? <span className="spinner" /> : null}
                            </span>
                            <div>
                              <h3>{step.title}</h3>
                              <p className={styles.why}>{step.why}</p>
                            </div>
                            <span className={styles.stepTime}>
                              {state.status === 'done'
                                ? `${state.seconds < 1 ? '<1' : Math.round(state.seconds)} s`
                                : state.status === 'running'
                                  ? `${elapsed} s / ~${step.seconds} s`
                                  : state.status === 'failed'
                                    ? 'failed'
                                    : `~${step.seconds} s`}
                            </span>
                          </div>
                          {state.status === 'done' ? (
                            <StepResult id={step.id} result={state.result} years={years} name={run.place?.name ?? 'this place'} />
                          ) : null}
                          {state.status === 'failed' ? (
                            <p className={styles.failed} role="alert">
                              {state.message} The other checks still count.
                            </p>
                          ) : null}
                        </li>
                      )
                    })}
                  </ol>
                </>
              ) : null}
              {run.error ? (
                <div className={styles.errorBox} role="alert">
                  <p>{run.error}</p>
                  <button type="button" className="btn" onClick={() => void start()}>
                    Try again
                  </button>
                </div>
              ) : null}
              {run.done && !run.error ? (
                <p className={styles.note}>
                  Investigation complete. The share the climate leaves unexplained is a clue, not an attribution.
                </p>
              ) : null}
            </section>
          ) : null}
        </aside>
      </div>
    </div>
  )
}
