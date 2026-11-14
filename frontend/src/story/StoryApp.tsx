'use client'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type * as THREE from 'three'
import { readFrame, useSite, useStoryAssets } from './useSite'
import { StoryScene } from './StoryScene'
import { DroneScene } from './drone/DroneScene'
import { useDetailAssets, useDetailInfo, usePhoto } from './drone/useDetail'
import type { DetailInfo } from './drone/useDetail'
import { useCaseLayers } from './useTimeline'
import { StoryPanel } from './StoryPanel'
import { Timeline } from './Timeline'
import type { SiteVariable } from './types'
import { bboxWidthMeters } from './types'
import { CASE_IDS, fmt, leadVariable, shortName } from '../lib/cases'
import { LayerPanel } from './layers/LayerPanel'
import { Curtain } from './layers/Curtain'
import { layerTexture } from './layers/assets'
import type { Overlay } from './Terrain'
import { pairFromLayers } from '../lib/beforeAfterPair'
import type { BeforeAfterPair } from '../lib/beforeAfterPair'
import type { StackEntry } from './layers/model'
import { defaultStack, fileFor, yearStatus } from './layers/model'
import { useOverlays } from './layers/useOverlays'
import { valueAt } from './layers/assets'
import { sampleHeight } from './heights'
import { API_URL } from '../features/explore/api'
import { CHAPTER_NAMES, chaptersFor } from '../lib/chapters'

/** Seconds each documentary chapter stays on screen when playing. */
const CHAPTER_SECONDS = 9

const CASE_LABELS: Record<string, string> = {
  lake_mead: 'Lake Mead',
  aletsch: 'Aletsch',
  donana: 'Doñana',
}

/** Seconds per year while playing: the frame holds, then moves to the next. */
const YEAR_SECONDS = 1.8

/** Which aerial photo stands for a year, and how to say it honestly. */
function photoFor(info: DetailInfo | null, year: number): { file: string; words: string } | null {
  const photos = info?.photos_by_year
  if (!photos) return null
  const entry = photos[String(year)]
  if (entry) {
    return {
      file: entry.file,
      words: entry.same_as ? `No new flight in ${year}: newest photo available is ${entry.same_as}` : `Aerial photo from ${year}`,
    }
  }
  const flown = Object.keys(photos).map(Number).sort((a, b) => a - b)
  const before = flown.filter((y) => y < year).pop()
  const pick = before ?? flown.find((y) => y > year)
  if (pick == null) return null
  return { file: photos[String(pick)].file, words: `No flight in ${year}: showing the ${pick} photo` }
}

function frameWords(texture: THREE.Texture | undefined): string | null {
  const read = texture ? readFrame(texture) : null
  if (!read) return null
  if (read.warmer > 0.6) return 'warmer than usual over most of the area'
  if (read.cooler > 0.6) return 'cooler than usual over most of the area'
  if (read.warmer > read.cooler + 0.15) return 'mixed, leaning warmer than usual'
  if (read.cooler > read.warmer + 0.15) return 'mixed, leaning cooler than usual'
  return 'close to usual, warmer in places and cooler in others'
}

interface IdentifyResult {
  year: number
  elevation: number | null
  rows: Array<{ title: string; text: string }>
}

export default function StoryApp({ caseId }: { caseId: string }) {
  const { site, error } = useSite(caseId)
  const detailInfo = useDetailInfo(caseId)
  const [drone, setDrone] = useState(false)
  const detail = useDetailAssets(caseId, detailInfo, drone)
  // The flying help shows for a few seconds on entering the drone, then leaves the view clean.
  const [droneHelp, setDroneHelp] = useState(false)
  useEffect(() => {
    if (!drone || !detail.assets) return
    setDroneHelp(true)
    const t = window.setTimeout(() => setDroneHelp(false), 6000)
    return () => window.clearTimeout(t)
  }, [drone, detail.assets])
  const { timeline, layers } = useCaseLayers(caseId)
  const [stack, setStack] = useState<StackEntry[]>([])
  const [whys, setWhys] = useState<Record<string, string>>({})
  const [caption, setCaption] = useState<string | null>(null)
  const [asking, setAsking] = useState(false)
  const [askError, setAskError] = useState<string | null>(null)
  const [identify, setIdentify] = useState(false)
  const [compareId, setCompareId] = useState<string | null>(null)
  const [split, setSplit] = useState(0.5)
  // Instrument layout puts a reading column over the left of the map on wide screens.
  const [wide, setWide] = useState(false)
  useEffect(() => {
    const q = window.matchMedia('(min-width: 1101px)')
    const on = () => setWide(q.matches)
    on()
    q.addEventListener('change', on)
    return () => q.removeEventListener('change', on)
  }, [])
  const [pair, setPair] = useState<{ id: string; value: BeforeAfterPair | null; textures: [Overlay, Overlay] | null }>({ id: '', value: null, textures: null })
  const [picked, setPicked] = useState<IdentifyResult | null>(null)
  const [noMapFor, setNoMapFor] = useState<string | null>(null)
  const [altitude, setAltitude] = useState<number | null>(null)
  const [variableId, setVariableId] = useState<string | null>(null)
  const [step, setStep] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [displayYear, setDisplayYear] = useState(0)
  // Documentary first (DESIGN.md): three chapters, then free exploring.
  const [mode, setMode] = useState<'doc' | 'free'>('doc')
  const [chapter, setChapter] = useState(0)
  const [chapterT, setChapterT] = useState(0)
  const [docPlaying, setDocPlaying] = useState(true)

  const assets = useStoryAssets(site, null)

  const firstYear = site?.years[0] ?? 2003
  const lastYear = site?.years[1] ?? 2024
  const clockRef = useRef(0)

  const variable: SiteVariable | null = useMemo(() => {
    if (!site || site.variables.length === 0) return null
    return site.variables.find((entry) => entry.id === variableId) ?? leadVariable(site)
  }, [site, variableId])

  // New case: lead record, all data layers off, play.
  useEffect(() => {
    if (!site) return
    setVariableId(leadVariable(site)?.id ?? null)
    setDrone(false)
    setNoMapFor(null)
    setPicked(null)
    setWhys({})
    setCaption(null)
    clockRef.current = 0
    setDisplayYear(site.years[0])
    setStep(0)
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    setPlaying(false)
    setMode('doc')
    setChapter(0)
    setChapterT(0)
    setDocPlaying(!reduced)
  }, [site])

  // Documentary clock: chapter 1 runs the years, then each chapter holds its subtitle.
  useEffect(() => {
    if (mode !== 'doc' || !docPlaying || !site) return
    let frame = 0
    let previous = performance.now()
    const tick = (now: number) => {
      const delta = Math.min((now - previous) / 1000, 0.1)
      previous = now
      setChapterT((t) => {
        const next = t + delta / CHAPTER_SECONDS
        if (next >= 1) {
          setChapter((c) => {
            if (c >= CHAPTER_NAMES.length - 1) {
              setDocPlaying(false)
              return c
            }
            return c + 1
          })
          return chapter >= CHAPTER_NAMES.length - 1 ? 1 : 0
        }
        return next
      })
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [mode, docPlaying, site, chapter])

  // In chapter 1 the year sweeps the record; later chapters talk about the whole period.
  useEffect(() => {
    if (mode !== 'doc' || !site) return
    const [a, b] = site.years
    setDisplayYear(chapter === 0 ? Math.min(b, a + Math.floor(chapterT * (b - a + 1))) : b)
  }, [mode, chapter, chapterT, site])

  const enterFree = () => {
    setMode('free')
    setDocPlaying(false)
  }
  const nextChapter = () => {
    if (chapter >= CHAPTER_NAMES.length - 1) {
      enterFree()
      return
    }
    setChapter((c) => c + 1)
    setChapterT(0)
  }

  useEffect(() => {
    setStack(defaultStack(layers))
  }, [layers])

  // Year playback: one year at a time, held long enough to read.
  useEffect(() => {
    if (!playing) return
    let frame = 0
    let previous = performance.now()
    const tick = (now: number) => {
      const delta = Math.min((now - previous) / 1000, 0.1)
      previous = now
      const span = lastYear - firstYear
      clockRef.current += delta
      if (clockRef.current > (span + 2) * YEAR_SECONDS) clockRef.current = 0
      const index = Math.min(Math.floor(clockRef.current / YEAR_SECONDS), span)
      setDisplayYear(firstYear + index)
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [playing, firstYear, lastYear])

  const handleScrub = (year: number) => {
    setPlaying(false)
    clockRef.current = (year - firstYear) * YEAR_SECONDS
    setDisplayYear(year)
  }

  const shownYear = displayYear || firstYear

  /** Picking a record turns on its map layer (record_map), or says there is none. */
  const selectRecord = (id: string) => {
    setVariableId(id)
    const mapId = timeline?.record_map?.[id] ?? null
    if (mapId && stack.some((s) => s.id === mapId)) {
      const others = stack.filter((s) => s.id !== mapId)
      const target = stack.find((s) => s.id === mapId) as StackEntry
      setStack([{ ...target, on: true }, ...others])
      setNoMapFor(null)
    } else {
      setNoMapFor(id)
    }
  }

  /** Turning a layer on puts its record on the timeline. */
  const changeStack = (incoming: StackEntry[]) => {
    const newlyOn = incoming.find((s) => s.on && !stack.find((p) => p.id === s.id)?.on)
    const isColoured = (id: string) => layers.find((l) => l.id === id)?.blend === 'normal'
    // One coloured layer at a time; a second one is seen through the curtain.
    const next =
      newlyOn && isColoured(newlyOn.id)
        ? incoming.map((s) => (s.id !== newlyOn.id && s.on && isColoured(s.id) ? { ...s, on: false } : s))
        : incoming
    if (newlyOn && newlyOn.id === compareId) setCompareId(null)
    if (!next.some((s) => s.on && isColoured(s.id))) setCompareId(null)
    setStack(next)
    if (newlyOn) {
      const def = layers.find((l) => l.id === newlyOn.id)
      if (def?.variable && site?.variables.some((v) => v.id === def.variable)) {
        setVariableId(def.variable)
        setNoMapFor(null)
      }
    }
  }

  const ask = async (question: string) => {
    setAsking(true)
    setAskError(null)
    try {
      const response = await fetch(`${API_URL}/layers/suggest`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ site_id: caseId, question, mode: drone ? 'drone' : 'overview', year: shownYear }),
        signal: AbortSignal.timeout(45_000),
      })
      if (!response.ok) throw new Error(String(response.status))
      const body = (await response.json()) as {
        stack?: Array<{ id: string; opacity?: number; why?: string }>
        year?: number | null
        caption?: string
      }
      const suggested = body.stack ?? []
      const known = new Set(stack.map((s) => s.id))
      const chosen = suggested.filter((s) => known.has(s.id))
      const rest = stack.filter((s) => !chosen.some((c) => c.id === s.id)).map((s) => ({ ...s, on: false }))
      setStack([
        ...chosen.map((c) => ({ id: c.id, on: true, opacity: c.opacity ?? 0.85 })),
        ...rest,
      ])
      const nextWhys: Record<string, string> = {}
      for (const s of suggested) {
        if (!s.why) continue
        nextWhys[known.has(s.id) ? s.id : '__base'] = s.why
      }
      setWhys(nextWhys)
      setCaption(body.caption ?? null)
      if (body.year && body.year >= firstYear && body.year <= lastYear) handleScrub(body.year)
      const firstVar = chosen.map((c) => layers.find((l) => l.id === c.id)?.variable).find((v) => v && site?.variables.some((x) => x.id === v))
      if (firstVar) setVariableId(firstVar)
    } catch {
      setAskError('The map could not answer. Check that the backend is running, or switch layers on by hand.')
    } finally {
      setAsking(false)
    }
  }

  // Close-up placement inside the case's picture, for draping layers in the drone.
  const detailRect = useMemo<[number, number, number, number] | undefined>(() => {
    if (!site || !detailInfo) return undefined
    const [W, S, E, N] = site.bbox
    const [w, s, e, n] = detailInfo.bbox
    return [(w - W) / (E - W), (s - S) / (N - S), (e - w) / (E - W), (n - s) / (N - S)]
  }, [site, detailInfo])

  const overlays = useOverlays(caseId, layers, stack, shownYear, undefined, compareId)
  const droneOverlays = useOverlays(caseId, layers, stack, shownYear, detailRect, compareId)

  // Then-and-now pair (2003 | 2024) for the documentary's first chapter.
  useEffect(() => {
    let alive = true
    fetch(`/sites/${caseId}/layers.json`)
      .then((r) => (r.ok ? r.json() : null))
      .then(async (file) => {
        const value = pairFromLayers(caseId, file)
        if (!value) {
          if (alive) setPair({ id: caseId, value: null, textures: null })
          return
        }
        const [a, b] = await Promise.all([layerTexture(value.before.src, false), layerTexture(value.after.src, false)])
        if (alive)
          setPair({
            id: caseId,
            value,
            textures: [
              { texture: a, opacity: 1, blend: 'normal', side: -1 },
              { texture: b, opacity: 1, blend: 'normal', side: 1 },
            ],
          })
      })
      .catch(() => alive && setPair({ id: caseId, value: null, textures: null }))
    return () => {
      alive = false
    }
  }, [caseId])
  const docPair = pair.id === caseId ? pair : null
  const docCurtain = mode === 'doc' && chapter === 0 && docPair?.textures ? docPair : null
  // In chapter 1 the curtain sweeps from the first picture to the last.
  const docSplit = 0.85 - 0.7 * Math.min(1, chapterT * 1.15)

  // Words for the trend-tested yearly anomaly layer, read back from its colours.
  const anomalyLayer = stack.find((s) => s.on && layers.find((l) => l.id === s.id)?.id.startsWith('year_'))
  const anomalyDef = anomalyLayer ? layers.find((l) => l.id === anomalyLayer.id) : undefined
  const anomalyIndex = anomalyLayer ? stack.filter((s) => s.on).findIndex((s) => s.id === anomalyLayer.id) : -1
  const anomalyTexture = anomalyIndex >= 0 ? overlays[overlays.length - 1 - anomalyIndex]?.texture : undefined
  const anomalyWords = useMemo(() => frameWords(anomalyTexture), [anomalyTexture])

  const onPick = useCallback(
    async (uv: THREE.Vector2) => {
      if (!identify || !site) return
      // Texture space of the case picture: in the drone, map the close-up into it.
      const r = drone && detailRect ? detailRect : [0, 0, 1, 1]
      const u = r[0] + uv.x * r[2]
      const v = r[1] + uv.y * r[3]
      const grid = drone ? detail.assets?.grid : assets.grid
      const elevation = grid ? sampleHeight(grid, uv.x, 1 - uv.y) : null
      const rows: IdentifyResult['rows'] = []
      for (const entry of stack.filter((s) => s.on)) {
        const def = layers.find((l) => l.id === entry.id)
        if (!def) continue
        if (def.valueFile && def.valueScale != null && def.valueOffset != null) {
          const value = await valueAt(`/sites/${caseId}/${def.valueFile}`, u, v, def.valueScale, def.valueOffset)
          let tested = ''
          if (value != null && def.significanceFile) {
            const flag = await valueAt(`/sites/${caseId}/${def.significanceFile}`, u, v, 1, 0)
            tested = flag === 2 ? ', a real trend here' : flag === 1 ? ', too small to call here' : ''
          }
          rows.push({
            title: def.title,
            text: value == null ? 'no data here' : `${fmt(value, true)} ${def.legend?.unit ?? ''}${tested}`.trim(),
          })
          continue
        }
        if (!def.valuePattern || def.valueScale == null || def.valueOffset == null) {
          rows.push({ title: def.title, text: 'a picture, no values to read' })
          continue
        }
        if (def.years && !def.years.includes(shownYear)) {
          rows.push({ title: def.title, text: `no data for ${shownYear}` })
          continue
        }
        const file = def.valuePattern.replace('{YYYY}', String(shownYear))
        const value = await valueAt(`/sites/${caseId}/${file}`, u, v, def.valueScale, def.valueOffset)
        rows.push({
          title: def.title,
          text:
            value == null
              ? `no clear view here in ${shownYear}`
              : /usual/.test(def.legend?.more ?? '')
                ? `${fmt(value, true)} ${def.legend?.unit ?? ''} against its usual`.replace(/\s+/g, ' ')
                : `${fmt(value)} ${def.legend?.unit ?? ''}`.trim(),
        })
      }
      if (variable && variable.series) {
        const point = variable.series.find((p) => p.year === shownYear)
        rows.push({
          title: `${variable.label} (one number for ${variable.footprint?.label ?? 'the whole area'})`,
          text: point ? `${fmt(point.value)} ${variable.unit}` : `no value for ${shownYear}`,
        })
      }
      setPicked({ year: shownYear, elevation, rows })
    },
    [identify, site, drone, detailRect, detail.assets, assets.grid, stack, layers, shownYear, caseId, variable],
  )

  // Lake Mead close-up: the water level for the year.
  const levels = detailInfo?.water_level_m_by_year ?? null
  const lakeLevel: SiteVariable | null =
    drone && levels
      ? {
          id: 'lake_level',
          label: 'Lake level',
          unit: 'm',
          sen_slope_per_decade: null,
          p_value: null,
          verdict: 'unknown',
          direction: 'flat',
          years_needed: null,
          residual_pct_non_climate: null,
          series: Object.entries(levels)
            .map(([y, value]) => ({ year: Number(y), value }))
            .sort((a, b) => a.year - b.year),
        }
      : null
  const timelineVariable = lakeLevel ?? variable
  const photo = drone ? photoFor(detailInfo, shownYear) : null
  const photoTexture = usePhoto(caseId, photo?.file ?? null)
  const recordYears = variable ? timeline?.records?.[variable.id] : undefined
  const recordHasYear = !recordYears || recordYears.includes(shownYear)
  const yearLevel = levels?.[String(shownYear)] ?? null
  const drawable = Boolean(detailInfo?.drawable_years?.includes(shownYear))
  const droneLevel = drawable ? yearLevel : null
  const mapKm = site ? bboxWidthMeters(site.bbox) / 1000 : 80
  const cropKm = detailInfo ? bboxWidthMeters(detailInfo.bbox) / 1000 : undefined
  const vx = Math.min(site?.vertical_exaggeration ?? 1.5, 2)
  const onLayers = stack.filter((s) => s.on).map((s) => layers.find((l) => l.id === s.id)).filter((l) => l != null)
  const baseInfo = drone
    ? { title: 'Aerial photo and lidar ground (close-up)', note: photo ? photo.words : 'present-day picture', status: 'visual_only' as const }
    : { title: 'Satellite picture', note: 'one date, not per year', status: 'visual_only' as const }

  return (
    <div className={mode === 'doc' ? 'st st-documentary' : drone ? 'st st-in-drone' : 'st'}>
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
        <Link href={`/investigate?site=${caseId}`} className="st-explore st-ask">
          <span>
            Ask<span className="st-hide-sm"> the detective</span>
          </span>
        </Link>
        <Link href="/explore" className="st-explore st-explore-last">
          <span>
            Explore<span className="st-hide-sm"> any point</span>
          </span>
          <span aria-hidden="true">→</span>
        </Link>
      </header>

      <main className="st-stage">
        <section className="st-viewer" aria-label="3D terrain">
          <div className={identify ? 'st-canvas st-identify' : 'st-canvas'}>
            {site && mode === 'doc' ? (
              <div className="doc">
                <div className="doc-top">
                  <Link href="/" className="doc-wordmark wide">
                    Earth Trend Detective
                  </Link>
                  <ol className="doc-chapters" aria-label="Chapters">
                    {CHAPTER_NAMES.map((name, i) => (
                      <li key={name}>
                        <button
                          type="button"
                          className={i === chapter ? 'doc-chapter doc-chapter-on' : 'doc-chapter'}
                          aria-current={i === chapter ? 'step' : undefined}
                          onClick={() => {
                            setChapter(i)
                            setChapterT(0)
                          }}
                        >
                          {name}
                        </button>
                      </li>
                    ))}
                  </ol>
                  <span className="doc-year narrow" aria-live="off">
                    {`${firstYear}–${lastYear}`}
                  </span>
                </div>
                {docCurtain?.value ? (
                  <Curtain
                    split={docSplit}
                    onSplit={() => undefined}
                    left={String(docCurtain.value.before.year)}
                    right={String(docCurtain.value.after.year)}
                    interactive={false}
                  />
                ) : null}
                {(() => {
                  const c = chaptersFor(site)[chapter]
                  return (
                    <div className="doc-sub" key={`${site.id}-${chapter}`} aria-live="polite">
                      <p className="doc-place">{shortName(site.name)}</p>
                      <p className="doc-headline narrow">{c.headline}</p>
                      {c.line ? <p className="doc-line">{c.line}</p> : null}
                    </div>
                  )
                })()}
                <div className="doc-bottom">
                  <div
                    className="doc-progress"
                    role="progressbar"
                    aria-label="Story progress"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={Math.round(((chapter + chapterT) / CHAPTER_NAMES.length) * 100)}
                  >
                    <i style={{ width: `${((chapter + chapterT) / CHAPTER_NAMES.length) * 100}%` }} />
                  </div>
                  <div className="doc-controls">
                    <button type="button" className="doc-quiet" onClick={enterFree}>
                      Explore
                    </button>
                    <button type="button" className="doc-quiet" onClick={() => setDocPlaying((p) => !p)} aria-pressed={!docPlaying}>
                      {docPlaying ? 'Pause' : 'Play'}
                    </button>
                    <button type="button" className="btn btn-primary" onClick={nextChapter}>
                      {chapter >= CHAPTER_NAMES.length - 1 ? 'Explore freely →' : `Next: ${CHAPTER_NAMES[chapter + 1].replace(/\?$/, '').toLowerCase()} →`}
                    </button>
                  </div>
                </div>
              </div>
            ) : null}

            {site && !error && !drone ? (
              <StoryScene
                site={site}
                assets={assets}
                overlays={mode === 'doc' ? (docCurtain?.textures ?? []) : overlays}
                split={mode === 'doc' ? docSplit : split}
                hideWater={Boolean(docCurtain)}
                shiftX={mode === 'free' && wide ? 0.16 : 0}
                onPick={identify && mode === 'free' ? onPick : undefined}
                exaggeration={vx}
                shot={mode === 'doc' ? chapter : null}
              />
            ) : null}

            {drone && detail.assets ? (
              <DroneScene
                detail={detail.assets}
                photo={photoTexture}
                overlays={droneOverlays}
                split={split}
                onPick={identify ? onPick : undefined}
                level={droneLevel}
                exaggeration={1}
                onAltitude={setAltitude}
              />
            ) : null}

            {drone && !detail.assets && !detail.error ? (
              <div className="st-message" role="status">
                <span className="spinner" aria-hidden="true" /> Loading the close-up: real ground and aerial photo…
              </div>
            ) : null}

            {drone && detail.error ? (
              <div className="st-message" role="alert">
                <p>
                  <strong>The close-up could not load.</strong>
                </p>
                <button type="button" className="btn" onClick={() => setDrone(false)}>
                  Back to the overview
                </button>
              </div>
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

            {site && !assets.error && assets.loading && !drone ? (
              <div className="st-loading" role="status">
                <span className="spinner" aria-hidden="true" /> Loading the terrain…
              </div>
            ) : null}

            {site && variable && drone ? (
              <div className="st-yearcard" aria-live="polite">
                <ul>
                  {drone ? (
                    <li>
                      {levels
                        ? yearLevel == null
                          ? 'No lake level for this year.'
                          : drawable
                            ? `Lake surface at ${Math.round(yearLevel)} m above sea level (USBR yearly mean).`
                            : `Lake at ${Math.round(yearLevel)} m: lower than this survey can show, so no water is drawn.`
                        : photo
                          ? `${photo.words}.`
                          : 'Present-day ground and photo.'}
                    </li>
                  ) : (
                    <li>
                      <strong>{variable.label}:</strong> {recordHasYear ? 'on the timeline below' : `no value for ${shownYear}`}
                      {noMapFor === variable.id ? '. No map for this record, showing the picture.' : ''}
                    </li>
                  )}
                  {onLayers.length === 0 ? (
                    <li>Map: {drone ? 'the close-up picture only' : 'satellite picture, one date'}</li>
                  ) : (
                    onLayers.map((l) => (
                      <li key={l.id}>
                        <strong>{l.title}:</strong>{' '}
                        {anomalyDef?.id === l.id && anomalyWords && fileFor(l, shownYear) ? anomalyWords : yearStatus(l, shownYear)}
                      </li>
                    ))
                  )}
                </ul>
              </div>
            ) : null}

            {site && detailInfo ? (
              <button
                type="button"
                className={drone ? 'st-drone-toggle st-drone-on' : 'st-drone-toggle'}
                onClick={() => {
                  setDrone((d) => !d)
                  setPicked(null)
                }}
              >
                {drone ? '← Back to the overview' : 'Drone view: fly low over the real ground'}
              </button>
            ) : null}

            {mode === 'free' && compareId ? (
              <Curtain
                split={split}
                onSplit={setSplit}
                left={layers.find((l) => stack.some((s) => s.on && s.id === l.id) && l.blend === 'normal')?.title ?? 'Layer'}
                right={layers.find((l) => l.id === compareId)?.title ?? 'Compared layer'}
              />
            ) : null}

            {picked ? (
              <div className="st-identify-card" role="status">
                <div className="st-identify-head">
                  <strong>Here, in {picked.year}</strong>
                  <button type="button" className="lp-more" aria-label="Close" onClick={() => setPicked(null)}>
                    ×
                  </button>
                </div>
                <ul>
                  {picked.elevation != null ? (
                    <li>
                      <span>Ground height</span>
                      <span>{Math.round(picked.elevation)} m</span>
                    </li>
                  ) : null}
                  {picked.rows.map((r) => (
                    <li key={r.title}>
                      <span>{r.title}</span>
                      <span>{r.text}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {drone && detail.assets ? (
              <div className="st-drone-hud">
                <p className="st-drone-help">
                  {altitude != null ? <strong>{altitude} m above ground</strong> : null}
                  {droneHelp ? (
                    <span>
                      {altitude != null ? ' · ' : null}W A S D or arrows to fly · drag to look · scroll or Q / E for height · on touch: drag to fly, pinch for
                      height
                    </span>
                  ) : (
                    <button type="button" className="st-drone-keys" onClick={() => setDroneHelp(true)}>
                      Controls
                    </button>
                  )}
                </p>
                <details className="st-drone-note">
                  <summary>About these pictures</summary>
                  <p>
                    {detailInfo?.photos_by_year
                      ? `${detailInfo.photo_note ?? ''} ${detailInfo.note ?? ''}`
                      : 'Ground: USGS lidar (2018). Photo: NAIP aerial. Both are present-day pictures, not measurements. Only the water level changes with the year.'}
                  </p>
                </details>
              </div>
            ) : null}

            {site && !drone ? (
              <div className="st-relief">
                <span title="Mountains and valleys are drawn this many times taller than they really are, so the shape reads at this size.">
                  {vx === 1 ? 'Relief at true scale' : `Relief exaggerated ×${vx}`}
                </span>
              </div>
            ) : null}
          </div>

          {site && layers.length > 0 ? (
            <LayerPanel
              layers={layers}
              stack={stack}
              onStack={changeStack}
              year={shownYear}
              base={baseInfo}
              whys={whys}
              caption={caption}
              onAsk={ask}
              asking={asking}
              askError={askError}
              identify={identify}
              onIdentify={(on) => {
                setIdentify(on)
                if (!on) setPicked(null)
              }}
              cropKm={drone ? cropKm : undefined}
              compareId={compareId}
              onCompare={setCompareId}
              notice={variable && noMapFor === variable.id ? 'no map for this record' : null}
            />
          ) : null}

          <Timeline
            first={firstYear}
            last={lastYear}
            year={shownYear}
            playing={playing}
            variable={timelineVariable}
            mapFollows={onLayers.some((l) => l.years != null) || (drone && Boolean(detail.assets))}
            mapKm={mapKm}
            onScrub={handleScrub}
            onToggle={() => setPlaying((value) => !value)}
          />
        </section>

        {site && variable ? (
          <StoryPanel site={site} variable={variable} step={step} mapKm={mapKm} onSelectVariable={selectRecord} onStep={setStep} />
        ) : (
          <aside className="sp sp-empty" aria-label="Case details">
            <p>{error ? 'Pick another case above.' : `Opening ${CASE_LABELS[caseId] ?? shortName(caseId)}…`}</p>
          </aside>
        )}
      </main>
    </div>
  )
}
