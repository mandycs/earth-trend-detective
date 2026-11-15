'use client'

import dynamic from 'next/dynamic'
import Link from 'next/link'
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { Wordmark } from '../../brand/Wordmark'
import { fetchCaseLayers } from './api'
import type { HistoryStep } from './api'
import { AnswerPanel } from './AnswerPanel'
import { CaseBoard } from './CaseBoard'
import { chartFor } from './chart'
import type { Bbox } from './events'
import { HistoryList } from './HistoryList'
import type { PickMode, PickResult } from './map/draw'
import { EMPTY_VIEW, mapViewAt } from './map/mapView'
import type { CaseLayers } from './map/mapView'
import { historyEnabled, isActiveRun, recordedDate } from './panels'
import { QuestionBox } from './QuestionBox'
import type { RecordingChip } from './replay'
import type { Target } from './request'
import { ScenePanel } from './ScenePanel'
import { StepList } from './StepList'
import { useDetectiveRun } from './useDetectiveRun'
import type { StartOpts } from './useDetectiveRun'
import { useScenePlayer } from './useScenePlayer'
import { STACK_MAX, stackFor } from './stack/stackModel'
import type { Slab } from './stack/stackModel'
import { showSlab, slabCaption } from './stack/showSlab'
import {
  ANSWER_READY, COORDS_HINT, COORDS_PLACEHOLDER, focusTargetFor, forkTurn, localDate, parseLatLon, previewCamera,
} from './viewModel'
import type { FocusTarget } from './viewModel'
import styles from './detective.module.css'

const DetectiveMap = dynamic(() => import('./DetectiveMap'), {
  ssr: false,
  loading: () => (
    <div className={styles.mapWrap}>
      <p className={styles.mapLoading}>Loading the globe…</p>
    </div>
  ),
})

const EvidenceStack = dynamic(() => import('./stack/EvidenceStack'), { ssr: false })

export interface CaseChip { id: string; name: string; bbox: Bbox }

export interface DetectiveViewProps {
  cases: CaseChip[]
  recordings: RecordingChip[]
  initialSite?: string
  replay?: string
}

const caseTarget = (c: CaseChip): Target => ({ kind: 'case', siteId: c.id, name: c.name, bbox: c.bbox })

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    const q = window.matchMedia('(prefers-reduced-motion: reduce)')
    setReduced(q.matches)
    const on = (e: MediaQueryListEvent) => setReduced(e.matches)
    q.addEventListener('change', on)
    return () => q.removeEventListener('change', on)
  }, [])
  return reduced
}

/** "Watch a recorded case": a quiet text link that opens the list of recordings. Hidden when there are none. */
function RecordingsMenu({ recordings }: { recordings: RecordingChip[] }) {
  const [open, setOpen] = useState(false)
  const listId = useId()
  const wrap = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    const onDown = (e: PointerEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('pointerdown', onDown)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('pointerdown', onDown)
    }
  }, [open])

  if (recordings.length === 0) return null
  return (
    <div className={styles.recWrap} ref={wrap}>
      <button
        type="button"
        className={styles.textBtn}
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((o) => !o)}
      >
        Watch a recorded case
      </button>
      {open && (
        <ul id={listId} className={styles.recMenu}>
          {recordings.map((r) => (
            <li key={r.name}>
              <Link
                href={`/detective?replay=${encodeURIComponent(r.name)}`}
                className={styles.recItem}
                onClick={() => setOpen(false)}
              >
                <span>{r.question}</span>
                {r.started_at && <span className={styles.recDate}>Recorded {recordedDate(r.started_at)}</span>}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** The keyboard path to a place: "lat, lon" typed in. Map picking is click or tap only. */
function CoordsField({ onTarget }: { onTarget: (t: Target) => void }) {
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const id = useId()
  return (
    <form
      className={styles.coords}
      onSubmit={(e) => {
        e.preventDefault()
        const r = parseLatLon(text)
        if (r.ok) {
          setError(null)
          onTarget(r.target)
        } else setError(r.message)
      }}
    >
      <label htmlFor={`${id}-c`} className={styles.coordsLabel}>
        {COORDS_HINT}
      </label>
      <div className={styles.coordsRow}>
        <input
          id={`${id}-c`}
          className={styles.coordsInput}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={COORDS_PLACEHOLDER}
          inputMode="text"
          autoComplete="off"
          spellCheck={false}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-e` : undefined}
        />
        <button type="submit" className="btn">
          Use this place
        </button>
      </div>
      {error && (
        <p id={`${id}-e`} className={styles.qReason} role="alert">
          {error}
        </p>
      )}
    </form>
  )
}

export default function DetectiveView({ cases, recordings, initialSite, replay }: DetectiveViewProps) {
  const det = useDetectiveRun()
  const { run, inv, outcomes, turns, recording } = det
  const player = useScenePlayer(inv)
  const reducedMotion = useReducedMotion()

  const [target, setTarget] = useState<Target | null>(() => {
    const c = initialSite ? cases.find((x) => x.id === initialSite) : undefined
    return c ? caseTarget(c) : null
  })
  // Where the map looks before a run: a preselected, typed or chosen place (map clicks are already in view).
  const [preview, setPreview] = useState<{ target: Target; seq: number } | null>(() => (target ? { target, seq: 1 } : null))
  const [pickMode, setPickMode] = useState<PickMode>('point')
  const [pickError, setPickError] = useState<string | null>(null)
  const [forkFrom, setForkFrom] = useState<HistoryStep | null>(null)
  const [forkAt, setForkAt] = useState<number | null>(null)
  const [lastQuestion, setLastQuestion] = useState('')
  const lastAsk = useRef<{ target: Target; question: string; opts: StartOpts } | null>(null)
  // The safe default date of ongoing layers: today, in the viewer's own time zone.
  const now = useMemo(() => localDate(new Date()), [])

  // `?replay=<name>` plays on mount and whenever the link changes; leaving it ("Run it live") ends the replay.
  const { replay: playRecording, reset } = det
  const modeRef = useRef(run.mode)
  useEffect(() => {
    modeRef.current = run.mode
  }, [run.mode])
  useEffect(() => {
    if (replay) playRecording(replay)
    else if (modeRef.current === 'replay') reset()
  }, [replay, playRecording, reset])

  // Case layers for a solved case, from /sites/<id>/layers.json. A missing file just means none.
  const siteId = inv.place?.site_id ?? null
  // A string key: `inv.place.bbox` is a fresh array on every regrouping and would refetch on every event.
  const caseBboxKey = siteId ? (cases.find((c) => c.id === siteId)?.bbox ?? inv.place?.bbox ?? null)?.join(',') ?? null : null
  const [caseLayers, setCaseLayers] = useState<CaseLayers | null>(null)
  useEffect(() => {
    setCaseLayers(null)
    if (!siteId || !caseBboxKey) return
    const bbox = caseBboxKey.split(',').map(Number) as Bbox
    const ctl = new AbortController()
    fetchCaseLayers(siteId, ctl.signal)
      .then((rows) => !ctl.signal.aborted && setCaseLayers({ siteId, bbox, rows }))
      .catch(() => undefined)
    return () => ctl.abort()
  }, [siteId, caseBboxKey])

  const sceneView = useMemo(() => {
    if (!inv.place && preview && run.mode === 'live') return { ...EMPTY_VIEW, camera: previewCamera(preview.target, preview.seq) }
    return mapViewAt(inv, player.state.index, { caseLayers, now })
  }, [inv, player.state.index, caseLayers, now, preview, run.mode])

  // ---- the exploded evidence stack (Task 17): the ending's closing beat ----
  const atEnding = player.scene?.kind === 'ending'
  const stack = useMemo(
    () => (atEnding ? stackFor(inv, sceneView, { max: STACK_MAX, ctx: { caseLayers, now } }) : null),
    [atEnding, inv, sceneView, caseLayers, now],
  )
  const [stackMounted, setStackMounted] = useState(false)
  const [exploded, setExploded] = useState(false)
  const [shownSlab, setShownSlab] = useState<Slab | null>(null)
  const explodeRef = useRef<HTMLButtonElement>(null)
  // A slab picked from the stack stays on the map only while the ending is on screen.
  useEffect(() => {
    if (!atEnding) setShownSlab(null)
  }, [atEnding])
  useEffect(() => {
    if (!stackMounted) return
    const raf = requestAnimationFrame(() => setExploded(true))
    return () => cancelAnimationFrame(raf)
  }, [stackMounted])
  const openStack = () => {
    setShownSlab(null)
    setExploded(false)
    setStackMounted(true)
  }
  const closeStack = useCallback(() => setExploded(false), [])
  const pickSlab = useCallback(
    (key: string) => {
      setShownSlab(stack?.slabs.find((s) => s.key === key) ?? null)
      setExploded(false)
    },
    [stack],
  )
  const onStackCollapsed = useCallback(() => {
    setStackMounted(false)
    explodeRef.current?.focus({ preventScroll: true })
  }, [])
  const view = useMemo(() => (shownSlab ? showSlab(sceneView, shownSlab) : sceneView), [sceneView, shownSlab])

  const active = isActiveRun(run.status)
  const replaying = run.mode === 'replay'
  const followUp = !replaying && run.status === 'finished' && !!run.threadId
  const canPick = !active && !replaying
  const scene = player.scene
  const chart = useMemo(() => (scene ? chartFor(inv, scene) : null), [inv, scene])
  const outcome = scene?.kind === 'ending' ? outcomes[scene.key] : undefined
  const lastIndex = inv.scenes.length - 1
  const atLast = player.state.index >= lastIndex

  /** A new place. Once a run has been shown, a new place is a new case. Typed and chosen places are flown to. */
  const choose = useCallback(
    (t: Target, fly = true) => {
      if (run.status !== 'idle') {
        reset()
        setForkFrom(null)
        setForkAt(null)
      }
      setPickError(null)
      setTarget(t)
      setPreview((p) => (fly ? { target: t, seq: (p?.seq ?? 0) + 1 } : null))
    },
    [run.status, reset],
  )

  const onPick = useCallback(
    (r: PickResult) => {
      if ('error' in r) setPickError(r.error)
      else choose(r.target, false)
    },
    [choose],
  )

  // ---- focus follows the run (fix round 1) ----
  const stopRef = useRef<HTMLButtonElement>(null)
  const answerRef = useRef<HTMLHeadingElement>(null)
  const sceneRef = useRef<HTMLElement>(null)
  const messageRef = useRef<HTMLParagraphElement>(null)
  const prevStatus = useRef(run.status)
  const [pendingFocus, setPendingFocus] = useState<Exclude<FocusTarget, 'stop'> | null>(null)
  const [announce, setAnnounce] = useState('')
  useEffect(() => {
    const t = focusTargetFor(prevStatus.current, run.status, run.mode, inv.answer !== null)
    prevStatus.current = run.status
    if (t === 'stop') {
      setPendingFocus(null)
      setAnnounce('')
      stopRef.current?.focus()
    } else if (t) setPendingFocus(t)
  }, [run.status, run.mode, inv.answer])
  // The ending is paced: focus waits until the player shows the last scene (or the answer itself).
  useEffect(() => {
    if (!pendingFocus || (inv.scenes.length > 0 && !atLast)) return
    const el = pendingFocus === 'answer' ? answerRef.current : (sceneRef.current ?? messageRef.current)
    if (!el) return
    el.focus({ preventScroll: true })
    el.scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'start' })
    if (pendingFocus === 'answer') setAnnounce(ANSWER_READY)
    setPendingFocus(null)
  })

  const ask = (question: string) => {
    if (!target) return
    const opts: StartOpts = forkFrom
      ? { followUp: true, checkpointId: forkFrom.checkpoint_id, keepTurns: forkAt ?? undefined }
      : followUp ? { followUp: true } : {}
    lastAsk.current = { target, question, opts }
    setLastQuestion(question)
    setForkFrom(null)
    setForkAt(null)
    det.start(target, question, opts)
  }

  const retry = () => {
    const a = lastAsk.current
    if (a) det.start(a.target, a.question, { ...a.opts, retry: true })
  }

  const fork = (step: HistoryStep, all: HistoryStep[]) => {
    setForkFrom(step)
    setForkAt(forkTurn(all, step))
    document.getElementById('detective-question')?.scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'start' })
  }

  // One box per turn: a follow-up or a fork opens empty, never with the previous question in it.
  const boxKey = replaying ? 'replay' : followUp ? `turn-${turns}-${forkFrom?.checkpoint_id ?? 'next'}` : 'ask'
  const mapTarget = replaying ? (recording?.target ?? null) : target

  return (
    <div className={styles.shell}>
      <header className={styles.bar}>
        <Link href="/" className={`${styles.wordmark} wide`}>
          <Wordmark />
        </Link>
        <RecordingsMenu recordings={recordings} />
      </header>

      <div className={styles.stage}>
        <div className={styles.mapArea}>
          <DetectiveMap
            view={view}
            target={mapTarget}
            pickMode={pickMode}
            pickEnabled={canPick}
            onPick={onPick}
            reducedMotion={reducedMotion}
          />
        </div>
        <div className={styles.scrim} aria-hidden="true" />

        <main className={styles.column} id="detective-question">
          <h1 className="sr-only">Your case</h1>
          <QuestionBox
            key={boxKey}
            target={target}
            status={run.status}
            mode={run.mode}
            followUp={followUp}
            forkFrom={forkFrom}
            initialQuestion={replaying ? (recording?.question ?? '') : boxKey === 'ask' ? lastQuestion : ''}
            onAsk={ask}
            onStop={det.stop}
            onCancelFork={() => {
              setForkFrom(null)
              setForkAt(null)
            }}
            onPickMode={setPickMode}
            pickMode={pickMode}
            recordedAt={recording?.startedAt ?? null}
            stopRef={stopRef}
          />
          <p className="sr-only" aria-live="polite">
            {announce}
          </p>

          {pickError && (
            <p className={styles.qReason} role="alert">
              {pickError}
            </p>
          )}

          {canPick && !followUp && !forkFrom && (
            <>
              {!target && cases.length > 0 && (
                <div className={styles.chips}>
                  <p className={styles.chipsLabel}>Or open a solved case:</p>
                  <ul className={styles.chipRow}>
                    {cases.slice(0, 3).map((c) => (
                      <li key={c.id}>
                        <button type="button" className={styles.chip} onClick={() => choose(caseTarget(c))}>
                          {c.name}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <CoordsField onTarget={choose} />
            </>
          )}

          {run.message && (
            <p
              ref={messageRef}
              tabIndex={-1}
              className={run.status === 'failed' ? styles.sceneError : styles.runNote}
              role={run.status === 'failed' ? 'alert' : 'status'}
            >
              {run.message}
            </p>
          )}

          {scene && (
            <ScenePanel
              inv={inv}
              scene={scene}
              chart={chart}
              onRetry={!replaying && lastAsk.current ? retry : undefined}
              focusRef={sceneRef}
            />
          )}

          {inv.place && <CaseBoard board={inv.board} beats={scene?.stamps ?? []} />}

          {outcome?.answer && <AnswerPanel answer={outcome.answer} done={outcome.done} headingRef={answerRef} />}

          {stack && stack.slabs.length > 0 && (
            <div className={styles.explodeRow}>
              <button type="button" ref={explodeRef} className="btn" onClick={openStack} aria-haspopup="dialog">
                Explode the evidence
              </button>
              {shownSlab && (
                <p className={styles.runNote} role="status">
                  On the map: {slabCaption(shownSlab)}.{' '}
                  <button type="button" className={styles.textBtn} onClick={() => setShownSlab(null)}>
                    Back to the ending view
                  </button>
                </p>
              )}
            </div>
          )}

          {player.running && (
            <div className={styles.playerRow}>
              <button type="button" className={styles.textBtn} onClick={player.state.paused ? player.resume : player.pause}>
                {player.state.paused ? 'Resume' : 'Pause'}
              </button>
            </div>
          )}

          <StepList
            inv={inv}
            index={player.state.index}
            pinned={player.state.pinned}
            onGoto={player.goto}
            onLive={player.live}
          />

          <HistoryList threadId={run.threadId} enabled={historyEnabled(run.status, run.mode, run.threadId)} onFork={fork} />
        </main>
      </div>

      {stackMounted && stack && (
        <EvidenceStack
          model={stack}
          exploded={exploded}
          onPick={pickSlab}
          onClose={closeStack}
          onCollapsed={onStackCollapsed}
          reducedMotion={reducedMotion}
        />
      )}
    </div>
  )
}
