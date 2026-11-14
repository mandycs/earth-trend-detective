/**
 * The area each record really describes, by data source. These are properties
 * of the NASA products, not of a place:
 * - GRACE/GRACE-FO mascons: about 300 km across (the pipeline's own caveat).
 * - NASA POWER (MERRA-2 / IMERG / CERES): a grid cell of roughly 50 km.
 * - GLDAS Noah 0.25°: a model cell of about 25 km.
 * - MODIS land products: per pixel, about 1 km or finer.
 * - "_upstream" records: the river basin upstream of the place.
 */
export interface Footprint {
  /** Short words for the UI. */
  words: string
  /** Approximate width in km; null when it is a basin, not a square. */
  km: number | null
  perPixel: boolean
}

const MODIS = new Set(['lst_day', 'ndvi', 'et', 'snow_cover', 'water_area'])
const GLDAS = new Set(['soil_moisture', 'runoff'])

export function footprintOf(variableId: string): Footprint {
  if (variableId === 'lake_level') return { words: 'the whole lake (USBR gauge)', km: null, perPixel: false }
  if (variableId === 'grace_tws') return { words: 'a region about 300 km across', km: 300, perPixel: false }
  if (variableId.endsWith('_upstream')) return { words: 'the river basin upstream', km: null, perPixel: false }
  if (MODIS.has(variableId)) return { words: 'every 1 km square of the map', km: 1, perPixel: true }
  if (GLDAS.has(variableId)) return { words: 'a model cell about 25 km across', km: 25, perPixel: false }
  return { words: 'a climate cell about 50 km across', km: 50, perPixel: false }
}

/** How the footprint compares with the map on screen, in words. */
export function footprintVsMap(fp: Footprint, mapKm: number): string {
  if (fp.perPixel) return 'pixel by pixel, so the map can show where it changes'
  if (fp.km == null) return 'one number for the whole basin'
  if (fp.km > mapKm * 1.3) return 'bigger than this whole map: one number for all of it'
  if (fp.km > mapKm * 0.7) return 'about the size of this map: one number for all of it'
  return 'one number for part of this map'
}

/**
 * Tiny scale picture: the solid square is this map, the outline is the area
 * the record covers. Per-pixel records show a grid instead.
 */
export function FootprintGlyph({ fp, mapKm, className }: { fp: Footprint; mapKm: number; className?: string }) {
  const size = 28
  if (fp.perPixel) {
    return (
      <svg width={size} height={size} viewBox="0 0 28 28" aria-hidden="true" className={className}>
        {[0, 1, 2, 3].map((r) =>
          [0, 1, 2, 3].map((c) => <rect key={`${r}-${c}`} x={2 + c * 6.25} y={2 + r * 6.25} width={5} height={5} fill="currentColor" opacity={(r + c) % 3 === 0 ? 1 : 0.55} />),
        )}
      </svg>
    )
  }
  const ratio = fp.km == null ? 2.2 : fp.km / Math.max(mapKm, 1)
  // Map square and footprint square, both centred, the larger one fills the box.
  const big = 26
  const mapSide = ratio >= 1 ? big / Math.min(ratio, 6) : big
  const fpSide = ratio >= 1 ? big : big * Math.max(ratio, 0.12)
  const o = (s: number) => (28 - s) / 2
  return (
    <svg width={size} height={size} viewBox="0 0 28 28" aria-hidden="true" className={className}>
      <rect x={o(mapSide)} y={o(mapSide)} width={mapSide} height={mapSide} fill="currentColor" opacity={0.45} />
      <rect x={o(fpSide)} y={o(fpSide)} width={fpSide} height={fpSide} fill="none" stroke="currentColor" strokeWidth={2} strokeDasharray={fp.km == null ? '3 2' : undefined} />
    </svg>
  )
}
