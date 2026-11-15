'use client'

import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'

/** Elements that already give the space bar a meaning of their own. */
const OWNS_SPACE = 'input, textarea, select, button, a[href], summary, [contenteditable], [role="button"], [role="checkbox"], [role="switch"], [role="slider"], [role="tab"]'

/**
 * The space bar plays and pauses `toggle` while at least half of `area` is on screen,
 * the way a video player behaves. Elsewhere on the page the space bar scrolls as usual,
 * and it never steals the key from a focused control or text field.
 */
export function useSpaceToggle(area: RefObject<HTMLElement | null>, toggle: () => void) {
  const latest = useRef(toggle)
  latest.current = toggle

  useEffect(() => {
    const el = area.current
    if (!el) return
    let visible = false
    const io = new IntersectionObserver(([entry]) => (visible = entry.intersectionRatio >= 0.5), {
      threshold: [0, 0.5, 1],
    })
    io.observe(el)

    const onKey = (e: KeyboardEvent) => {
      if (e.key !== ' ' || e.repeat || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return
      if (!visible || e.defaultPrevented) return
      const target = e.target as Element | null
      if (target?.closest?.(OWNS_SPACE)) return
      e.preventDefault()
      latest.current()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      io.disconnect()
      window.removeEventListener('keydown', onKey)
    }
  }, [area])
}
