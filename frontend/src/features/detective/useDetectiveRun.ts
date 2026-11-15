'use client'

// Owns one investigation: a live stream from the backend or a recorded run replayed on its own timing.
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { FriendlyError } from '../explore/api'
import { fetchRecording, streamDetective } from './api'
import type { DetEvent } from './events'
import { RECORDING_NAME, parseRecording, replaySchedule, targetFromRequest } from './replay'
import { requestBody } from './request'
import type { Target } from './request'
import { IDLE_RUN, runReducer } from './runState'
import type { RunState } from './runState'
import { groupScenes } from './scenes'
import type { Investigation } from './scenes'
import { turnCount, turnOutcomes, wrapTarget } from './viewModel'
import type { TurnOutcome } from './viewModel'

const NOT_AVAILABLE = 'This recording is not available.'
const GENERIC = 'The investigation failed. Try again in a moment.'

export interface StartOpts { followUp?: boolean; checkpointId?: string }
export interface LoadedRecording { name: string; question: string; startedAt: string; target: Target | null }

export interface DetectiveRun {
  run: RunState
  inv: Investigation
  /** Answer and `done` of every turn, keyed by the ending scene key. */
  outcomes: Record<string, TurnOutcome>
  /** Turns started so far (place events), for keying the question box per turn. */
  turns: number
  recording: LoadedRecording | null
  start: (target: Target, question: string, opts?: StartOpts) => void
  stop: () => void
  replay: (name: string) => void
  reset: () => void
}

export function useDetectiveRun(): DetectiveRun {
  const [run, dispatch] = useReducer(runReducer, IDLE_RUN)
  // Earlier turns of the same thread. The reducer clears `events` on every start; a follow-up keeps them here.
  const [earlier, setEarlier] = useState<DetEvent[]>([])
  const [recording, setRecording] = useState<LoadedRecording | null>(null)
  const ctl = useRef<AbortController | null>(null)
  const timers = useRef<ReturnType<typeof setTimeout>[]>([])
  const runRef = useRef(run)
  useEffect(() => {
    runRef.current = run
  }, [run])

  const halt = useCallback(() => {
    ctl.current?.abort()
    ctl.current = null
    for (const t of timers.current) clearTimeout(t)
    timers.current = []
  }, [])

  useEffect(() => halt, [halt])

  const start = useCallback(
    (target: Target, question: string, opts: StartOpts = {}) => {
      halt()
      const followUp = opts.followUp === true
      const prev = runRef.current
      // State updates queue in order: the earlier turns are read from the run before `start` clears it.
      setEarlier((e) => (followUp ? [...e, ...prev.events] : []))
      setRecording(null)
      const c = new AbortController()
      ctl.current = c
      dispatch({ type: 'start', mode: 'live', keepThread: followUp })
      // Follow-ups and forks use the reducer's thread, never a made-up id.
      const body = requestBody(wrapTarget(target), question, {
        threadId: followUp ? prev.threadId : null,
        checkpointId: opts.checkpointId ?? null,
      })
      streamDetective(body, (e) => !c.signal.aborted && dispatch({ type: 'event', event: e }), c.signal)
        .then(() => {
          if (!c.signal.aborted) dispatch({ type: 'end' })
        })
        .catch((e: unknown) => {
          // An aborted run was stopped (or replaced) on purpose: `stop` already said so.
          if (c.signal.aborted) return
          dispatch({ type: 'fail', message: e instanceof FriendlyError ? e.message : GENERIC })
        })
    },
    [halt],
  )

  const stop = useCallback(() => {
    halt()
    dispatch({ type: 'stop' })
  }, [halt])

  const reset = useCallback(() => {
    halt()
    setEarlier([])
    setRecording(null)
    dispatch({ type: 'reset' })
  }, [halt])

  const replay = useCallback(
    (name: string) => {
      halt()
      setEarlier([])
      setRecording(null)
      dispatch({ type: 'start', mode: 'replay', keepThread: false })
      if (!RECORDING_NAME.test(name)) {
        dispatch({ type: 'fail', message: NOT_AVAILABLE })
        return
      }
      const c = new AbortController()
      ctl.current = c
      fetchRecording(name, c.signal)
        .then((raw) => {
          if (c.signal.aborted) return
          const rec = parseRecording(raw)
          if (!rec) {
            dispatch({ type: 'fail', message: NOT_AVAILABLE })
            return
          }
          setRecording({ name, question: rec.question, startedAt: rec.started_at, target: targetFromRequest(rec.request) })
          const schedule = replaySchedule(rec)
          for (const { atMs, event } of schedule) {
            timers.current.push(setTimeout(() => dispatch({ type: 'event', event }), atMs))
          }
          const last = schedule.length > 0 ? schedule[schedule.length - 1].atMs : 0
          timers.current.push(setTimeout(() => dispatch({ type: 'end' }), last + 50))
        })
        .catch(() => {
          if (!c.signal.aborted) dispatch({ type: 'fail', message: NOT_AVAILABLE })
        })
    },
    [halt],
  )

  const all = useMemo(() => (earlier.length === 0 ? run.events : [...earlier, ...run.events]), [earlier, run.events])
  const ended = run.status === 'stopped' || run.status === 'cut' || run.status === 'failed'
  const inv = useMemo(() => groupScenes(all, { ended }), [all, ended])
  const outcomes = useMemo(() => turnOutcomes(all), [all])
  const turns = useMemo(() => turnCount(all), [all])

  return { run, inv, outcomes, turns, recording, start, stop, replay, reset }
}
