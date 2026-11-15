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

const DAY_MS = 86_400_000

function isoDay(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10)
}

/**
 * Default date for an ongoing layer: a safe lag behind `now` by step, because same-day GIBS tiles are often empty.
 * daily: now - 7 days; 8day: now - 16 days; monthly: first day of the month two months back; annual: Jan 1 of last year.
 */
export function safeDefaultDate(step: string, now: string): string {
  const t = Date.parse(`${now}T00:00:00Z`)
  const y = Number(now.slice(0, 4))
  const m = Number(now.slice(5, 7)) // 1..12
  switch (step) {
    case 'annual':
      return `${y - 1}-01-01`
    case 'monthly': {
      const back = new Date(Date.UTC(y, m - 1 - 2, 1))
      return isoDay(back.getTime())
    }
    case '8day':
      return isoDay(t - 16 * DAY_MS)
    default:
      return isoDay(t - 7 * DAY_MS)
  }
}

/**
 * Date to request: a given date wins; else a year snapped to the layer period; else, for an ongoing layer, a safe
 * lag behind `now` (see safeDefaultDate); else dates.end. Clamped to [start, end]. Pure: `now` (YYYY-MM-DD) is
 * passed in; when it is omitted the layer's own dates.end stands in for it.
 */
export function dateFor(
  layer: CatalogLayer,
  when: { date?: string | null; year?: number | null },
  now?: string | null,
): string {
  const { start, end, step, years, ongoing } = layer.dates
  let d: string
  if (when.date) d = when.date
  else if (when.year != null) {
    const jan = step === 'annual' || (years?.length ?? 0) > 0
    d = `${when.year}-${jan ? '01-01' : '07-01'}`
    // A year alone on an ongoing layer: mid-year of this year may not exist yet; the delayed safe date stands in.
    if (ongoing && now) {
      const safe = safeDefaultDate(step, now)
      if (d > safe) d = safe
    }
  } else if (ongoing) d = safeDefaultDate(step, now ?? end)
  else d = end
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

/** Picture size for one WMS GetMap: `width` across, the height following the bbox's degree ratio (EPSG:4326). */
function wmsSize(bbox: [number, number, number, number], width: number): [number, number] {
  const [w, s, e, n] = bbox
  const ratio = e > w ? (n - s) / (e - w) : 1
  return [width, Math.max(64, Math.min(2048, Math.round(width * ratio)))]
}

/**
 * One GIBS WMS GetMap for an exact bbox (west, south, east, north) and date, as a single picture in EPSG:4326.
 * WMS 1.3.0 with EPSG:4326 takes the bbox as lat,lon: south, west, north, east. Same layer, format and date as the
 * tiles from `tileUrl`; vector layers come back as a png, like their tile fallback.
 */
export function wmsUrl(layer: CatalogLayer, date: string, bbox: [number, number, number, number], width = 1024): string {
  const [w, s, e, n] = bbox
  const [wd, ht] = wmsSize(bbox, width)
  const jpeg = layer.format === 'image/jpeg'
  const params = new URLSearchParams({
    SERVICE: 'WMS',
    REQUEST: 'GetMap',
    VERSION: '1.3.0',
    LAYERS: layer.gibs_layer,
    STYLES: '',
    CRS: 'EPSG:4326',
    BBOX: [s, w, n, e].join(','),
    WIDTH: String(wd),
    HEIGHT: String(ht),
    FORMAT: jpeg ? 'image/jpeg' : 'image/png',
    TIME: date,
  })
  if (!jpeg) params.set('TRANSPARENT', 'TRUE')
  return `${GIBS}/wms/epsg4326/best/wms.cgi?${params.toString()}`
}

/** The cloud-free picture under the globe (explore/mapStyle.ts uses the same GIBS layer as its base tiles). */
export const BLUE_MARBLE = {
  gibs_layer: 'BlueMarble_ShadedRelief_Bathymetry',
  title: 'Blue Marble, cloud-free',
  source: 'Blue Marble imagery, NASA Earth Observatory via GIBS',
} as const

/** One WMS GetMap of the Blue Marble for an exact bbox. A single fixed composite: it takes no date. */
export function blueMarbleUrl(bbox: [number, number, number, number], width = 1024): string {
  const [w, s, e, n] = bbox
  const [wd, ht] = wmsSize(bbox, width)
  const params = new URLSearchParams({
    SERVICE: 'WMS', REQUEST: 'GetMap', VERSION: '1.3.0', LAYERS: BLUE_MARBLE.gibs_layer, STYLES: '', CRS: 'EPSG:4326',
    BBOX: [s, w, n, e].join(','), WIDTH: String(wd), HEIGHT: String(ht), FORMAT: 'image/jpeg',
  })
  return `${GIBS}/wms/epsg4326/best/wms.cgi?${params.toString()}`
}
