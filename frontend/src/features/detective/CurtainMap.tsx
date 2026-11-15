'use client'

import { useEffect, useRef, useState } from 'react'
import type { Map as MlMap } from 'maplibre-gl'
import { STYLE } from '../explore/mapStyle'
import { curtainAriaLabel, curtainYears, drawSpecs, initialSplit } from './map/draw'
import type { DrawSpec } from './map/draw'
import type { CurtainView, MapView } from './map/mapView'
import { syncSpecs } from './mapSync'
import styles from './detective.module.css'

export interface CurtainCamera {
  center: [number, number]
  zoom: number
  pitch: number
  bearing: number
}

interface Props {
  curtain: CurtainView
  camera: CurtainCamera
  /** Footprints and the picked box, so they stay visible on the right of the divider too. */
  overlays?: DrawSpec[]
}

const curtainOnly = (curtain: CurtainView): MapView => ({
  place: null, context: null, evidence: null, curtain, footprints: [], camera: null, notes: [],
})

/**
 * The right-hand picture of a comparison: a second, non-interactive map (same style, no terrain) over the main
 * one, clipped at the divider. The main map drives its camera through `camera`.
 */
export function CurtainMap({ curtain, camera, overlays = [] }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<MlMap | null>(null)
  const registry = useRef(new Map<string, string>())
  const cameraRef = useRef(camera)
  const [ready, setReady] = useState(false)
  const [split, setSplit] = useState(() => (typeof window === 'undefined' ? 50 : initialSplit(window.innerWidth)))

  useEffect(() => {
    cameraRef.current = camera
    map.current?.jumpTo(camera)
  }, [camera])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const maplibregl = (await import('maplibre-gl')).default
      if (cancelled || !container.current) return
      const m = new maplibregl.Map({
        container: container.current,
        style: { ...STYLE, projection: { type: 'globe' } },
        interactive: false,
        attributionControl: false,
        maxPitch: 85,
        ...cameraRef.current,
      })
      m.on('load', () => !cancelled && setReady(true))
      map.current = m
    })().catch(() => {
      // The main map reports load failures; a missing curtain leaves the left picture readable.
    })
    const reg = registry.current
    return () => {
      cancelled = true
      map.current?.remove()
      map.current = null
      reg.clear()
      setReady(false)
    }
  }, [])

  useEffect(() => {
    const m = map.current
    if (!m || !ready) return
    syncSpecs(m, [...drawSpecs(curtainOnly(curtain), 'curtain', null), ...overlays], registry.current)
  }, [curtain, overlays, ready])

  const [yearA, yearB] = curtainYears(curtain)
  return (
    <div className={styles.curtain}>
      <div ref={container} className={styles.curtainMap} style={{ clipPath: `inset(0 0 0 ${split}%)` }} aria-hidden="true" />
      <div className={styles.curtainDivider} style={{ left: `${split}%` }} aria-hidden="true" />
      <p className={`${styles.curtainYear} ${styles.curtainYearLeft}`}>
        <span aria-hidden="true">◀ </span>
        {yearA}
      </p>
      <p className={`${styles.curtainYear} ${styles.curtainYearRight}`}>
        {yearB}
        <span aria-hidden="true"> ▶</span>
      </p>
      <input
        type="range"
        className={styles.curtainRange}
        min={0}
        max={100}
        step={0.5}
        value={split}
        aria-label={curtainAriaLabel(curtain)}
        onChange={(e) => setSplit(Number(e.target.value))}
      />
    </div>
  )
}

export default CurtainMap
