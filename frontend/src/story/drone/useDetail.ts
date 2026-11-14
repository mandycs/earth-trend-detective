import { useEffect, useState } from 'react'
import * as THREE from 'three'
import type { HeightGrid } from '../heights'
import { loadHeights } from '../heights'

/** sites/<id>/detail/detail.json, as written by the pipeline. */
export interface DetailInfo {
  bbox: [number, number, number, number]
  resolution_m?: { heightmap?: number; base?: number }
  height_range_m?: [number, number]
  survey?: string
  lidar_water_surface_m?: number
  water_level_m_by_year?: Record<string, number>
  drawable_years?: number[]
  note?: string
  sources?: Array<{ name: string; url?: string }>
}

export interface DetailAssets {
  info: DetailInfo
  grid: HeightGrid
  base: THREE.Texture
  hillshade: THREE.Texture | null
}

function texture(url: string, srgb: boolean): Promise<THREE.Texture> {
  return new Promise((resolve, reject) => {
    new THREE.TextureLoader().load(
      url,
      (t) => {
        t.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace
        t.anisotropy = 8
        t.generateMipmaps = true
        t.minFilter = THREE.LinearMipmapLinearFilter
        resolve(t)
      },
      undefined,
      () => reject(new Error(`Could not load ${url}`)),
    )
  })
}

/** Probes for a close-up; `available` stays false when the site has none. */
export function useDetailInfo(siteId: string): DetailInfo | null {
  const [info, setInfo] = useState<{ id: string; value: DetailInfo | null }>({ id: '', value: null })
  useEffect(() => {
    let alive = true
    fetch(`/sites/${siteId}/detail/detail.json`)
      .then((r) => (r.ok ? (r.json() as Promise<DetailInfo>) : null))
      .then((value) => alive && setInfo({ id: siteId, value }))
      .catch(() => alive && setInfo({ id: siteId, value: null }))
    return () => {
      alive = false
    }
  }, [siteId])
  return info.id === siteId ? info.value : null
}

export function useDetailAssets(siteId: string, info: DetailInfo | null, enabled: boolean) {
  const [state, setState] = useState<{ key: string; assets: DetailAssets | null; error: string | null }>({
    key: '',
    assets: null,
    error: null,
  })
  const key = enabled && info ? siteId : ''
  useEffect(() => {
    if (!key || !info) return
    let alive = true
    const root = `/sites/${siteId}/detail/`
    Promise.all([
      loadHeights({ rgb: root + 'heightmap_rgb.png', grey: root + 'heightmap_rgb.png' }, info.height_range_m),
      texture(root + 'base.jpg', true),
      texture(root + 'hillshade.png', false).catch(() => null),
    ])
      .then(([grid, base, hillshade]) => alive && setState({ key, assets: { info, grid, base, hillshade }, error: null }))
      .catch((cause: unknown) =>
        alive && setState({ key, assets: null, error: cause instanceof Error ? cause.message : 'Could not load the close-up' }),
      )
    return () => {
      alive = false
    }
  }, [key, info, siteId])
  return state.key === key ? state : { key, assets: null, error: null }
}
