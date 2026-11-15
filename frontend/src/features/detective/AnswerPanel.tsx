import type { Ref } from 'react'
import type { AnswerEvent, DoneEvent } from './events'
import {
  CLUE_LINE, NEXT_REPLAY_LINE, NEXT_TITLE, TEMPLATE_LINE, checkLine, nextQuestionChips, notMeasuredLine,
} from './panels'
import styles from './detective.module.css'

/** The ending: the answer, the clue line, the check line, what was not measured and what to ask next. */
export function AnswerPanel({
  answer, done, headingRef, onAskNext, replay = false,
}: {
  answer: AnswerEvent
  done: DoneEvent | null
  headingRef?: Ref<HTMLHeadingElement>
  /** Asks a suggested question in the same thread; absent when it cannot be asked (a replay, a run going). */
  onAskNext?: (question: string) => void
  /** A recording: the questions are shown, not asked (there is no live thread behind it). */
  replay?: boolean
}) {
  // Live with no way to ask (a follow-up is running): no chips that do nothing.
  const next = onAskNext || replay ? nextQuestionChips(answer) : []
  return (
    <section className={styles.answer} aria-label="Answer">
      <h2 className={styles.boardTitle} tabIndex={-1} ref={headingRef}>
        The answer
      </h2>
      <p className={styles.answerText}>{answer.text}</p>
      <p className={styles.answerClue}>{CLUE_LINE}</p>
      <p className={styles.answerCheck}>{checkLine(answer, done)}</p>
      {answer.not_measured.length > 0 && (
        <div className={styles.notMeasured}>
          <h3 className={styles.notMeasuredTitle}>Not measured here</h3>
          <ul>
            {answer.not_measured.map((n, i) => (
              <li key={i}>{notMeasuredLine(n.label, n.reason)}</li>
            ))}
          </ul>
        </div>
      )}
      {answer.source === 'template' && <p className={styles.muted}>{TEMPLATE_LINE}</p>}
      {next.length > 0 && (
        <div className={styles.nextAsk}>
          <h3 className={styles.notMeasuredTitle}>{NEXT_TITLE}</h3>
          <ul className={styles.nextRow}>
            {next.map((q) => (
              <li key={q}>
                {onAskNext ? (
                  <button type="button" className={`${styles.chip} ${styles.nextChip}`} onClick={() => onAskNext(q)}>
                    {q}
                  </button>
                ) : (
                  <span className={`${styles.chip} ${styles.nextChip} ${styles.nextChipStatic}`}>{q}</span>
                )}
              </li>
            ))}
          </ul>
          {!onAskNext && <p className={styles.muted}>{NEXT_REPLAY_LINE}</p>}
        </div>
      )}
    </section>
  )
}
