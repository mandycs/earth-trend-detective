'use client'

// Drives the pure scene player with a 250 ms clock (spec §5.5b).
import { useCallback, useEffect, useReducer, useRef } from 'react'
import { INITIAL_PLAYER, playerReducer } from './player'
import type { PlayerState } from './player'
import type { Investigation, Scene } from './scenes'

const TICK_MS = 250

export interface ScenePlayer {
  state: PlayerState
  scene: Scene | null
  goto: (i: number) => void
  live: () => void
  /** The clock is ticking: scenes may still advance (Pause makes sense). */
  running: boolean
  pause: () => void
  resume: () => void
}

export function useScenePlayer(inv: Investigation): ScenePlayer {
  const [state, dispatch] = useReducer(playerReducer, INITIAL_PLAYER)
  const scenes = inv.scenes
  const scenesRef = useRef(scenes)
  useEffect(() => {
    scenesRef.current = scenes
  }, [scenes])

  // A new run (its opening scene changes, or the scenes empty out) starts the player again.
  const openingKey = scenes[0]?.key ?? null
  useEffect(() => {
    dispatch({ type: 'reset', now: performance.now() })
  }, [openingKey])

  const last = scenes.length - 1
  const atEnd = state.index >= last
  const running = scenes.length > 0 && !(inv.finished && atEnd)
  useEffect(() => {
    if (!running) return
    const id = setInterval(() => dispatch({ type: 'tick', now: performance.now(), scenes: scenesRef.current }), TICK_MS)
    return () => clearInterval(id)
  }, [running])

  const goto = useCallback((i: number) => {
    const max = Math.max(0, scenesRef.current.length - 1)
    dispatch({ type: 'goto', index: Math.min(i, max), now: performance.now() })
  }, [])
  const live = useCallback(() => dispatch({ type: 'live', now: performance.now(), scenes: scenesRef.current }), [])
  const pause = useCallback(() => dispatch({ type: 'pause' }), [])
  const resume = useCallback(() => dispatch({ type: 'resume', now: performance.now() }), [])

  const scene = scenes.length > 0 ? scenes[Math.min(state.index, last)] : null
  return { state, scene, goto, live, running, pause, resume }
}
