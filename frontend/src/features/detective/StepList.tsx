import { stepRow } from './panels'
import type { Investigation } from './scenes'
import styles from './detective.module.css'

export interface StepListProps {
  inv: Investigation
  index: number
  pinned: boolean
  onGoto: (i: number) => void
  onLive: () => void
}

/** Every scene as one row; the user can look back at any of them. */
export function StepList({ inv, index, pinned, onGoto, onLive }: StepListProps) {
  if (inv.scenes.length === 0) return null
  const current = Math.min(index, inv.scenes.length - 1)
  return (
    <nav className={styles.steps} aria-label="Steps">
      <ol>
        {inv.scenes.map((s, i) => {
          const r = stepRow(s)
          return (
            <li key={s.key}>
              <button
                type="button"
                className={styles.step}
                aria-current={i === current ? 'step' : undefined}
                onClick={() => onGoto(i)}
              >
                <span className={styles.stepIcon} aria-hidden="true">
                  {r.icon}
                </span>
                <span>{r.label}</span>
                <span className="sr-only">, {r.state}</span>
              </button>
            </li>
          )
        })}
      </ol>
      {pinned && (
        <button type="button" className={styles.textBtn} onClick={onLive}>
          Back to live
        </button>
      )}
    </nav>
  )
}
