'use client'

import { useEffect, useState } from 'react'
import { FriendlyError } from '../explore/api'
import { fetchHistory } from './api'
import type { HistoryStep } from './api'
import { historyLine } from './panels'
import styles from './detective.module.css'

type Load =
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | { state: 'ok'; steps: HistoryStep[] }

const FALLBACK = 'The steps could not be loaded. Try again in a moment.'

/** The thread's checkpoints, each one a place to re-run from. Only for a finished live run. */
export function HistoryList({
  threadId,
  enabled,
  onFork,
}: {
  threadId: string | null
  enabled: boolean
  /** `all` is the full list, for working out which turn the step belongs to. */
  onFork: (step: HistoryStep, all: HistoryStep[]) => void
}) {
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const on = enabled && !!threadId

  useEffect(() => {
    if (!on || !threadId) return
    const ctl = new AbortController()
    setLoad({ state: 'loading' })
    fetchHistory(threadId, ctl.signal)
      .then((steps) => setLoad({ state: 'ok', steps: Array.isArray(steps) ? steps : [] }))
      .catch((e: unknown) => {
        if (ctl.signal.aborted) return
        setLoad({ state: 'error', message: e instanceof FriendlyError ? e.message : FALLBACK })
      })
    return () => ctl.abort()
  }, [on, threadId])

  if (!on) return null

  return (
    <section className={styles.history} aria-label="Re-run from a step">
      <h2 className={styles.boardTitle}>Re-run from a step</h2>
      {load.state === 'loading' && (
        <p className={styles.muted} aria-live="polite">
          Loading the steps…
        </p>
      )}
      {load.state === 'error' && (
        <p className={styles.sceneError} role="alert">
          {load.message}
        </p>
      )}
      {load.state === 'ok' &&
        (load.steps.length === 0 ? (
          <p className={styles.muted}>No steps to re-run yet.</p>
        ) : (
          <ul className={styles.historyRows}>
            {load.steps.map((s) => (
              <li key={s.checkpoint_id} className={styles.historyRow}>
                <span>
                  Step {s.step} · {historyLine(s)}
                </span>
                <button type="button" className={styles.textBtn} onClick={() => onFork(s, load.steps)}>
                  Re-run from this step
                </button>
              </li>
            ))}
          </ul>
        ))}
    </section>
  )
}
