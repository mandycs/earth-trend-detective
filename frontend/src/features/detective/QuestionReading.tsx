import { useMemo } from 'react'
import { questionReading } from './instruments'
import type { Investigation } from './scenes'
import styles from './detective.module.css'

/**
 * "How Alibi read your question": the records the detective chose to answer the visitor's words (shown just above,
 * in the question box), each with the satellite or model behind it. The methods sit in a disclosure, for whoever
 * wants the real names.
 */
export function QuestionReading({ inv }: { inv: Investigation }) {
  const reading = useMemo(() => questionReading(inv), [inv])
  if (!inv.place || reading.records.length === 0) return null
  return (
    <section className={styles.reading} aria-labelledby="reading-title">
      <h2 id="reading-title" className={styles.readingTitle}>
        How Alibi read your question
      </h2>
      <p className={styles.readingArrow}>
        Your words became {reading.records.length === 1 ? 'this record' : 'these records'}, and this is where each
        one comes from:
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
