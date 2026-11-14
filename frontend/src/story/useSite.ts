import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import type { Site } from './types'
import type { HeightGrid } from './heights'
import { loadHeights } from './heights'

export function siteAssetBase(siteId: string): string {
  return `/sites/${siteId}/`
}

function loadTexture(url: string, srgb: boolean): Promise<THREE.Texture> {
  return new Promise((resolve, reject) => {
    new THREE.TextureLoader().load(
      url,
      (texture) => {
        texture.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace
        texture.minFilter = THREE.LinearMipmapLinearFilter
        texture.magFilter = THREE.LinearFilter
        texture.wrapS = THREE.ClampToEdgeWrapping
        texture.wrapT = THREE.ClampToEdgeWrapping
        texture.generateMipmaps = true
        texture.anisotropy = 8
        texture.needsUpdate = true
        resolve(texture)
      },
      undefined,
      () => reject(new Error(`Could not load image: ${url}`)),
    )
  })
}

/**
 * The pipeline and this viewer grew up separately, so the manifest is normalised
 * here: missing arrays become empty arrays and absent layers become empty maps.
 */
function normaliseSite(raw: Site): Site {
  return {
    ...raw,
    steps: Array.isArray(raw.steps) ? raw.steps : [],
    narrative: raw.narrative ?? null,
    sources: Array.isArray(raw.sources) ? raw.sources : [],
    variables: Array.isArray(raw.variables) ? raw.variables : [],
    caveats: Array.isArray(raw.caveats) ? raw.caveats : [],
    assets: {
      ...raw.assets,
      trend: raw.assets?.trend ?? {},
      yearly: raw.assets?.yearly ?? {},
    },
  }
}

/** Optional prose file that lives next to site.json (see sites/<id>/copy.json). */
type CopyOverlay = Partial<Pick<Site, 'steps' | 'narrative' | 'caveats'>>

/**
 * The prose is authored by hand and the pipeline owns site.json, so they are
 * separate files. Pipeline caveats always come first and are never dropped
 * (they explain the method: GRACE footprint, no climate split at snow sites);
 * copy.json caveats are added after them, without duplicates.
 *
 * The hand-written narrative is kept apart as `editorial` and is NOT the
 * case's answer: it has not passed the figure validator. The answer stays the
 * validated narrator text.
 */
function withCopy(data: Site, copy: CopyOverlay | null): Site {
  if (!copy) return data
  const caveats = [...(data.caveats ?? [])]
  for (const c of copy.caveats ?? []) if (!caveats.includes(c)) caveats.push(c)
  return {
    ...data,
    ...(copy.steps ? { steps: copy.steps } : {}),
    editorial: copy.narrative ?? null,
    caveats,
  }
}

/** The sharper of base_hq and base: base_hq is only worth it when it is wider. */
async function pickBase(site: Site, get: (url: string, srgb: boolean) => Promise<THREE.Texture>): Promise<THREE.Texture> {
  const base = siteAssetBase(site.id)
  if (site.assets.base_hq) {
    try {
      const hq = await get(base + site.assets.base_hq, true)
      const width = (hq.image as { width?: number } | undefined)?.width ?? 0
      if (width >= 2400) return hq
    } catch {
      /* fall back to base */
    }
  }
  return get(base + site.assets.base, true)
}

export function useSite(siteId: string) {
  const [state, setState] = useState<{ id: string; site: Site | null; error: string | null }>({
    id: siteId,
    site: null,
    error: null,
  })

  useEffect(() => {
    let alive = true
    const base = siteAssetBase(siteId)
    Promise.all([
      fetch(`${base}site.json`).then((response) => {
        if (!response.ok) throw new Error(`site.json returned ${response.status}`)
        return response.json() as Promise<Site>
      }),
      fetch(`${base}copy.json`)
        .then((response) => (response.ok ? (response.json() as Promise<CopyOverlay>) : null))
        .catch(() => null),
    ])
      .then(([data, copy]) => {
        if (alive) setState({ id: siteId, site: normaliseSite(withCopy(data, copy)), error: null })
      })
      .catch((cause: unknown) => {
        if (alive)
          setState({ id: siteId, site: null, error: cause instanceof Error ? cause.message : 'Could not load the case' })
      })
    return () => {
      alive = false
    }
  }, [siteId])

  const current = state.id === siteId
  return { site: current ? state.site : null, error: current ? state.error : null }
}

/** A per-pixel layer the map can show, with its legend file. */
export interface MapLayer {
  key: string
  variable: string
  kind: 'trend' | 'year'
  file: string
  legendFile: string
}

export function mapLayers(site: Site | null): MapLayer[] {
  if (!site) return []
  const out: MapLayer[] = []
  for (const [variable, file] of Object.entries(site.assets.yearly ?? {})) {
    out.push({ key: `year:${variable}`, variable, kind: 'year', file, legendFile: file.replace(/_\{YYYY\}\.png$/, '.json') })
  }
  for (const [variable, file] of Object.entries(site.assets.trend ?? {})) {
    out.push({ key: `trend:${variable}`, variable, kind: 'trend', file, legendFile: file.replace(/\.png$/, '.json') })
  }
  return out
}

export interface LayerLegend {
  label: string
  kind: 'trend' | 'anomaly'
  unit: string
  vmin: number
  vmax: number
  stops: string[]
  legend: { more?: string; less?: string; faded?: string; transparent?: string }
  share_significant?: number
  share_up?: number
  source?: string
}

export function useLegend(siteId: string | null, file: string | null): LayerLegend | null {
  const [legend, setLegend] = useState<{ key: string; value: LayerLegend | null }>({ key: '', value: null })
  const key = siteId && file ? `${siteId}/${file}` : ''
  useEffect(() => {
    if (!key) return
    let alive = true
    fetch(`/sites/${key}`)
      .then((r) => (r.ok ? (r.json() as Promise<LayerLegend>) : null))
      .then((value) => alive && setLegend({ key, value }))
      .catch(() => alive && setLegend({ key, value: null }))
    return () => {
      alive = false
    }
  }, [key])
  return legend.key === key ? legend.value : null
}

/** How a yearly anomaly frame reads overall: which way most of the area leans. */
export interface FrameRead {
  warmer: number
  cooler: number
}

/**
 * Reads one anomaly frame back from its colours (red side vs blue side of
 * the pipeline's diverging map). Pale and transparent pixels count as neither.
 */
export function readFrame(texture: THREE.Texture): FrameRead | null {
  const image = texture.image as CanvasImageSource | undefined
  if (!image || typeof document === 'undefined') return null
  try {
    const canvas = document.createElement('canvas')
    canvas.width = 64
    canvas.height = 64
    const context = canvas.getContext('2d', { willReadFrequently: true })
    if (!context) return null
    context.drawImage(image, 0, 0, 64, 64)
    const data = context.getImageData(0, 0, 64, 64).data
    let warm = 0
    let cool = 0
    let seen = 0
    for (let i = 0; i < data.length; i += 4) {
      if (data[i + 3] < 100) continue
      seen += 1
      const lean = data[i] - data[i + 2]
      if (lean > 40) warm += 1
      else if (lean < -40) cool += 1
    }
    if (seen === 0) return null
    return { warmer: warm / seen, cooler: cool / seen }
  } catch {
    return null
  }
}

export interface StoryAssets {
  grid: HeightGrid | null
  base: THREE.Texture | null
  hillshade: THREE.Texture | null
  trend: THREE.Texture | null
  /** One texture per year, oldest first. Empty when the layer is not yearly. */
  years: THREE.Texture[]
  /** One reading per yearly frame, same order as `years`. */
  reads: Array<FrameRead | null>
  loading: boolean
  error: string | null
}

const EMPTY: StoryAssets = { grid: null, base: null, hillshade: null, trend: null, years: [], reads: [], loading: true, error: null }

/** Loads the relief and the base picture once per site, then the chosen map layer. */
export function useStoryAssets(site: Site | null, layer: MapLayer | null): StoryAssets {
  const [ground, setGround] = useState<{ id: string; grid: HeightGrid | null; base: THREE.Texture | null; hillshade: THREE.Texture | null; error: string | null }>({
    id: '',
    grid: null,
    base: null,
    hillshade: null,
    error: null,
  })
  const [overlay, setOverlay] = useState<{ key: string; trend: THREE.Texture | null; years: THREE.Texture[]; reads: Array<FrameRead | null> }>({
    key: '',
    trend: null,
    years: [],
    reads: [],
  })
  const cache = useRef(new Map<string, THREE.Texture>())

  const get = (url: string, srgb: boolean) => {
    const hit = cache.current.get(url)
    if (hit) return Promise.resolve(hit)
    return loadTexture(url, srgb).then((texture) => {
      cache.current.set(url, texture)
      return texture
    })
  }

  useEffect(() => {
    if (!site) return
    let alive = true
    const base = siteAssetBase(site.id)
    Promise.all([
      loadHeights(
        { rgb: site.assets.heightmap_rgb ? base + site.assets.heightmap_rgb : undefined, grey: base + site.assets.heightmap },
        site.assets.heightmap_range_m ?? site.elevation_m,
      ),
      pickBase(site, get),
      site.assets.hillshade ? get(base + site.assets.hillshade, false).catch(() => null) : Promise.resolve(null),
    ])
      .then(([grid, map, shade]) => {
        if (alive) setGround({ id: site.id, grid, base: map, hillshade: shade, error: null })
      })
      .catch((cause: unknown) => {
        if (alive)
          setGround({
            id: site.id,
            grid: null,
            base: null,
            hillshade: null,
            error: cause instanceof Error ? cause.message : 'Could not load the terrain',
          })
      })
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [site])

  const yearList = useMemo(() => {
    if (!site) return []
    const [first, last] = site.years
    return Array.from({ length: Math.min(last - first + 1, 60) }, (_, i) => first + i)
  }, [site])

  const overlayKey = site && layer ? `${site.id}/${layer.key}` : ''

  useEffect(() => {
    if (!site || !layer) return
    let alive = true
    const base = siteAssetBase(site.id)
    if (layer.kind === 'trend') {
      get(base + layer.file, true)
        .then((t) => alive && setOverlay({ key: overlayKey, trend: t, years: [], reads: [] }))
        .catch(() => alive && setOverlay({ key: overlayKey, trend: null, years: [], reads: [] }))
    } else {
      Promise.all(yearList.map((y) => get(base + layer.file.replace('{YYYY}', String(y)), true).catch(() => null))).then(
        (list) => {
          if (alive)
          {
            const years = list.filter((t): t is THREE.Texture => Boolean(t))
            setOverlay({ key: overlayKey, trend: null, years, reads: years.map(readFrame) })
          }
        },
      )
    }
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overlayKey, yearList])

  if (!site) return EMPTY
  const groundReady = ground.id === site.id
  const overlayReady = !layer || overlay.key === overlayKey
  return {
    grid: groundReady ? ground.grid : null,
    base: groundReady ? ground.base : null,
    hillshade: groundReady ? ground.hillshade : null,
    trend: overlayReady && layer ? overlay.trend : null,
    years: overlayReady && layer ? overlay.years : [],
    reads: overlayReady && layer ? overlay.reads : [],
    loading: !groundReady || !overlayReady,
    error: groundReady ? ground.error : null,
  }
}
