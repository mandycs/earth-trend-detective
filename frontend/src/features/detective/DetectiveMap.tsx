'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Map as MlMap, Marker } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { STYLE } from '../explore/mapStyle'
import { OPPOSITE_CORNER_HINT, drawSpecs, fitPadding, mapLabel, overlaySpecs, pickStep } from './map/draw'
import type { Corner, PickMode, PickResult } from './map/draw'
import type { MapView } from './map/mapView'
import type { Target } from './request'
import { CurtainMap } from './CurtainMap'
import type { CurtainCamera, CurtainSync } from './CurtainMap'
import { LayerLegend } from './LayerLegend'
import { addRelief, demErrorHandler, syncSpecs } from './mapSync'
import styles from './detective.module.css'

export type { PickMode } from './map/draw'

export interface DetectiveMapProps {
  view: MapView
  target: Target | null
  pickMode: PickMode
  pickEnabled: boolean
  onPick: (result: PickResult) => void
  reducedMotion: boolean
}

const BASE = 'earth'
const FLY_MS = 2200
const MAX_FIT_ZOOM = 12
export const FLAT_NOTE = 'Relief could not load; the map is flat.'
export const MAP_FAILED = 'The map could not load. Check your connection and reload. You can still watch a recorded case.'

function cameraOf(m: MlMap): CurtainCamera {
  const c = m.getCenter()
  return { center: [c.lng, c.lat], zoom: m.getZoom(), pitch: m.getPitch(), bearing: m.getBearing() }
}

export default function DetectiveMap({ view, target, pickMode, pickEnabled, onPick, reducedMotion }: DetectiveMapProps) {
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<MlMap | null>(null)
  const marker = useRef<Marker | null>(null)
  const cornerMarker = useRef<Marker | null>(null)
  const registry = useRef(new Map<string, string>())
  const loaded = useRef(false)
  const baseTileSeen = useRef(false)
  const lastSeq = useRef<number | null>(null)
  const pending = useRef<Corner | null>(null)
  const curtainSync: CurtainSync = useRef<((c: CurtainCamera) => void) | null>(null)
  // Read inside maplibre handlers, which are bound once.
  const live = useRef({ onPick, pickMode, pickEnabled })
  const [ready, setReady] = useState(false)
  const [failed, setFailed] = useState(false)
  const [flat, setFlat] = useState(false)
  const [waitingCorner, setWaitingCorner] = useState(false)
  const [curtainCamera, setCurtainCamera] = useState<CurtainCamera | null>(null)

  useEffect(() => {
    live.current = { onPick, pickMode, pickEnabled }
  }, [onPick, pickMode, pickEnabled])

  const clearPending = useCallback(() => {
    pending.current = null
    cornerMarker.current?.remove()
    setWaitingCorner(false)
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const maplibregl = (await import('maplibre-gl')).default
      if (cancelled || !container.current) return
      const m = new maplibregl.Map({
        container: container.current,
        style: { ...STYLE, projection: { type: 'globe' } },
        center: [-20, 28],
        zoom: 1.6,
        maxPitch: 85,
        attributionControl: { compact: true },
        locale: { 'Map.Title': mapLabel(live.current.pickEnabled, live.current.pickMode) },
      })
      m.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right')
      const onDem = demErrorHandler(m, () => !cancelled && setFlat(true))
      m.on('load', () => {
        if (cancelled) return
        loaded.current = true
        addRelief(m)
        setReady(true)
      })
      m.on('data', (e) => {
        const ev = e as { sourceId?: string; tile?: unknown }
        if (ev.sourceId === BASE && ev.tile) baseTileSeen.current = true
      })
      m.on('error', (e) => {
        const sourceId = (e as { sourceId?: string }).sourceId
        if (onDem(sourceId)) return
        // Fatal only when the style never loaded, or the base picture has never shown a single tile.
        // Missing data tiles (det-*) and a stray base tile after the first one are not a broken map.
        if (!sourceId && !loaded.current) setFailed(true)
        else if (sourceId === BASE && !baseTileSeen.current) setFailed(true)
      })
      m.on('click', (e) => {
        const { onPick: pick, pickMode: mode, pickEnabled: enabled } = live.current
        if (!enabled) return
        const step = pickStep(pending.current, mode, { lat: e.lngLat.lat, lon: e.lngLat.lng })
        pending.current = step.pending
        if (step.pending) {
          cornerMarker.current?.setLngLat([step.pending.lon, step.pending.lat]).addTo(m)
          setWaitingCorner(true)
        } else {
          cornerMarker.current?.remove()
          setWaitingCorner(false)
        }
        if (step.result) pick(step.result)
      })
      // The curtain follows imperatively, in the same frame, with no React render per move.
      m.on('move', () => curtainSync.current?.(cameraOf(m)))
      marker.current = new maplibregl.Marker({ color: '#e9ecee' })
      const dot = document.createElement('div')
      dot.className = styles.cornerDot
      cornerMarker.current = new maplibregl.Marker({ element: dot })
      map.current = m
    })().catch(() => setFailed(true))
    const reg = registry.current
    return () => {
      cancelled = true
      map.current?.remove()
      map.current = null
      loaded.current = false
      baseTileSeen.current = false
      lastSeq.current = null
      reg.clear()
      setReady(false)
    }
  }, [])

  // Cursor and accessible name; a half-drawn box is dropped when picking stops or the mode changes.
  useEffect(() => {
    const m = map.current
    if (m && ready) {
      const canvas = m.getCanvas()
      canvas.style.cursor = pickEnabled ? 'crosshair' : 'default'
      canvas.setAttribute('aria-label', mapLabel(pickEnabled, pickMode))
    }
    clearPending()
  }, [pickEnabled, pickMode, ready, clearPending])

  useEffect(() => {
    if (!waitingCorner) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') clearPending()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [waitingCorner, clearPending])

  // Data layers, footprints and the picked box.
  useEffect(() => {
    const m = map.current
    if (!m || !ready) return
    syncSpecs(m, drawSpecs(view, 'main', target), registry.current)
  }, [view, target, ready])

  // A picked point is a marker.
  useEffect(() => {
    const m = map.current
    if (!m || !ready || !marker.current) return
    if (target?.kind === 'point') marker.current.setLngLat([target.lon, target.lat]).addTo(m)
    else marker.current.remove()
  }, [target, ready])

  // The camera moves only when the scene asks for a new view.
  const cam = view.camera
  useEffect(() => {
    const m = map.current
    if (!m || !ready || !cam || cam.seq === lastSeq.current) return
    lastSeq.current = cam.seq
    const [w, s, e, n] = cam.bbox
    const el = m.getContainer()
    m.fitBounds(
      [
        [w, s],
        [e, n],
      ],
      {
        pitch: cam.pitch, bearing: cam.bearing, padding: fitPadding(el.clientWidth, el.clientHeight),
        maxZoom: MAX_FIT_ZOOM, duration: reducedMotion ? 0 : FLY_MS,
      },
    )
  }, [cam, ready, reducedMotion])

  // The camera the curtain opens on; after that it follows through `curtainSync`.
  const curtainOn = view.curtain !== null
  useEffect(() => {
    const m = map.current
    setCurtainCamera(curtainOn && m && ready ? cameraOf(m) : null)
  }, [curtainOn, ready])

  const overlays = useMemo(() => overlaySpecs(view, target, { point: true }), [view, target])

  return (
    <div className={styles.mapWrap}>
      <div ref={container} className={styles.map} />
      {view.curtain && curtainCamera ? (
        <CurtainMap curtain={view.curtain} camera={curtainCamera} overlays={overlays} sync={curtainSync} flat={flat} />
      ) : null}
      <div className={styles.mapNotes} aria-live="polite">
        {waitingCorner ? (
          <p className={styles.mapHint}>
            {OPPOSITE_CORNER_HINT}
            <span className={styles.mapHintSub}> · Esc to cancel</span>
          </p>
        ) : null}
        {flat ? <p className={styles.mapNote}>{FLAT_NOTE}</p> : null}
        {view.notes.map((n) => (
          <p key={n} className={styles.mapNote}>
            {n}
          </p>
        ))}
      </div>
      <LayerLegend view={view} flat={flat} />
      {failed ? (
        <p className={styles.mapError} role="alert">
          {MAP_FAILED}
        </p>
      ) : null}
    </div>
  )
}
