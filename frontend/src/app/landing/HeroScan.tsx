'use client'

import { useEffect, useRef, useState } from 'react'
import styles from './landing.module.css'

export interface HeroScanProps {
  base: string
  /** Pattern with {YYYY}; absent when the case has no yearly layer. */
  framePattern?: string
  years: [number, number]
  layerLabel?: string
  stops?: string[]
  more?: string
  less?: string
  alt: string
}

const STEP_MS = 650

/**
 * The cover picture: the real satellite base of a case, with its yearly
 * per-pixel layer playing over it and a year scrubber under the thumb.
 */
export function HeroScan({ base, framePattern, years, layerLabel, stops, more, less, alt }: HeroScanProps) {
  const [first, last] = years
  const [year, setYear] = useState(first)
  const [playing, setPlaying] = useState(true)
  const [ready, setReady] = useState(false)
  const reduced = useRef(false)

  useEffect(() => {
    reduced.current = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduced.current) setPlaying(false)
  }, [])

  // Preload every frame before playing, so the loop never flashes.
  useEffect(() => {
    if (!framePattern) return
    let alive = true
    const all: Promise<void>[] = []
    for (let y = first; y <= last; y += 1) {
      const img = new Image()
      img.src = framePattern.replace('{YYYY}', String(y))
      all.push(img.decode().catch(() => undefined))
    }
    Promise.all(all).then(() => alive && setReady(true))
    return () => {
      alive = false
    }
  }, [framePattern, first, last])

  useEffect(() => {
    if (!framePattern || !playing || !ready) return
    const id = window.setInterval(() => setYear((y) => (y >= last ? first : y + 1)), STEP_MS)
    return () => window.clearInterval(id)
  }, [framePattern, playing, ready, first, last])

  return (
    <figure className={styles.scan}>
      <div className={styles.scanPicture}>
        <img src={base} alt={alt} className={styles.scanBase} fetchPriority="high" />
        {framePattern && ready ? (
          <img
            src={framePattern.replace('{YYYY}', String(year))}
            alt=""
            aria-hidden="true"
            className={styles.scanFrame}
          />
        ) : null}
        {framePattern ? (
          <output className={`${styles.scanYear} narrow`} aria-live="off">
            {year}
          </output>
        ) : null}
      </div>
      {framePattern ? (
        <figcaption className={styles.scanBar}>
          <button
            type="button"
            className={styles.scanPlay}
            onClick={() => setPlaying((p) => !p)}
            aria-pressed={playing}
            aria-label={playing ? 'Pause the years' : 'Play the years'}
          >
            <span aria-hidden="true">{playing ? '❚❚' : '▶'}</span>
          </button>
          <label className={styles.scanTrack}>
            <span className="sr-only">Year</span>
            <input
              type="range"
              min={first}
              max={last}
              step={1}
              value={year}
              onChange={(event) => {
                setPlaying(false)
                setYear(Number(event.target.value))
              }}
            />
          </label>
          <span className={styles.scanLegend}>
            <span className={styles.scanLegendTitle}>{layerLabel}, each year against its usual</span>
            {stops && stops.length > 1 ? (
              <span className={styles.ramp} aria-hidden="true">
                {stops.map((c) => (
                  <span key={c} style={{ background: c }} />
                ))}
              </span>
            ) : null}
            <span className={styles.rampEnds}>
              <span>{less}</span>
              <span>{more}</span>
            </span>
          </span>
        </figcaption>
      ) : null}
    </figure>
  )
}
