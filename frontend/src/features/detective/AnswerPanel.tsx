import type { AnswerEvent, DoneEvent } from './events'
import { CLUE_LINE, TEMPLATE_LINE, checkLine, notMeasuredLine } from './panels'
import styles from './detective.module.css'

/** The ending: the answer, the clue line, the check line and what was not measured. */
export function AnswerPanel({ answer, done }: { answer: AnswerEvent; done: DoneEvent | null }) {
  return (
    <section className={styles.answer} aria-label="Answer">
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
    </section>
  )
}
