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

  // The film starts once the page has loaded, so its megabytes never compete with the first paint
  // (the poster is what the viewer sees first; preload="none" keeps the video off the wire until then).
  useEffect(() => {
    const v = video.current
    if (!v) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const start = () => v.play().catch(() => setPlaying(false))
    if (document.readyState === 'complete') {
      start()
      return
    }
    window.addEventListener('load', start, { once: true })
    return () => window.removeEventListener('load', start)
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
        poster="/video/alibi-hero-poster.webp"
        width={1920}
        height={1080}
        muted
        loop
        playsInline
        preload="none"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        aria-label="A 71-second film: satellites have watched Earth for decades, and Alibi turns their records into plain answers"
      >
        {/* Same film, two encodes: phones and laptops get the 1280 one (about half the bytes). */}
        <source src="/video/alibi-hero-1280.mp4" type="video/mp4" media="(max-width: 1280px)" />
        <source src="/video/alibi-hero.mp4" type="video/mp4" />
      </video>
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
