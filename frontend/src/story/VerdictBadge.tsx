import type { SiteVariable, Verdict } from './types'

const LABELS: Record<Verdict, { icon: string; text: string; hint: string }> = {
  real: { icon: '✓', text: 'Real', hint: 'Statistically significant after correcting for chance.' },
  likely: { icon: '≈', text: 'Likely', hint: 'Suggestive, but not significant after correcting for chance.' },
  unknown: { icon: '?', text: "Can't tell yet", hint: 'The series is too short to separate a trend from noise.' },
}

/**
 * Verdict pill. Never colour alone: the icon and the words carry the meaning,
 * which is what the UX checklist asks for.
 */
export function VerdictBadge({ verdict, direction }: { verdict: Verdict; direction: SiteVariable['direction'] }) {
  const meta = LABELS[verdict]
  const arrow = verdict === 'unknown' ? '' : direction === 'down' ? ' ↓' : direction === 'up' ? ' ↑' : ''
  return (
    <span className={`badge badge-${verdict}`} title={meta.hint}>
      <span aria-hidden="true" className="badge-icon">
        {meta.icon}
      </span>
      <span>
        {meta.text}
        {arrow}
      </span>
    </span>
  )
}
