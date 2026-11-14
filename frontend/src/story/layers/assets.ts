import * as THREE from 'three'
import { decodeGreyPng } from '../heights'

const textures = new Map<string, Promise<THREE.Texture>>()

/**
 * Loads a layer picture once. Coarse data layers use nearest filtering, so a
 * 1 km measurement shows as a 1 km block and never as invented detail.
 */
export function layerTexture(url: string, blocks: boolean, srgb = true): Promise<THREE.Texture> {
  const key = `${url}|${blocks ? 'n' : 'l'}`
  let hit = textures.get(key)
  if (!hit) {
    hit = new Promise((resolve, reject) => {
      new THREE.TextureLoader().load(
        url,
        (t) => {
          t.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace
          t.wrapS = THREE.ClampToEdgeWrapping
          t.wrapT = THREE.ClampToEdgeWrapping
          if (blocks) {
            t.magFilter = THREE.NearestFilter
            t.minFilter = THREE.NearestFilter
            t.generateMipmaps = false
          } else {
            t.anisotropy = 8
          }
          t.needsUpdate = true
          resolve(t)
        },
        undefined,
        () => reject(new Error(`Could not load ${url}`)),
      )
    })
    textures.set(key, hit)
  }
  return hit
}

const grids = new Map<string, Promise<{ width: number; height: number; samples: Float32Array } | null>>()

/** 16-bit value grid; pixel 0 means no data. */
export function valueGrid(url: string) {
  let hit = grids.get(url)
  if (!hit) {
    hit = fetch(url)
      .then((r) => (r.ok ? r.arrayBuffer() : null))
      .then((buffer) => (buffer ? decodeGreyPng(buffer) : null))
      .catch(() => null)
    grids.set(url, hit)
  }
  return hit
}

/** Value at u, v (v = 0 at the south edge, as texture coordinates). */
export async function valueAt(url: string, u: number, v: number, scale: number, offset: number): Promise<number | null> {
  const grid = await valueGrid(url)
  if (!grid) return null
  const x = Math.min(grid.width - 1, Math.max(0, Math.floor(u * grid.width)))
  const y = Math.min(grid.height - 1, Math.max(0, Math.floor((1 - v) * grid.height)))
  const raw = grid.samples[y * grid.width + x]
  if (!raw) return null
  return offset + scale * raw
}
