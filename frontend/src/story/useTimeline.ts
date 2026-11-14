import { useEffect, useState } from 'react'
import type { LayerDef } from './layers/model'
import { parseLayers } from './layers/model'

/** The `timeline` block of sites/<id>/layers.json. */
export interface CaseTimeline {
  years: number[]
  layers: Record<string, { mode: 'yearly' | 'span' | 'pair' | 'static'; years?: number[]; new_photo_years?: number[]; water_years?: number[] }>
  /** Years with a yearly value, per record. */
  records: Record<string, number[]>
  /** Map layer id for a record, or null when it has no map. */
  record_map: Record<string, string | null>
}

export interface CaseLayers {
  timeline: CaseTimeline | null
  layers: LayerDef[]
}

const EMPTY: CaseLayers = { timeline: null, layers: [] }

/** sites/<id>/layers.json: the stackable layers and the shared timeline. */
export function useCaseLayers(siteId: string): CaseLayers {
  const [state, setState] = useState<{ id: string; value: CaseLayers }>({ id: '', value: EMPTY })
  useEffect(() => {
    let alive = true
    fetch(`/sites/${siteId}/layers.json`)
      .then((r) => (r.ok ? r.json() : null))
      .then((file) => alive && setState({ id: siteId, value: { timeline: file?.timeline ?? null, layers: parseLayers(file) } }))
      .catch(() => alive && setState({ id: siteId, value: EMPTY }))
    return () => {
      alive = false
    }
  }, [siteId])
  return state.id === siteId ? state.value : EMPTY
}
