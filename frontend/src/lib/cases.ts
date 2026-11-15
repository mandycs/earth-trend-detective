import type { Site, SiteVariable, Verdict, Direction } from '../story/types'

/** The solved cases shown in story mode. `_example` (synthetic art) is never listed. */
export const CASE_IDS = ['lake_mead', 'aletsch', 'donana', 'great_barrier_reef'] as const
export type CaseId = (typeof CASE_IDS)[number]

export function isCaseId(value: string): value is CaseId {
  return (CASE_IDS as readonly string[]).includes(value)
}

/** "Lake Mead (USA)" -> "Lake Mead". The pipeline name stays the source of truth. */
export function shortName(name: string): string {
  return name.replace(/\s*\(.*\)\s*$/, '').trim() || name
}

/** True for an event record (e.g. heat stress): counts, never a trend verdict. */
export function isEvents(v: Pick<SiteVariable, 'kind'>): boolean {
  return v.kind === 'events'
}

/**
 * The variable a case is about: the one the climate split was computed for,
 * else total water stored, else the first real trend. Event records never lead.
 */
export function leadVariable(site: Pick<Site, 'variables'>): SiteVariable | null {
  const vars = (site.variables ?? []).filter((v) => !isEvents(v))
  return (
    vars.find((v) => v.residual_pct_non_climate != null) ??
    vars.find((v) => v.id === 'grace_tws') ??
    vars.find((v) => v.verdict === 'real') ??
    vars[0] ??
    null
  )
}

const MINUS = '−'

/** Two significant figures, a real minus sign, optional leading plus. */
export function fmt(value: number, signed = false): string {
  if (value === 0) return '0'
  const abs = Math.abs(value)
  const text = new Intl.NumberFormat('en-US', {
    maximumSignificantDigits: abs >= 100 ? 3 : 2,
    maximumFractionDigits: abs >= 1 ? 1 : 3,
  }).format(abs)
  if (value < 0) return `${MINUS}${text}`
  return signed ? `+${text}` : text
}

export function pct(value: number): string {
  return `${Math.round(value)}%`
}

/** The leftover share as words: "54–84%" when the climate models disagree, else "62%". */
export function residualText(v: Pick<SiteVariable, 'residual_pct_non_climate' | 'residual_pct_range'>): string | null {
  const range = v.residual_pct_range
  if (range && range.length === 2) {
    const lo = Math.round(Math.min(range[0], range[1]))
    const hi = Math.round(Math.max(range[0], range[1]))
    return lo === hi ? `${lo}%` : `${lo}–${hi}%`
  }
  return v.residual_pct_non_climate == null ? null : pct(v.residual_pct_non_climate)
}

/** [low, high] in whole percent; equal when there is a single value. */
export function residualBounds(v: Pick<SiteVariable, 'residual_pct_non_climate' | 'residual_pct_range'>): [number, number] | null {
  const range = v.residual_pct_range
  if (range && range.length === 2) {
    return [Math.round(Math.min(range[0], range[1])), Math.round(Math.max(range[0], range[1]))]
  }
  if (v.residual_pct_non_climate == null) return null
  const one = Math.round(v.residual_pct_non_climate)
  return [one, one]
}

export function slopeText(v: SiteVariable): string | null {
  if (v.sen_slope_per_decade == null) return null
  return `${fmt(v.sen_slope_per_decade, true)} ${v.unit}`
}

export interface StampInfo {
  icon: string
  text: string
  meaning: string
}

export function stampFor(verdict: Verdict, direction: Direction): StampInfo {
  if (verdict === 'unknown' || direction === 'flat') {
    return { icon: '?', text: "Can't tell yet", meaning: 'Too noisy or too short to tell a real change from chance.' }
  }
  const icon = direction === 'up' ? '↑' : '↓'
  if (verdict === 'real') {
    return { icon, text: 'Real', meaning: `Going ${direction}, and very unlikely to be chance.` }
  }
  return { icon, text: 'Likely', meaning: `Probably going ${direction}. A strong hint, not yet proof.` }
}
