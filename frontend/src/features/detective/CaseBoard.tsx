'use client'

import { useId, useState } from 'react'
import { STATUS_WORDS } from './board'
import type { StampBeat } from './board'
import type { BoardEvent, SuspectStatus } from './events'
import { boardToggleLabel } from './panels'
import styles from './detective.module.css'

const TONE: Record<SuspectStatus, string> = {
  supported: styles.suspectSupported,
  hint: styles.suspectHint,
  ruled_out: styles.suspectRuledOut,
  trend_only: styles.suspectTrendOnly,
  open: styles.suspectOpen,
}

/** The suspects and their stamps. Folded behind one button on narrow screens. */
export function CaseBoard({ board, beats }: { board: BoardEvent | null; beats: StampBeat[] }) {
  const [open, setOpen] = useState(false)
  const bodyId = useId()
  const suspects = board?.suspects ?? []
  const fresh = new Set(beats.map((b) => b.suspectId))

  return (
    <section className={styles.board} aria-label="Case board">
      <button
        type="button"
        className={styles.boardToggle}
        aria-expanded={open}
        aria-controls={bodyId}
        onClick={() => setOpen((o) => !o)}
      >
        <span className={styles.legendChevron} aria-hidden="true">
          {open ? '−' : '+'}
        </span>
        {boardToggleLabel(suspects.length)}
      </button>
      <div id={bodyId} className={styles.boardBody} data-open={open}>
        <h2 className={styles.boardTitle}>Case board</h2>
        {suspects.length === 0 ? (
          <p className={styles.muted}>No suspects yet. They appear as the detective tests them.</p>
        ) : (
          <ul className={styles.suspects}>
            {suspects.map((s) => {
              const w = STATUS_WORDS[s.status] ?? STATUS_WORDS.open
              return (
                <li key={s.id} className={styles.suspect}>
                  <span
                    key={s.status}
                    className={`${styles.suspectStamp} ${TONE[s.status] ?? styles.suspectOpen}${fresh.has(s.id) ? ` ${styles.stampIn}` : ''}`}
                    title={w.meaning}
                  >
                    <span aria-hidden="true">{w.icon}</span>
                    <span>{w.text}</span>
                  </span>
                  <div className={styles.suspectText}>
                    <p className={styles.suspectLabel}>{s.label}</p>
                    {s.note && <p>{s.note}</p>}
                    {s.status === 'trend_only' && <p className={styles.muted}>{w.meaning}</p>}
                    {s.downgraded && <p className={styles.tertiary}>{s.downgraded}</p>}
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </section>
  )
}
