import { useRef } from 'react'

export interface CurtainProps {
  split: number
  onSplit: (value: number) => void
  left: string
  right: string
  /** When false the line is shown but cannot be dragged (documentary). */
  interactive?: boolean
}

/**
 * Vertical divider across the map: one layer left of it, the other right.
 * Drag the handle, or use the arrow keys on the hidden range input.
 */
export function Curtain({ split, onSplit, left, right, interactive = true }: CurtainProps) {
  const box = useRef<HTMLDivElement>(null)

  const fromPointer = (clientX: number) => {
    const rect = box.current?.getBoundingClientRect()
    if (!rect) return
    onSplit(Math.min(0.95, Math.max(0.05, (clientX - rect.left) / rect.width)))
  }

  return (
    <div ref={box} className={interactive ? 'curtain' : 'curtain curtain-still'}>
      <span className="curtain-line" style={{ left: `${split * 100}%` }} aria-hidden="true">
        {interactive ? (
          <span
            className="curtain-handle"
            onPointerDown={(e) => {
              e.currentTarget.setPointerCapture(e.pointerId)
              fromPointer(e.clientX)
            }}
            onPointerMove={(e) => {
              if (e.currentTarget.hasPointerCapture(e.pointerId)) fromPointer(e.clientX)
            }}
          >
            ⇆
          </span>
        ) : null}
      </span>
      <span className="curtain-label curtain-left" style={{ right: `${(1 - split) * 100}%` }}>
        {left}
      </span>
      <span className="curtain-label curtain-right" style={{ left: `${split * 100}%` }}>
        {right}
      </span>
      {interactive ? (
        <input
          className="sr-only"
          type="range"
          min={5}
          max={95}
          value={Math.round(split * 100)}
          aria-label={`Curtain between ${left} and ${right}`}
          onChange={(e) => onSplit(Number(e.target.value) / 100)}
        />
      ) : null}
    </div>
  )
}
