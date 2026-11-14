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
  trend: Record<string, string>
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
  /** Objects preferred; plain strings are accepted for early fixtures. */
  steps: Array<string | SiteStep>
  narrative: string
  sources: SiteSource[]
  caveats?: string[]
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
  const [minElev, maxElev] = site.elevation_m ?? [0, 1000]
  const range = Math.max(maxElev - minElev, 50)
  return (range / bboxWidthMeters(site.bbox)) * (site.vertical_exaggeration || 3)
}
