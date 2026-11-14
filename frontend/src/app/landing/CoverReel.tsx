'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
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
  const [t, setT] = useState(0)
  const [playing, setPlaying] = useState(true)

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) setPlaying(false)
  }, [])

  useEffect(() => {
    if (!playing || cases.length < 2) return
    let frame = 0
    let previous = performance.now()
    const tick = (now: number) => {
      const delta = Math.min((now - previous) / 1000, 0.1)
      previous = now
      setT((value) => {
        const next = value + delta / SECONDS
        if (next >= 1) {
          setIndex((i) => (i + 1) % cases.length)
          return 0
        }
        return next
      })
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [playing, cases.length])

  const current = cases[index]
  if (!current) return null

  return (
    <section className={styles.reel} aria-label="Three solved cases">
      {cases.map((c, i) => (
        <img
          key={c.id}
          src={c.image}
          alt={i === index ? `Satellite picture of ${c.name}` : ''}
          aria-hidden={i === index ? undefined : true}
          className={i === index ? `${styles.reelImage} ${styles.reelImageOn}` : styles.reelImage}
          fetchPriority={i === 0 ? 'high' : 'low'}
        />
      ))}
      <div className={styles.reelShade} aria-hidden="true" />

      <header className={styles.reelTop}>
        <Link href="/" className={`${styles.wordmark} wide`}>
          Earth Trend Detective
        </Link>
        <ol className={styles.reelCases} aria-label="Cases">
          {cases.map((c, i) => (
            <li key={c.id}>
              <button
                type="button"
                className={i === index ? `${styles.reelCase} ${styles.reelCaseOn}` : styles.reelCase}
                aria-current={i === index ? 'true' : undefined}
                onClick={() => {
                  setIndex(i)
                  setT(0)
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
          <i style={{ width: `${((index + t) / cases.length) * 100}%` }} />
        </div>
        <div className={styles.reelControls}>
          <Link href="/investigate" className={styles.quiet}>
            Investigate any point
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
