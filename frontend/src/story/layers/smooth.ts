import * as THREE from 'three'
import { valueGrid } from './assets'
import type { LayerDef } from './model'

/**
 * Data layers arrive as their native grid stretched with hard blocks (e.g.
 * MODIS 1 km cells drawn 9-10 px wide in a 1024 px image). This rebuilds the
 * native grid, colours it with the layer's own continuous ramp, and lets the
 * GPU interpolate between cell centres: the same values, read as a field.
 */

/** Typical block width along rows: a fractional period such as 9.5 px, or 1 when already native. */
function blockPeriod(samples: ArrayLike<number>, width: number, height: number): number {
  const counts = new Map<number, number>()
  const rowStep = Math.max(1, Math.floor(height / 40))
  for (let y = 0; y < height; y += rowStep) {
    let run = 1
    for (let x = 1; x < width; x += 1) {
      if (samples[y * width + x] === samples[y * width + x - 1]) run += 1
      else {
        counts.set(run, (counts.get(run) ?? 0) + 1)
        run = 1
      }
    }
  }
  let mode = 1
  let best = 0
  for (const [run, n] of counts) {
    if (n > best) {
      best = n
      mode = run
    }
  }
  if (mode < 3) return 1
  // Blocks alternate between two widths when the period is fractional (9 and 10 -> 9.5).
  const a = counts.get(mode) ?? 0
  const b = counts.get(mode + 1) ?? 0
  const c = counts.get(mode - 1) ?? 0
  const [other, otherCount] = b >= c ? [mode + 1, b] : [mode - 1, c]
  return (mode * a + other * otherCount) / Math.max(a + otherCount, 1)
}

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '')
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]
}

/** Continuous ramp: linear between the pipeline's stops. */
function ramp(stops: string[], t: number): [number, number, number] {
  const rgb = stops.map(hexToRgb)
  const x = Math.min(Math.max(t, 0), 1) * (rgb.length - 1)
  const i = Math.min(Math.floor(x), rgb.length - 2)
  const f = x - i
  return [0, 1, 2].map((k) => rgb[i][k] + (rgb[i + 1][k] - rgb[i][k]) * f) as [number, number, number]
}

export interface SmoothResult {
  texture: THREE.Texture
  /** Native cells across the width, for the legend. */
  cols: number
}

const cache = new Map<string, Promise<SmoothResult | null>>()

/** Smoothed texture for a value-backed layer at a year, or null when it cannot be built. */
export function smoothTexture(siteId: string, def: LayerDef, year: number): Promise<SmoothResult | null> {
  const stops = def.legend?.stops
  const range = def.legend?.range
  const valueFile = def.valueFile ?? (def.valuePattern ? def.valuePattern.replace('{YYYY}', String(year)) : null)
  if (!stops || stops.length < 2 || !range || !valueFile || def.valueScale == null || def.valueOffset == null) {
    return Promise.resolve(null)
  }
  if (def.years && !def.years.includes(year)) return Promise.resolve(null)
  const offset = def.valueOffset
  const scale = def.valueScale
  const key = `${siteId}/${valueFile}`
  let hit = cache.get(key)
  if (!hit) {
    hit = (async () => {
      const grid = await valueGrid(`/sites/${siteId}/${valueFile}`)
      if (!grid || typeof document === 'undefined') return null
      const sig = def.significanceFile ? await valueGrid(`/sites/${siteId}/${def.significanceFile}`) : null
      const period = blockPeriod(grid.samples, grid.width, grid.height)
      const cols = Math.max(1, Math.round(grid.width / period))
      const rows = Math.max(1, Math.round(grid.height / period))
      const canvas = document.createElement('canvas')
      canvas.width = cols
      canvas.height = rows
      const ctx = canvas.getContext('2d')
      if (!ctx) return null
      const image = ctx.createImageData(cols, rows)
      const px = image.data
      const [lo, hi] = range
      const valid = new Uint8Array(cols * rows)
      for (let j = 0; j < rows; j += 1) {
        for (let i = 0; i < cols; i += 1) {
          // Sample the centre of each native cell.
          const sx = Math.min(grid.width - 1, Math.floor((i + 0.5) * (grid.width / cols)))
          const sy = Math.min(grid.height - 1, Math.floor((j + 0.5) * (grid.height / rows)))
          const raw = grid.samples[sy * grid.width + sx]
          const o = (j * cols + i) * 4
          if (!raw) continue
          const value = offset + scale * raw
          const [r, g, b] = ramp(stops, (value - lo) / (hi - lo || 1))
          let alpha = 230
          if (sig) {
            const flag = sig.samples[Math.min(sig.height - 1, sy) * sig.width + Math.min(sig.width - 1, sx)]
            alpha = flag === 2 ? 230 : flag === 1 ? 70 : 0
          }
          px[o] = r
          px[o + 1] = g
          px[o + 2] = b
          px[o + 3] = alpha
          valid[j * cols + i] = alpha > 0 ? 1 : 0
        }
      }
      // Give empty cells their neighbour's colour (alpha stays 0), so the
      // linear filter does not pull dark halos into the edges of the data.
      for (let pass = 0; pass < 2; pass += 1) {
        const filled = valid.slice()
        for (let j = 0; j < rows; j += 1) {
          for (let i = 0; i < cols; i += 1) {
            if (valid[j * cols + i]) continue
            for (const [di, dj] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
              const ni = i + di
              const nj = j + dj
              if (ni < 0 || nj < 0 || ni >= cols || nj >= rows || !valid[nj * cols + ni]) continue
              const o = (j * cols + i) * 4
              const n = (nj * cols + ni) * 4
              px[o] = px[n]
              px[o + 1] = px[n + 1]
              px[o + 2] = px[n + 2]
              filled[j * cols + i] = 1
              break
            }
          }
        }
        valid.set(filled)
      }
      ctx.putImageData(image, 0, 0)
      const texture = new THREE.CanvasTexture(canvas)
      texture.colorSpace = THREE.SRGBColorSpace
      texture.magFilter = THREE.LinearFilter
      texture.minFilter = THREE.LinearFilter
      texture.generateMipmaps = false
      texture.wrapS = THREE.ClampToEdgeWrapping
      texture.wrapT = THREE.ClampToEdgeWrapping
      texture.premultiplyAlpha = false
      texture.needsUpdate = true
      return { texture, cols }
    })().catch(() => null)
    cache.set(key, hit)
  }
  return hit
}
