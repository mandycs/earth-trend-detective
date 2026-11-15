export interface CatalogLayer {
  id: string
  title: string
  gibs_layer: string
  kind: 'wmts'
  format: string
  tile_matrix_set: string
  legend: { unit: string; min: number | null; max: number | null; colormap?: string }
  dates: { start: string; end: string; step: string; ongoing: boolean; years?: number[]; gaps?: string[][] }
  zones: string[]
  source: string
  resolution: string
}

export interface CaseLayerRow {
  id: string
  kind: string
  title?: string
  file?: string
  file_pattern?: string
  years?: number[]
  source?: { name?: string } | string
  before?: { file: string; year: number }
  after?: { file: string; year: number }
  pixel_m?: number
  legend?: CaseLegend
}

/** A case legend as written in sites/<id>/layers.json; read defensively. */
export interface CaseLegend {
  unit?: string
  range?: number[]
  labels?: Record<string, string> | string[]
  stops?: string[]
}
