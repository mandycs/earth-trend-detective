import type { CatalogLayer } from './types.ts'
import { LAYER_CATALOG } from './layerCatalog.generated.ts'

export const GIBS_ATTRIBUTION = 'NASA GIBS'

export const TERRAIN = {
  url: 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png',
  encoding: 'terrarium',
  maxzoom: 15,
  exaggeration: 1.5,
  attribution: 'Relief: AWS Terrain Tiles (Mapzen), not a NASA product',
} as const

const GIBS = 'https://gibs.earthdata.nasa.gov'

export function catalogLayer(id: string): CatalogLayer | null {
  return LAYER_CATALOG.find((l) => l.id === id) ?? null
}

/** Date to request: a given date wins; else a year snapped to the layer period; else dates.end. Clamped to [start, end]. */
export function dateFor(layer: CatalogLayer, when: { date?: string | null; year?: number | null }): string {
  const { start, end, step, years } = layer.dates
  let d: string
  if (when.date) d = when.date
  else if (when.year != null) {
    const jan = step === 'annual' || (years?.length ?? 0) > 0
    d = `${when.year}-${jan ? '01-01' : '07-01'}`
  } else d = end
  if (d > end) return end
  if (d < start) return start
  return d
}

function isVector(layer: CatalogLayer): boolean {
  return layer.format.includes('mapbox-vector-tile')
}

function ext(layer: CatalogLayer): string {
  return layer.format === 'image/jpeg' ? 'jpg' : 'png'
}

export function tileUrl(layer: CatalogLayer, date: string): string {
  if (isVector(layer)) {
    // MVT cannot feed a raster source: fall back to a WMS png (same pattern as InvestigateMap).
    const params = new URLSearchParams({
      SERVICE: 'WMS',
      REQUEST: 'GetMap',
      VERSION: '1.3.0',
      LAYERS: layer.gibs_layer,
      STYLES: '',
      CRS: 'EPSG:3857',
      WIDTH: '256',
      HEIGHT: '256',
      FORMAT: 'image/png',
      TRANSPARENT: 'TRUE',
      TIME: date,
    })
    return `${GIBS}/wms/epsg3857/best/wms.cgi?${params.toString()}&BBOX={bbox-epsg-3857}`
  }
  return `${GIBS}/wmts/epsg3857/best/${layer.gibs_layer}/default/${date}/${layer.tile_matrix_set}/{z}/{y}/{x}.${ext(layer)}`
}

export function maxZoomOf(layer: CatalogLayer): number {
  const m = /Level(\d+)$/.exec(layer.tile_matrix_set)
  return m ? Number(m[1]) : 0
}
