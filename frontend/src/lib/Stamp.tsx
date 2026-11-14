import type { Direction, Verdict } from '../story/types'
import { stampFor } from './cases'

/** Verdict stamp. Icon and words carry the meaning; the fill only reinforces it. */
export function Stamp({
  verdict,
  direction,
  big = false,
  className = '',
}: {
  verdict: Verdict
  direction: Direction
  big?: boolean
  className?: string
}) {
  const s = stampFor(verdict, direction)
  const tone = verdict === 'unknown' || direction === 'flat' ? 'unknown' : verdict
  return (
    <span className={`stamp stamp-${tone}${big ? ' stamp-big' : ''} ${className}`} title={s.meaning}>
      <span aria-hidden="true">{s.icon}</span>
      <span>{s.text}</span>
    </span>
  )
}
