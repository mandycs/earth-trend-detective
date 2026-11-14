'use client'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { mapLayers, useLegend, useSite, useStoryAssets } from './useSite'
import type { MapLayer } from './useSite'
import { StoryScene } from './StoryScene'
import { DroneScene } from './drone/DroneScene'
import { useDetailAssets, useDetailInfo, usePhoto } from './drone/useDetail'
import type { DetailInfo } from './drone/useDetail'
import { useTimeline } from './useTimeline'
import { StoryPanel } from './StoryPanel'
import { Timeline } from './Timeline'
import type { SiteVariable } from './types'
import { bboxWidthMeters } from './types'
import { CASE_IDS, leadVariable, shortName } from '../lib/cases'

const CASE_LABELS: Record<string, string> = {
  lake_mead: 'Lake Mead',
  aletsch: 'Aletsch',
  donana: 'Doñana',
}

/** Seconds per year while playing: the frame holds, then fades to the next. */
const YEAR_SECONDS = 1.8
/** Share of each year spent holding still before the fade starts. */
const HOLD = 0.7

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

function layerName(layer: MapLayer, label: string | undefined, single: boolean): string {
  const how = layer.kind === 'year' ? 'Year by year' : 'Trend'
  if (single) return how
  return `${label ?? layer.variable.replace(/_/g, ' ')}: ${how.toLowerCase()}`
}

export default function StoryApp({ caseId }: { caseId: string }) {
  const { site, error } = useSite(caseId)
  const detailInfo = useDetailInfo(caseId)
  const [drone, setDrone] = useState(false)
  const detail = useDetailAssets(caseId, detailInfo, drone)
  const timeline = useTimeline(caseId)
  const [noMapFor, setNoMapFor] = useState<string | null>(null)
  const [altitude, setAltitude] = useState<number | null>(null)
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
  const clockRef = useRef(0)

  const variable: SiteVariable | null = useMemo(() => {
    if (!site || site.variables.length === 0) return null
    return site.variables.find((entry) => entry.id === variableId) ?? leadVariable(site)
  }, [site, variableId])

  // New case: lead record on the timeline, yearly map layer if there is one, play.
  useEffect(() => {
    if (!site) return
    setVariableId(leadVariable(site)?.id ?? null)
    // True colours first; the data layers are one tap away.
    setLayerKey('none')
    setExaggeration(null)
    setDrone(false)
    setNoMapFor(null)
    yearRef.current = site.years[0]
    clockRef.current = 0
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
      const span = lastYear - firstYear
      clockRef.current += delta
      // Hold an extra year's time on the last frame before starting again.
      if (clockRef.current > (span + 2) * YEAR_SECONDS) clockRef.current = 0
      const index = Math.min(Math.floor(clockRef.current / YEAR_SECONDS), span)
      const phase = (clockRef.current / YEAR_SECONDS) % 1
      const fade = index >= span ? 0 : Math.max(0, (phase - HOLD) / (1 - HOLD))
      const eased = fade * fade * (3 - 2 * fade)
      yearRef.current = firstYear + index + eased
      setDisplayYear(firstYear + index + (eased > 0.5 ? 1 : 0))
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [playing, firstYear, lastYear])

  /** Picking a record moves the map to that record's yearly layer, or says there is none. */
  const selectRecord = (id: string) => {
    setVariableId(id)
    const mapId = timeline?.record_map?.[id] ?? null
    const match = mapId ? layers.find((l) => l.kind === 'year' && mapId === `year_${l.variable}`) : null
    if (match) {
      setLayerKey(match.key)
      setNoMapFor(null)
    } else {
      setLayerKey('none')
      setNoMapFor(id)
    }
  }

  /** Picking a map layer puts its record on the timeline. */
  const selectLayer = (key: string) => {
    setLayerKey(key)
    setNoMapFor(null)
    const picked = layers.find((l) => l.key === key)
    if (picked && site?.variables.some((v) => v.id === picked.variable)) setVariableId(picked.variable)
  }

  const yearProgress = useCallback(() => Math.min(yearRef.current, lastYear) - firstYear, [firstYear, lastYear])

  const handleScrub = (year: number) => {
    setPlaying(false)
    yearRef.current = year
    clockRef.current = (year - firstYear) * YEAR_SECONDS
    setDisplayYear(year)
  }

  const shownYear = displayYear || firstYear
  const layerYears = layer ? timeline?.layers?.[`${layer.kind === 'year' ? 'year' : 'trend'}_${layer.variable}`]?.years : undefined
  const layerHasYear = layer?.kind !== 'year' || !layerYears || layerYears.includes(shownYear)
  const showYears = layer?.kind === 'year' && assets.years.length > 1 && layerHasYear
  // In the drone, the record under the timeline is the lake level the water is drawn at.
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
  const frameRead = showYears ? assets.reads[(displayYear || firstYear) - firstYear] ?? null : null
  const frameWords = frameRead
    ? frameRead.warmer > 0.6
      ? 'warmer than usual over most of the area'
      : frameRead.cooler > 0.6
        ? 'cooler than usual over most of the area'
        : frameRead.warmer > frameRead.cooler + 0.15
          ? 'mixed, leaning warmer than usual'
          : frameRead.cooler > frameRead.warmer + 0.15
            ? 'mixed, leaning cooler than usual'
            : 'close to usual, warmer in places and cooler in others'
    : null
  // Close to true scale reads as a real place; the pipeline's value is a ceiling.
  const vx = exaggeration ?? Math.min(site?.vertical_exaggeration ?? 1.5, 2)

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
          <div className="st-canvas">
            {site && !error && !drone ? (
              <StoryScene site={site} assets={assets} yearProgress={yearProgress} showYears={showYears} exaggeration={vx} />
            ) : null}

            {drone && detail.assets ? (
              <DroneScene detail={detail.assets} photo={photoTexture} level={droneLevel} exaggeration={1} onAltitude={setAltitude} />
            ) : null}

            {drone && !detail.assets && !detail.error ? (
              <div className="st-message" role="status">
                <span className="spinner" aria-hidden="true" /> Loading the close-up: lidar ground and aerial photo…
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

            {drone && detail.assets ? (
              <div className="st-drone-hud">
                <div className="st-drone-level">
                  <span className="st-yearnote-year narrow">{shownYear}</span>
                  <span>
                    {levels
                      ? yearLevel == null
                        ? 'No lake level for this year.'
                        : drawable
                          ? `Lake surface at ${Math.round(yearLevel)} m above sea level (USBR yearly mean).`
                          : `Lake at ${Math.round(yearLevel)} m: lower than this survey can show, so no water is drawn.`
                      : photo
                        ? `${photo.words}.`
                        : 'Present-day ground and photo.'}
                  </span>
                </div>
                <p className="st-drone-help">
                  {altitude != null ? <strong>{altitude} m above ground · </strong> : null}
                  W A S D or arrows to fly · drag to look · scroll or Q / E for height · on touch: drag to fly, pinch for height
                </p>
                <p className="st-drone-note">
                  {detailInfo?.photos_by_year
                    ? `${detailInfo.photo_note ?? ''} ${detailInfo.note ?? ''}`
                    : 'Ground: USGS lidar (2018). Photo: NAIP aerial. Both are present-day pictures, not measurements. Only the water level changes with the year.'}
                </p>
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

            {site && !assets.error && assets.loading ? (
              <div className="st-loading" role="status">
                <span className="spinner" aria-hidden="true" /> Loading the terrain and satellite layers…
              </div>
            ) : null}

            {site && !drone && variable ? (
              <div className="st-yearcard" aria-live="polite">
                <span className="st-yearnote-year narrow">{shownYear}</span>
                <ul>
                  <li>
                    <strong>{variable.label}:</strong>{' '}
                    {recordHasYear ? 'on the timeline below' : `no value for ${shownYear}`}
                  </li>
                  <li>
                    <strong>Map:</strong>{' '}
                    {!layer
                      ? noMapFor === variable.id
                        ? 'no map for this record, showing the satellite picture (one date, not per year)'
                        : 'satellite picture (one date, not per year)'
                      : layer.kind === 'trend'
                        ? `${legend?.label ?? 'trend'}, change over the whole ${firstYear}–${lastYear} period`
                        : !layerHasYear
                          ? `no MODIS map for ${shownYear}`
                          : frameWords && legend
                            ? `${legend.label}: ${frameWords}`
                            : `${legend?.label ?? 'yearly map'} for ${shownYear}`}
                  </li>
                </ul>
              </div>
            ) : null}

            {site && detailInfo ? (
              <button type="button" className={drone ? 'st-drone-toggle st-drone-on' : 'st-drone-toggle'} onClick={() => setDrone((d) => !d)}>
                {drone ? '← Back to the overview' : 'Drone view: fly low over the real ground'}
              </button>
            ) : null}

            {site && !drone ? (
              <div className="st-relief">
                <span title="Mountains and valleys are drawn this many times taller than they really are, so the shape reads at this size.">
                  {vx === 1 ? 'Relief at true scale' : `Relief exaggerated ×${vx}`}
                </span>
              </div>
            ) : null}
          </div>

          {site && !drone ? (
            <div className="st-layers">
              <div className="st-layer-pick" role="radiogroup" aria-label="What the map shows">
                <button
                  type="button"
                  role="radio"
                  aria-checked={layerKey === 'none'}
                  className={layerKey === 'none' ? 'st-chip st-chip-on' : 'st-chip'}
                  onClick={() => selectLayer('none')}
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
                    onClick={() => selectLayer(l.key)}
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
            variable={timelineVariable}
            mapFollows={showYears || (drone && Boolean(detail.assets))}
            mapKm={mapKm}
            onScrub={handleScrub}
            onToggle={() => setPlaying((value) => !value)}
          />
        </section>

        {site && variable ? (
          <StoryPanel
            site={site}
            variable={variable}
            step={step}
            mapKm={mapKm}
            onSelectVariable={selectRecord}
            onStep={setStep}
          />
        ) : (
          <aside className="sp sp-empty" aria-label="Case details">
            <p>{error ? 'Pick another case above.' : `Opening ${CASE_LABELS[caseId] ?? shortName(caseId)}…`}</p>
          </aside>
        )}
      </main>
    </div>
  )
}
