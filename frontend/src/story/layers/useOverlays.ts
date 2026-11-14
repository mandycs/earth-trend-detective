import { useEffect, useState } from 'react'
import type * as THREE from 'three'
import type { Overlay } from '../Terrain'
import { MAX_OVERLAYS } from '../Terrain'
import type { LayerDef, StackEntry } from './model'
import { fileFor } from './model'
import { layerTexture } from './assets'
import { smoothTexture } from './smooth'

interface Wanted {
  def: LayerDef
  opacity: number
  side: -1 | 0 | 1
  url: string
  key: string
}

/**
 * Textures for the visible overlays, bottom first, for the cursor year.
 * Value-backed layers are rebuilt at their native resolution and smoothed;
 * the rest load as pictures. A layer with nothing for that year is left out
 * (the panel says so). With a curtain, the main layer draws left of it and
 * the compared layer right of it.
 */
export function useOverlays(
  siteId: string,
  layers: LayerDef[],
  stack: StackEntry[],
  year: number,
  rect?: [number, number, number, number],
  compareId?: string | null,
): Overlay[] {
  const [loaded, setLoaded] = useState<Record<string, THREE.Texture>>({})

  const wanted: Wanted[] = []
  for (const s of stack) {
    if (!s.on) continue
    const def = layers.find((l) => l.id === s.id)
    const file = def ? fileFor(def, year) : null
    if (!def || !file) continue
    const side: -1 | 0 | 1 = compareId && def.blend !== 'multiply' ? -1 : 0
    wanted.push({ def, opacity: s.opacity, side, url: `/sites/${siteId}/${file}`, key: `${def.id}@${year}` })
  }
  if (compareId) {
    const def = layers.find((l) => l.id === compareId)
    const file = def ? fileFor(def, year) : null
    const entry = stack.find((s) => s.id === compareId)
    if (def && file) wanted.unshift({ def, opacity: entry?.opacity ?? 0.85, side: 1, url: `/sites/${siteId}/${file}`, key: `${def.id}@${year}` })
  }
  const list = wanted.slice(0, MAX_OVERLAYS)
  const signature = list.map((w) => w.key).join('|')

  useEffect(() => {
    let alive = true
    for (const w of list) {
      const store = (t: THREE.Texture) => alive && setLoaded((prev) => (prev[w.key] === t ? prev : { ...prev, [w.key]: t }))
      smoothTexture(siteId, w.def, year)
        .then((smooth) => {
          if (smooth) store(smooth.texture)
          else return layerTexture(w.url, false, w.def.blend !== 'multiply').then(store)
        })
        .catch(() => undefined)
      // Warm the neighbouring years so playback does not stall.
      for (const near of [year + 1, year - 1]) smoothTexture(siteId, w.def, near).catch(() => undefined)
    }
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature, siteId, year])

  // Stack is top first; the shader wants bottom first.
  return list
    .slice()
    .reverse()
    .map((w) => {
      const texture = loaded[w.key]
      const overlay: Overlay | null = texture ? { texture, opacity: w.opacity, blend: w.def.blend, rect, side: w.side } : null
      return overlay
    })
    .filter((o): o is Overlay => o !== null)
}
