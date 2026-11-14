import { useEffect, useRef } from 'react'

export interface TimelineProps {
  first: number
  last: number
  year: number
  playing: boolean
  hasFrames: boolean
  onScrub: (year: number) => void
  onToggle: () => void
}

/**
 * Year scrubber for the story mode. The slider is a real <input type=range> so
 * keyboard, screen reader and touch all work without extra code.
 */
export function Timeline({ first, last, year, playing, hasFrames, onScrub, onToggle }: TimelineProps) {
  const trackRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!hasFrames) return
    const element = trackRef.current
    if (!element) return
    const ratio = (year - first) / Math.max(last - first, 1)
    element.style.setProperty('--progress', `${Math.round(ratio * 100)}%`)
  }, [year, first, last, hasFrames])

  return (
    <div className="timeline" aria-label="Year timeline">
      <button
        type="button"
        className="play"
        onClick={onToggle}
        disabled={!hasFrames}
        aria-pressed={playing}
        aria-label={playing ? 'Pause the timeline' : 'Play the timeline'}
      >
        <span aria-hidden="true">{playing ? '❚❚' : '▶'}</span>
        <span className="play-label">{playing ? 'Pause' : 'Play'}</span>
      </button>

      <div className="timeline-track" ref={trackRef}>
        <input
          type="range"
          min={first}
          max={last}
          step={1}
          value={year}
          disabled={!hasFrames}
          aria-label="Year on the timeline"
          aria-valuetext={`${year}`}
          onChange={(event) => onScrub(Number(event.target.value))}
        />
        <div className="timeline-ticks" aria-hidden="true">
          <span>{first}</span>
          <span>{last}</span>
        </div>
      </div>

      <output className="timeline-year" aria-live="polite">
        {hasFrames ? year : 'No yearly frames'}
      </output>
    </div>
  )
}
