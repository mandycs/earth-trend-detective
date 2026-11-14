import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import type { Site } from './types'

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
        texture.anisotropy = 4
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
 * here: missing arrays become empty arrays, absent layers become empty maps, and
 * the headline stands in when the prose has not been generated yet.
 */
function normaliseSite(raw: Site): Site {
  return {
    ...raw,
    steps: Array.isArray(raw.steps) ? raw.steps : [],
    narrative: raw.narrative ?? null,
    sources: Array.isArray(raw.sources) ? raw.sources : [],
    variables: Array.isArray(raw.variables) ? raw.variables : [],
    assets: {
      ...raw.assets,
      trend: raw.assets?.trend ?? {},
      yearly: raw.assets?.yearly ?? {},
    },
  }
}

export function useSite(siteId: string) {
  const [site, setSite] = useState<Site | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    setSite(null)
    setError(null)
    fetch(`${siteAssetBase(siteId)}site.json`)
      .then((response) => {
        if (!response.ok) throw new Error(`site.json returned ${response.status}`)
        return response.json() as Promise<Site>
      })
      .then((data) => {
        if (alive) setSite(normaliseSite(data))
      })
      .catch((cause: unknown) => {
        if (alive) setError(cause instanceof Error ? cause.message : 'Unknown error loading site')
      })
    return () => {
      alive = false
    }
  }, [siteId])

  return { site, error }
}

export interface StoryAssets {
  height: THREE.Texture | null
  base: THREE.Texture | null
  trend: THREE.Texture | null
  /** One texture per year, oldest first. Empty when the site has no yearly layer. */
  years: THREE.Texture[]
  loading: boolean
  error: string | null
}

/** Loads every texture the story mode needs for one site + variable. */
export function useStoryAssets(site: Site | null, variableId: string | null): StoryAssets {
  const [state, setState] = useState<StoryAssets>({
    height: null,
    base: null,
    trend: null,
    years: [],
    loading: true,
    error: null,
  })
  const cache = useRef(new Map<string, THREE.Texture>())

  const trendFile = site && variableId ? site.assets.trend?.[variableId] : undefined
  const yearlyPattern = site && variableId ? site.assets.yearly?.[variableId] : undefined
  const yearList = useMemo(() => {
    if (!site) return []
    const [first, last] = site.years
    const count = Math.min(last - first + 1, 60)
    return Array.from({ length: count }, (_, index) => first + index)
  }, [site])

  useEffect(() => {
    if (!site) return
    let alive = true
    setState((previous) => ({ ...previous, loading: true, error: null }))
    const base = siteAssetBase(site.id)

    const get = (url: string, srgb: boolean) => {
      const hit = cache.current.get(url)
      if (hit) return Promise.resolve(hit)
      return loadTexture(url, srgb).then((texture) => {
        cache.current.set(url, texture)
        return texture
      })
    }

    Promise.all([
      get(base + site.assets.heightmap, false),
      get(base + site.assets.base, true),
    ])
      .then(async ([height, map]) => {
        const trend = trendFile ? await get(base + trendFile, true).catch(() => null) : null
        let years: THREE.Texture[] = []
        if (yearlyPattern) {
          years = await Promise.all(
            yearList.map((year) =>
              get(base + yearlyPattern.replace('{YYYY}', String(year)), true).catch(() => null),
            ),
          ).then((list) => list.filter((texture): texture is THREE.Texture => Boolean(texture)))
        }
        if (!alive) return
        setState({ height, base: map, trend, years, loading: false, error: null })
      })
      .catch((cause: unknown) => {
        if (!alive) return
        setState({
          height: null,
          base: null,
          trend: null,
          years: [],
          loading: false,
          error: cause instanceof Error ? cause.message : 'Could not load the site images',
        })
      })

    return () => {
      alive = false
    }
  }, [site, trendFile, yearlyPattern, variableId, yearList])

  return state
}

export function disposeTextures(textures: Array<THREE.Texture | null | undefined>) {
  textures.forEach((texture) => texture?.dispose())
}
