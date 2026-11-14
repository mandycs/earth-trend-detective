export interface BeforeAfterPair {
  before: { src: string; year: number }
  after: { src: string; year: number }
  note?: string
  source?: string
}

export interface LayersFile {
  layers?: Array<{
    kind?: string
    note?: string
    source?: { name?: string }
    before?: { file?: string; year?: number }
    after?: { file?: string; year?: number }
  }>
}

/** Pulls the then-and-now pair out of a site's layers.json, or null when there is none. */
export function pairFromLayers(siteId: string, file: LayersFile | null): BeforeAfterPair | null {
  const layer = file?.layers?.find((l) => l.kind === 'before_after')
  if (!layer?.before?.file || !layer.after?.file || layer.before.year == null || layer.after.year == null) return null
  return {
    before: { src: `/sites/${siteId}/${layer.before.file}`, year: layer.before.year },
    after: { src: `/sites/${siteId}/${layer.after.file}`, year: layer.after.year },
    note: layer.note,
    source: layer.source?.name,
  }
}
