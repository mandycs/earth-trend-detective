'use client'

// Story mode's "Layers" (Task 17, deferred to Task 16): a solved case's own data layers as the exploded stack.
// Self-contained so the story view only gains one element: it fetches sites/<id>/layers.json on demand.
import dynamic from 'next/dynamic'
import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { fetchCaseLayers } from '../api'
import type { Bbox } from '../events'
import { caseStackNote, stackForCase } from './stackModel'
import type { StackModel } from './stackModel'

const EvidenceStack = dynamic(() => import('./EvidenceStack'), { ssr: false })

const LEDE = "Each slab is one of this case's data layers, over the same box. The year drawn is on each card."

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

export function CaseLayersButton({ siteId, bbox, className }: { siteId: string; bbox: Bbox; className?: string }) {
  const reducedMotion = useReducedMotion()
  const [model, setModel] = useState<StackModel | null>(null)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<{ text: string; retry: boolean } | null>(null)
  const [exploded, setExploded] = useState(false)
  const explodedRef = useRef(false)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const refocus = useRef(false)
  const ctl = useRef<AbortController | null>(null)

  useEffect(() => {
    explodedRef.current = exploded
  }, [exploded])
  useEffect(() => () => ctl.current?.abort(), [])
  // A new case: whatever was open belongs to the old one.
  useEffect(() => {
    ctl.current?.abort()
    ctl.current = null
    setBusy(false)
    setModel(null)
    setNote(null)
  }, [siteId])

  // aria-modal needs a real trap: the page behind goes inert while the stack is open (the stack itself is portalled
  // to <body>, outside it).
  useEffect(() => {
    if (!model) return
    const page = buttonRef.current?.closest('.st') as HTMLElement | null
    if (!page) return
    page.inert = true
    return () => {
      page.inert = false
    }
  }, [model])

  // Rise on the frame after mounting, so the slabs start on the ground.
  useEffect(() => {
    if (!model) return
    const raf = requestAnimationFrame(() => setExploded(true))
    return () => cancelAnimationFrame(raf)
  }, [model])
  useEffect(() => {
    if (model || !refocus.current) return
    refocus.current = false
    buttonRef.current?.focus({ preventScroll: true })
  }, [model])

  const collapsed = useCallback(() => {
    refocus.current = true
    setExploded(false)
    setModel(null)
  }, [])
  const close = useCallback(() => {
    if (explodedRef.current) setExploded(false)
    else collapsed()
  }, [collapsed])

  const open = () => {
    if (busy) return
    ctl.current?.abort()
    const c = new AbortController()
    ctl.current = c
    setBusy(true)
    setNote(null)
    fetchCaseLayers(siteId, c.signal)
      .then((rows) => {
        if (c.signal.aborted) return
        const m = stackForCase({ siteId, bbox, rows })
        const text = caseStackNote({ slabs: m.slabs.length })
        if (text) setNote({ text, retry: false })
        else {
          setExploded(false)
          setModel(m)
        }
      })
      .catch(() => {
        if (!c.signal.aborted) setNote({ text: caseStackNote({ failed: true }) ?? '', retry: true })
      })
      .finally(() => !c.signal.aborted && setBusy(false))
  }

  return (
    <>
      <button
        type="button"
        ref={buttonRef}
        className={className}
        onClick={open}
        aria-haspopup="dialog"
        aria-busy={busy}
      >
        <span>
          Layer<span className="st-hide-sm"> stack</span>
          {busy ? '…' : ''}
        </span>
      </button>
      {/* Always mounted, so screen readers hear the text when it changes; only the text and the box come and go. */}
      <div role="status" className={note ? 'st-stack-status st-stack-note' : 'st-stack-status'}>
        {note && (
          <>
            <p>{note.text}</p>
            <div className="st-stack-note-actions">
              {note.retry && (
                <button type="button" className="st-stack-note-btn" onClick={open}>
                  Try again
                </button>
              )}
              <button type="button" className="st-stack-note-btn" onClick={() => setNote(null)}>
                Dismiss
              </button>
            </div>
          </>
        )}
      </div>
      {model &&
        createPortal(
          <EvidenceStack
            model={model}
            exploded={exploded}
            onPick={close}
            onClose={close}
            onCollapsed={collapsed}
            reducedMotion={reducedMotion}
            lede={LEDE}
            closeLabel="Close"
            pickHint="Close the stack."
          />,
          document.body,
        )}
    </>
  )
}

export default CaseLayersButton
