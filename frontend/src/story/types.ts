export type Verdict = 'real' | 'likely' | 'unknown'
export type Direction = 'up' | 'down' | 'flat'

export interface SeriesPoint {
  year: number
  value: number
}

export interface SiteVariable {
  id: string
  label: string
  unit: string
  /** Sen's slope, units per decade. null when the series is too short. */
  sen_slope_per_decade: number | null
  p_value: number | null
  verdict: Verdict
  direction: Direction
  /** Extra years of data needed before a verdict is possible. */
  years_needed: number | null
  /** Share of the trend the climate drivers do not explain, 0-100. */
  residual_pct_non_climate: number | null
  /** [min, max] share across the climate models tried, or null when only one applies. */
  residual_pct_range?: [number, number] | null
  ci_low?: number | null
  ci_high?: number | null
  q_value?: number | null
  /** The area the record describes, from the pipeline. */
  footprint?: { km: number | null; label: string } | null
  /** Ready-made label from the pipeline, e.g. "↓ Real". */
  badge?: string
  /** Yearly means, used for the sparkline. */
  series?: SeriesPoint[]
  note?: string
}

export interface SiteStep {
  title: string
  body: string
}

export interface SiteSource {
  title: string
  url: string
}

export interface SiteAssets {
  heightmap: string
  base: string
  /** [min, max] metres, as written by the pipeline. */
  heightmap_range_m?: [number, number]
  /** Mapbox terrain-RGB encoding: height = -10000 + (R*65536 + G*256 + B) * 0.1 m. */
  heightmap_rgb?: string
  /** Greyscale multidirectional hillshade, same extent as `base`. */
  hillshade?: string
  /** Higher-resolution cloud-free picture; used when it is sharper than `base`. */
  base_hq?: string
  trend?: Record<string, string>
  yearly?: Record<string, string>
}

export interface Site {
  id: string
  name: string
  country?: string
  /** [west, south, east, north] */
  bbox: [number, number, number, number]
  vertical_exaggeration: number
  elevation_m?: [number, number]
  years: [number, number]
  assets: SiteAssets
  variables: SiteVariable[]
  /** Objects preferred; plain strings (pipeline output) are used as titles. */
  steps: Array<string | SiteStep>
  /** The pipeline writes a one-line headline when the prose is not generated yet. */
  narrative: string | null
  headline?: string | null
  sources?: SiteSource[]
  caveats?: string[]
  /** Variables the pipeline could not fetch, with a reason. */
  missing?: Record<string, string>
  validation?: SiteValidation | null
}

export interface SiteValidation {
  source: string
  url?: string
  metric?: string
  r?: number
  n_months?: number
  elevation_trend_m_per_decade?: number
}

/** Metres of horizontal extent covered by the bbox (approximate, flat Earth). */
export function bboxWidthMeters(bbox: [number, number, number, number]): number {
  const [west, south, east, north] = bbox
  const midLat = ((south + north) / 2) * (Math.PI / 180)
  const width = Math.abs(east - west) * 111_320 * Math.cos(midLat)
  const height = Math.abs(north - south) * 110_540
  return Math.max(width, height, 1)
}

/**
 * Vertical relief expressed as a fraction of the plane width, so the shader can
 * displace a 1x1 plane without knowing the real-world scale.
 */
export function reliefUnits(site: Site): number {
  const range = site.elevation_m ?? site.assets.heightmap_range_m ?? [0, 1000]
  const [minElev, maxElev] = range
  const span = Math.max(maxElev - minElev, 50)
  return (span / bboxWidthMeters(site.bbox)) * (site.vertical_exaggeration || 3)
}
