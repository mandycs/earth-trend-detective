/**
 * The layer list of a case, read from sites/<id>/layers.json. Only layers that
 * can be draped on the relief are kept: pictures (the base), shading, trend
 * maps and yearly maps. The relief itself and the then-and-now pair live
 * elsewhere in the UI.
 */
export type LayerStatus = 'analysed' | 'observed' | 'visual_only'

export interface LayerLegend {
  unit?: string
  range?: [number, number]
  stops?: string[]
  more?: string
  less?: string
  notes: string[]
}

export interface LayerDef {
  id: string
  title: string
  /** picture = a base photo; overlay = drawn on top of it. */
  role: 'picture' | 'overlay'
  kind: string
  status: LayerStatus
  source?: { name?: string; url?: string }
  legend: LayerLegend | null
  /** null: one image for all years. */
  years: number[] | null
  /** 'span' layers show change over the whole period (a trend). */
  span: [number, number] | null
  file?: string
  filePattern?: string
  valuePattern?: string
  valueScale?: number
  valueOffset?: number
  /** Ground size of one pixel, metres; drawn as blocks when coarse. */
  pixelM?: number
  blend: 'normal' | 'multiply'
  /** Record id this layer maps, if any. */
  variable?: string
  method?: string | null
}

interface RawLayer {
  id: string
  kind: string
  title?: string
  status?: string
  file?: string
  file_pattern?: string
  value_pattern?: string
  value_scale?: number
  value_offset?: number
  pixel_m?: number
  years?: number[]
  var?: string
  legend?: {
    unit?: string
    range?: [number, number]
    stops?: string[]
    labels?: Record<string, string>
  }
  method?: string | null
  source?: { name?: string; url?: string }
}

function legendOf(raw: RawLayer): LayerLegend | null {
  if (!raw.legend) return null
  const labels = raw.legend.labels ?? {}
  const notes = Object.entries(labels)
    .filter(([k]) => k !== 'more' && k !== 'less')
    .map(([, v]) => v)
  return {
    unit: raw.legend.unit,
    range: raw.legend.range,
    stops: raw.legend.stops,
    more: labels.more,
    less: labels.less,
    notes,
  }
}

function statusOf(value: string | undefined): LayerStatus {
  return value === 'analysed' || value === 'observed' ? value : 'visual_only'
}

/** Layers that can be stacked, in the file's order. */
export function parseLayers(file: { layers?: RawLayer[] } | null): LayerDef[] {
  const out: LayerDef[] = []
  for (const raw of file?.layers ?? []) {
    const common = {
      id: raw.id,
      title: raw.title ?? raw.id,
      kind: raw.kind,
      status: statusOf(raw.status),
      source: raw.source,
      legend: legendOf(raw),
      method: raw.method ?? null,
      variable: raw.var,
    }
    if (raw.kind === 'image' && raw.file) {
      out.push({ ...common, role: 'picture', years: null, span: null, file: raw.file, blend: 'normal' })
    } else if (raw.kind === 'detail') {
      out.push({ ...common, role: 'picture', years: null, span: null, blend: 'normal' })
    } else if (raw.kind === 'shading' && raw.file) {
      out.push({ ...common, role: 'overlay', years: null, span: null, file: raw.file, blend: 'multiply' })
    } else if (raw.kind === 'trend' && raw.file) {
      const span = raw.years && raw.years.length === 2 ? ([raw.years[0], raw.years[1]] as [number, number]) : null
      out.push({ ...common, role: 'overlay', years: null, span, file: raw.file, pixelM: raw.pixel_m ?? 1000, blend: 'normal' })
    } else if (raw.kind === 'yearly' && raw.file_pattern) {
      out.push({
        ...common,
        role: 'overlay',
        years: raw.years ?? null,
        span: null,
        filePattern: raw.file_pattern,
        valuePattern: raw.value_pattern,
        valueScale: raw.value_scale,
        valueOffset: raw.value_offset,
        pixelM: raw.pixel_m ?? 1000,
        blend: 'normal',
      })
    }
  }
  return out
}

/** File for a year, or null when the layer has nothing for it. */
export function fileFor(layer: LayerDef, year: number): string | null {
  if (layer.filePattern) {
    if (layer.years && !layer.years.includes(year)) return null
    return layer.filePattern.replace('{YYYY}', String(year))
  }
  return layer.file ?? null
}

/** What the layer shows for the cursor year, in words. */
export function yearStatus(layer: LayerDef, year: number): string {
  if (layer.span) return `change over ${layer.span[0]}–${layer.span[1]}`
  if (layer.years) return layer.years.includes(year) ? String(year) : `no data for ${year}`
  return 'one date, not per year'
}

export const STATUS_WORDS: Record<LayerStatus, string> = {
  analysed: 'Trend-tested',
  observed: 'Measured values',
  visual_only: 'A picture',
}

/** One entry of the visible stack, top first. */
export interface StackEntry {
  id: string
  on: boolean
  opacity: number
}

/** Default stack: every overlay listed, all off, hillshade on lightly. */
export function defaultStack(layers: LayerDef[]): StackEntry[] {
  return layers
    .filter((l) => l.role === 'overlay')
    .map((l) => ({ id: l.id, on: false, opacity: l.blend === 'multiply' ? 0.6 : 0.85 }))
}
