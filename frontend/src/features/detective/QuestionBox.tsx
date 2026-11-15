'use client'

import { useId, useState } from 'react'
import type { Ref } from 'react'
import Link from 'next/link'
import type { HistoryStep } from './api'
import type { PickMode } from './map/draw'
import type { Target } from './request'
import { targetLabel } from './request'
import type { RunStatus } from './runState'
import {
  NO_TARGET_HINT, QUESTION_MAX, QUESTION_PLACEHOLDER, askBlocker, forkLine, isActiveRun, replayLine,
} from './panels'
import styles from './detective.module.css'

export interface QuestionBoxProps {
  target: Target | null
  status: RunStatus
  mode: 'live' | 'replay'
  followUp: boolean
  forkFrom: HistoryStep | null
  initialQuestion: string
  onAsk: (question: string) => void
  onStop: () => void
  onCancelFork: () => void
  onPickMode: (m: PickMode) => void
  pickMode: PickMode
  /** `started_at` of the recording, for the replay line. */
  recordedAt?: string | null
  /** Focus lands here when a live run starts (the Ask button it replaces is gone). */
  stopRef?: Ref<HTMLButtonElement>
}

export function QuestionBox({
  target, status, mode, followUp, forkFrom, initialQuestion, onAsk, onStop, onCancelFork, onPickMode, pickMode,
  recordedAt = null, stopRef,
}: QuestionBoxProps) {
  const [question, setQuestion] = useState(initialQuestion)
  const id = useId()
  const reasonId = `${id}-reason`
  const active = isActiveRun(status)

  if (mode === 'replay') {
    return (
      <section className={styles.qbox} aria-label="Question">
        <p className={styles.qReadonly}>{initialQuestion}</p>
        <p className={styles.qMeta}>{replayLine(recordedAt)}</p>
        <Link href="/detective" className={styles.textBtn}>
          Run it live
        </Link>
      </section>
    )
  }

  const blocker = askBlocker(target, question)
  const showPick = !followUp && !active

  return (
    <form
      className={styles.qbox}
      aria-label="Question"
      onSubmit={(e) => {
        e.preventDefault()
        if (!blocker && !active) onAsk(question.trim())
      }}
    >
      {target ? (
        <p className={styles.qMeta}>{targetLabel(target)}</p>
      ) : (
        <p className={styles.qHint}>{NO_TARGET_HINT}</p>
      )}

      {showPick && (
        <div className={styles.toggleRow} role="group" aria-label="How to pick a place">
          {(['point', 'box'] as const).map((m) => (
            <button
              key={m}
              type="button"
              className={styles.toggle}
              aria-pressed={pickMode === m}
              onClick={() => onPickMode(m)}
            >
              {m === 'point' ? 'Point' : 'Box'}
            </button>
          ))}
        </div>
      )}

      {forkFrom && (
        <div className={styles.forkLine}>
          <p>{forkLine(forkFrom.step, forkFrom.summary)}</p>
          <button type="button" className={styles.textBtn} onClick={onCancelFork}>
            Cancel
          </button>
        </div>
      )}

      <label htmlFor={`${id}-q`} className="sr-only">
        Your question
      </label>
      <textarea
        id={`${id}-q`}
        className={styles.qInput}
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        placeholder={QUESTION_PLACEHOLDER}
        maxLength={QUESTION_MAX}
        rows={3}
        readOnly={active}
        aria-describedby={blocker ? reasonId : undefined}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) e.currentTarget.form?.requestSubmit()
        }}
      />

      <div className={styles.qActions}>
        {active ? (
          <>
            <p className={styles.qStatus} aria-live="polite">
              {status === 'connecting' ? 'Opening the case…' : ''}
            </p>
            <button type="button" className="btn" onClick={onStop} ref={stopRef}>
              Stop
            </button>
          </>
        ) : (
          <>
            <button type="submit" className="btn btn-primary" disabled={blocker !== null}>
              {followUp ? 'Ask' : 'Investigate'}
            </button>
            {blocker && (
              <p id={reasonId} className={styles.qReason}>
                {blocker}
              </p>
            )}
          </>
        )}
      </div>
    </form>
  )
}
