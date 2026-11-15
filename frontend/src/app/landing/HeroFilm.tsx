'use client'

import { useEffect, useRef, useState } from 'react'
import type { MouseEvent } from 'react'
import { Wordmark } from '../../brand/Wordmark'
import { useSpaceToggle } from './useSpaceToggle'
import styles from './hero.module.css'

/**
 * The opening film, full screen, muted until the viewer asks for sound.
 * One big play/pause button sits on the center of the film; the space bar does the same while the film is on screen.
 * With reduced motion it waits on its poster for a click.
 */
/**
 * Glide down to the cases: about a second with ease-in-out, instead of the jump an
 * anchor makes (or the browser's own smooth scroll, which is quick and flat).
 * Reduced motion jumps straight there.
 */
function glideTo(id: string) {
  const target = document.getElementById(id)
  if (!target) return
  const to = target.getBoundingClientRect().top + window.scrollY
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    window.scrollTo(0, to)
    return
  }
  const from = window.scrollY
  const distance = to - from
  const duration = Math.min(1400, Math.max(700, Math.abs(distance) * 0.9))
  const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)
  const start = performance.now()
  const step = (now: number) => {
    const t = Math.min(1, (now - start) / duration)
    window.scrollTo(0, from + distance * ease(t))
    if (t < 1) requestAnimationFrame(step)
    else target.focus({ preventScroll: true })
  }
  requestAnimationFrame(step)
}

const toCases = (e: MouseEvent<HTMLAnchorElement>) => {
  e.preventDefault()
  glideTo('cases')
}

export function HeroFilm() {
  const section = useRef<HTMLElement>(null)
  const video = useRef<HTMLVideoElement>(null)
  const [muted, setMuted] = useState(true)
  const [playing, setPlaying] = useState(false)
  // The film plays once. When it ends, an arrow invites the viewer down to the cases.
  const [ended, setEnded] = useState(false)

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
    if (v.paused) {
      if (v.ended) v.currentTime = 0
      setEnded(false)
      v.play().catch(() => undefined)
    } else v.pause()
  }

  useSpaceToggle(section, togglePlay)

  return (
    <section ref={section} className={styles.hero} aria-label="Alibi, the film">
      <video
        ref={video}
        className={styles.film}
        poster="/video/alibi-hero-poster.webp"
        width={1920}
        height={1080}
        muted
        playsInline
        preload="none"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setEnded(true)}
        onClick={togglePlay}
        aria-label="A 71-second film: satellites have watched Earth for decades, and Alibi turns their records into plain answers"
      >
        {/* Same film, two encodes: phones and laptops get the 1280 one (about half the bytes). */}
        <source src="/video/alibi-hero-1280.mp4" type="video/mp4" media="(max-width: 1280px)" />
        <source src="/video/alibi-hero.mp4" type="video/mp4" />
      </video>
      <div className={styles.shade} aria-hidden="true" />
      <p className={`${styles.brand} wide`}>
        <Wordmark full />
      </p>
      {/* At the end the center stays clear for the film's last card; replay moves to the controls. */}
      {ended ? null : (
        <button
          type="button"
          className={playing ? `${styles.bigPlay} ${styles.bigPlayOn}` : styles.bigPlay}
          onClick={togglePlay}
          // A mouse click should not leave focus here: the space bar would keep driving the film after scrolling away.
          onPointerUp={(e) => e.currentTarget.blur()}
          aria-label={playing ? 'Pause the film' : 'Play the film'}
          title="Space bar plays and pauses"
        >
          <svg viewBox="0 0 24 24" width="40" height="40" aria-hidden="true" focusable="false">
            {playing ? (
              <path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" fill="currentColor" />
            ) : (
              <path d="M8 5.5v13l11-6.5z" fill="currentColor" />
            )}
          </svg>
        </button>
      )}
      <div className={styles.controls}>
        {ended ? (
          <button
            type="button"
            className={`${styles.control} ${styles.iconControl}`}
            onClick={togglePlay}
            onPointerUp={(e) => e.currentTarget.blur()}
            aria-label="Play the film again"
            title="Play again"
          >
            <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false">
              <path
                d="M12 5a7 7 0 1 1-6.6 4.7M5 4.5v5h5"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="square"
              />
            </svg>
          </button>
        ) : null}
        <button
          type="button"
          className={`${styles.control} ${styles.iconControl}`}
          onClick={toggleSound}
          aria-pressed={!muted}
          aria-label={muted ? 'Turn sound on' : 'Turn sound off'}
          title={muted ? 'Sound on' : 'Sound off'}
        >
          <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false">
            <path d="M4 9h4l5-4v14l-5-4H4z" fill="currentColor" />
            {muted ? (
              <path d="M16 9l5 6M21 9l-5 6" stroke="currentColor" strokeWidth="2" strokeLinecap="square" />
            ) : (
              <path
                d="M16 8.5a5 5 0 0 1 0 7M18.5 6a8.5 8.5 0 0 1 0 12"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              />
            )}
          </svg>
        </button>
        <p className={styles.keyHint}>
          <kbd>Space</kbd> {playing ? 'pauses' : ended ? 'plays again' : 'plays'}
        </p>
        {ended ? null : (
          <a href="#cases" onClick={toCases} className={styles.skip}>
            See the cases ↓
          </a>
        )}
      </div>
      {ended ? (
        <a href="#cases" onClick={toCases} className={styles.next} aria-label="Scroll down to the cases">
          <span>See the cases</span>
          <svg viewBox="0 0 24 24" width="32" height="32" aria-hidden="true" focusable="false">
            <path
              d="M12 4v15M5.5 12.5 12 19l6.5-6.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="square"
            />
          </svg>
        </a>
      ) : null}
    </section>
  )
}
