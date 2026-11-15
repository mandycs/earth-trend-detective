import { useMemo } from 'react'
import { questionReading } from './instruments'
import type { Investigation } from './scenes'
import styles from './detective.module.css'

/**
 * "How Alibi read your question": the visitor's own words, then the records the detective chose to answer them,
 * each with the instrument that measured it. The methods sit in a disclosure, for whoever wants the real names.
 */
export function QuestionReading({ inv, question }: { inv: Investigation; question: string }) {
  const reading = useMemo(() => questionReading(inv), [inv])
  if (!inv.place || reading.records.length === 0) return null
  return (
    <section className={styles.reading} aria-labelledby="reading-title">
      <h2 id="reading-title" className={styles.readingTitle}>
        How Alibi read your question
      </h2>
      {question && <p className={styles.readingWords}>“{question}”</p>}
      <p className={styles.readingArrow}>
        <span aria-hidden="true">↓ </span>
        {reading.records.length === 1 ? 'turned into this record:' : 'turned into these records:'}
      </p>
      <ul className={styles.readingRecords}>
        {reading.records.map((r) => (
          <li key={r.varId} className={styles.readingRecord}>
            <span className={styles.readingLabel}>{r.label}</span>
            {r.instrument && <span className={styles.readingInstrument}>{r.instrument}</span>}
          </li>
        ))}
      </ul>
      {reading.methods.length > 0 && (
        <details className={styles.readingMethods}>
          <summary>The methods behind the words</summary>
          <ul>
            {reading.methods.map((m) => (
              <li key={m.tool}>{m.text}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}
