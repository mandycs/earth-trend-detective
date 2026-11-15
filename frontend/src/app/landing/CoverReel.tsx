'use client'

import Image from 'next/image'
import Link from 'next/link'
import { Wordmark } from '../../brand/Wordmark'
import { useEffect, useRef, useState } from 'react'
import styles from './cover.module.css'

export interface ReelCase {
  id: string
  name: string
  where: string
  image: string
  headline: string
  line: string
}

const SECONDS = 7

/**
 * Documentary cover: the three real cases, one at a time, full screen.
 * Case names sit top centre like chapters; one subtitle; a progress line.
 * Everything on screen comes from each case's site.json.
 */
export function CoverReel({ cases, years }: { cases: ReelCase[]; years: string }) {
  const [index, setIndex] = useState(0)
  // Progress within the current case lives in a ref and is painted straight onto the bar, so the
  // reel does not re-render React sixty times a second.
  const t = useRef(0)
  const bar = useRef<HTMLElement>(null)
  const section = useRef<HTMLElement>(null)
  const [visible, setVisible] = useState(true)
  const [playing, setPlaying] = useState(true)
  // Only the picture on screen and the next one are fetched; the rest wait for their turn.
  const [warm, setWarm] = useState<ReadonlySet<number>>(() => new Set([0, 1]))

  useEffect(() => {
    if (cases.length === 0) return
    const next = (index + 1) % cases.length
    setWarm((seen) => (seen.has(index) && seen.has(next) ? seen : new Set([...seen, index, next])))
  }, [index, cases.length])

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) setPlaying(false)
  }, [])

  // Off screen, the reel stops: no animation work while the viewer is on the film or below.
  useEffect(() => {
    const el = section.current
    if (!el || typeof IntersectionObserver === 'undefined') return
    const io = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { threshold: 0.1 })
    io.observe(el)
    return () => io.disconnect()
  }, [])

  useEffect(() => {
    if (bar.current) bar.current.style.width = `${((index + t.current) / Math.max(cases.length, 1)) * 100}%`
  }, [index, cases.length])

  useEffect(() => {
    if (!playing || !visible || cases.length < 2) return
    let frame = 0
    let previous = performance.now()
    const tick = (now: number) => {
      const delta = Math.min((now - previous) / 1000, 0.1)
      previous = now
      t.current += delta / SECONDS
      if (t.current >= 1) {
        t.current = 0
        setIndex((i) => (i + 1) % cases.length)
      }
      if (bar.current) bar.current.style.width = `${((index + t.current) / cases.length) * 100}%`
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [playing, visible, cases.length, index])

  const current = cases[index]
  if (!current) return null

  return (
    <section ref={section} className={styles.reel} aria-label="Three solved cases">
      {cases.map((c, i) =>
        warm.has(i) || i === index ? (
          // next/image serves a WebP sized to the screen instead of the 2-4k source JPEG.
          <Image
            key={c.id}
            src={c.image}
            alt={i === index ? `Satellite picture of ${c.name}` : ''}
            aria-hidden={i === index ? undefined : true}
            className={i === index ? `${styles.reelImage} ${styles.reelImageOn}` : styles.reelImage}
            fill
            sizes="100vw"
            loading={i === 0 ? 'eager' : 'lazy'}
            fetchPriority={i === 0 ? 'high' : 'low'}
          />
        ) : null,
      )}
      <div className={styles.reelShade} aria-hidden="true" />

      <header className={styles.reelTop}>
        <Link href="/" className={`${styles.wordmark} wide`}>
          <Wordmark />
        </Link>
        <ol className={styles.reelCases} aria-label="Cases">
          {cases.map((c, i) => (
            <li key={c.id}>
              <button
                type="button"
                className={i === index ? `${styles.reelCase} ${styles.reelCaseOn}` : styles.reelCase}
                aria-current={i === index ? 'true' : undefined}
                onClick={() => {
                  t.current = 0
                  setIndex(i)
                }}
              >
                {c.name}
              </button>
            </li>
          ))}
        </ol>
        <span className={`${styles.reelYears} narrow`}>{years}</span>
      </header>

      <div className={styles.reelSub} key={current.id} aria-live="polite">
        <h1 className={`${styles.reelTitle} narrow`}>Is it the climate?</h1>
        <p className={styles.reelPlace}>
          {current.name} · {current.where}
        </p>
        <p className={`${styles.reelHeadline} narrow`}>{current.headline}</p>
        <p className={styles.reelLine}>{current.line}</p>
      </div>

      <div className={styles.reelBottom}>
        <div className={styles.reelProgress} aria-hidden="true">
          <i ref={bar} />
        </div>
        <div className={styles.reelControls}>
          <Link href="/detective" className={styles.quiet}>
            Pick your own place
          </Link>
          <button type="button" className={styles.quiet} onClick={() => setPlaying((p) => !p)} aria-pressed={!playing}>
            {playing ? 'Pause' : 'Play'}
          </button>
          <Link href={`/story/${current.id}`} className="btn btn-primary">
            Watch the {current.name} case →
          </Link>
        </div>
      </div>
    </section>
  )
}
