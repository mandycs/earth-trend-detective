'use client'

import { useEffect, useRef, useState } from 'react'
import { Wordmark } from '../../brand/Wordmark'
import styles from './hero.module.css'

/**
 * The opening film, full screen, muted until the viewer asks for sound.
 * With reduced motion it waits on its poster for a click.
 */
export function HeroFilm() {
  const video = useRef<HTMLVideoElement>(null)
  const [muted, setMuted] = useState(true)
  const [playing, setPlaying] = useState(false)

  useEffect(() => {
    const v = video.current
    if (!v) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    v.play().catch(() => setPlaying(false))
  }, [])

  const toggleSound = () => {
    const v = video.current
    if (!v) return
    v.muted = !v.muted
    setMuted(v.muted)
    if (v.paused) v.play().catch(() => undefined)
  }

  const togglePlay = () => {
    const v = video.current
    if (!v) return
    if (v.paused) v.play().catch(() => undefined)
    else v.pause()
  }

  return (
    <section className={styles.hero} aria-label="Alibi, the film">
      <video
        ref={video}
        className={styles.film}
        src="/video/alibi-hero.mp4"
        poster="/video/alibi-hero-poster.jpg"
        muted
        loop
        playsInline
        preload="metadata"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        aria-label="A 71-second film: satellites have watched Earth for decades, and Alibi turns their records into plain answers"
      />
      <div className={styles.shade} aria-hidden="true" />
      <p className={styles.brand}>
        <Wordmark />
      </p>
      <div className={styles.controls}>
        <button type="button" className={styles.control} onClick={togglePlay} aria-pressed={!playing}>
          {playing ? 'Pause' : 'Play'}
        </button>
        <button type="button" className={styles.control} onClick={toggleSound} aria-pressed={!muted}>
          {muted ? 'Sound on' : 'Sound off'}
        </button>
        <a href="#cases" className={styles.skip}>
          See the cases ↓
        </a>
      </div>
    </section>
  )
}
