import type { Ref } from 'react'
import { Stamp } from '../../lib/Stamp'
import { verdictFor } from './board'
import type { ChartModel } from './chart'
import { compareSides, sceneSummary, toolLabel } from './panels'
import type { Investigation, Scene } from './scenes'
import { SceneChart } from './SceneChart'
import styles from './detective.module.css'

export interface ScenePanelProps {
  inv: Investigation
  scene: Scene
  chart: ChartModel | null
  /** Shown as "Try again" on the error scene. */
  onRetry?: () => void
  /** Focus lands on the panel (tabIndex −1) when a run ends without an answer. */
  focusRef?: Ref<HTMLElement>
}

/** The subtitle of one scene: question line, plain tool label, summary, chart and verdict. */
export function ScenePanel({ inv, scene, chart, onRetry, focusRef }: ScenePanelProps) {
  const tool = scene.tool

  if (scene.kind === 'error') {
    return (
      <section className={styles.scene} aria-label="Investigation stopped" tabIndex={-1} ref={focusRef}>
        <p className={styles.sceneError} role="alert">
          {scene.note}
        </p>
        {onRetry && (
          <button type="button" className="btn" onClick={onRetry}>
            Try again
          </button>
        )}
      </section>
    )
  }

  const sides = tool?.tool === 'compare' && tool.state === 'done' ? compareSides(tool.result) : null
  const summary = tool?.state === 'done' ? sceneSummary(tool.summary, !!chart?.verdict) : null

  return (
    <section className={styles.scene} aria-label="Current step" tabIndex={-1} ref={focusRef}>
      {scene.kind === 'opening' && inv.place && <h2 className={styles.scenePlace}>{inv.place.name}</h2>}
      {scene.question && <p className={styles.sceneQuestion}>{scene.question}</p>}
      {tool && <p className={styles.sceneTool}>{toolLabel(tool.tool)}</p>}

      {tool?.state === 'running' && (
        <p className={styles.sceneState} aria-live="polite">
          Checking…
        </p>
      )}
      {tool?.state === 'failed' && (
        <p className={styles.sceneState}>
          <span aria-hidden="true">✕ </span>
          Could not check: {tool.reason}
        </p>
      )}
      {tool?.state === 'unfinished' && <p className={styles.sceneState}>Did not finish</p>}

      {summary && <p className={styles.sceneSummary}>{summary}</p>}
      {scene.kind === 'note' && scene.note && <p className={styles.sceneSummary}>{scene.note}</p>}

      {chart && <SceneChart model={chart} />}
      {chart?.verdict && <Stamp verdict={chart.verdict.verdict} direction={chart.verdict.direction} big />}

      {sides && (
        <ul className={styles.compare}>
          {sides.map((s, i) => {
            const v = verdictFor(s.testId, inv.board, s.raw)
            return (
              <li key={i} className={styles.compareSide}>
                <span className={styles.compareKey}>{i === 0 ? 'A' : 'B'}</span>
                <span>
                  {s.place}
                  {s.years && <span className={styles.compareYears}> · {s.years}</span>}
                </span>
                {v && <Stamp verdict={v.verdict} direction={v.direction} />}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
