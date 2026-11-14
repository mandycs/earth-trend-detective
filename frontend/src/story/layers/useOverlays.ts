import { useEffect, useState } from 'react'
import type * as THREE from 'three'
import type { Overlay } from '../Terrain'
import { MAX_OVERLAYS } from '../Terrain'
import type { LayerDef, StackEntry } from './model'
import { fileFor } from './model'
import { layerTexture } from './assets'

/** Coarser than this is drawn as visible blocks. */
const BLOCK_METRES = 200

/**
 * Textures for the visible overlays, bottom first, for the cursor year.
 * A layer with nothing for that year is left out (the panel says so).
 * Each year's picture stays on screen until the next one has loaded.
 */
export function useOverlays(
  siteId: string,
  layers: LayerDef[],
  stack: StackEntry[],
  year: number,
  rect?: [number, number, number, number],
): Overlay[] {
  const [loaded, setLoaded] = useState<Record<string, THREE.Texture>>({})

  const wanted = stack
    .filter((s) => s.on)
    .map((s) => {
      const def = layers.find((l) => l.id === s.id)
      const file = def ? fileFor(def, year) : null
      return def && file ? { def, entry: s, url: `/sites/${siteId}/${file}` } : null
    })
    .filter((x): x is { def: LayerDef; entry: StackEntry; url: string } => x !== null)
    .slice(0, MAX_OVERLAYS)

  const key = wanted.map((w) => w.url).join('|')

  useEffect(() => {
    let alive = true
    for (const w of wanted) {
      const blocks = (w.def.pixelM ?? 0) >= BLOCK_METRES
      layerTexture(w.url, blocks, w.def.blend !== 'multiply')
        .then((t) => alive && setLoaded((prev) => (prev[w.url] === t ? prev : { ...prev, [w.url]: t })))
        .catch(() => undefined)
      // Warm the neighbouring years so playback does not stall.
      for (const near of [year + 1, year - 1]) {
        const f = fileFor(w.def, near)
        if (f) layerTexture(`/sites/${siteId}/${f}`, blocks, w.def.blend !== 'multiply').catch(() => undefined)
      }
    }
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, siteId, year])

  // Stack is top first; the shader wants bottom first.
  return wanted
    .slice()
    .reverse()
    .map((w) => {
      const texture = loaded[w.url]
      const overlay: Overlay | null = texture ? { texture, opacity: w.entry.opacity, blend: w.def.blend, rect } : null
      return overlay
    })
    .filter((o): o is Overlay => o !== null)
}
