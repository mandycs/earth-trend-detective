import { useEffect, useState } from 'react'

/** The `timeline` block of sites/<id>/layers.json. */
export interface CaseTimeline {
  years: number[]
  layers: Record<string, { mode: 'yearly' | 'span' | 'pair' | 'static'; years?: number[]; new_photo_years?: number[]; water_years?: number[] }>
  /** Years with a yearly value, per record. */
  records: Record<string, number[]>
  /** Yearly map layer id for a record, or null when it has no map. */
  record_map: Record<string, string | null>
}

export function useTimeline(siteId: string): CaseTimeline | null {
  const [state, setState] = useState<{ id: string; value: CaseTimeline | null }>({ id: '', value: null })
  useEffect(() => {
    let alive = true
    fetch(`/sites/${siteId}/layers.json`)
      .then((r) => (r.ok ? r.json() : null))
      .then((file: { timeline?: CaseTimeline } | null) => alive && setState({ id: siteId, value: file?.timeline ?? null }))
      .catch(() => alive && setState({ id: siteId, value: null }))
    return () => {
      alive = false
    }
  }, [siteId])
  return state.id === siteId ? state.value : null
}
