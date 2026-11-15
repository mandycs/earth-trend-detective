import fs from 'node:fs'
import path from 'node:path'
import type { Metadata } from 'next'
import DetectiveView from '../../features/detective/DetectiveView'
import type { CaseChip } from '../../features/detective/DetectiveView'
import type { RecordingChip } from '../../features/detective/replay'
import { shortName } from '../../lib/cases'
import { readCases } from '../../lib/readSites'
import { pointFromParams } from '../../features/detective/viewModel'

export const metadata: Metadata = {
  title: 'Your case · Alibi',
  description: 'Pick any place on Earth, ask in plain words, and watch the detective test it with satellite data, scene by scene.',
}

/** The replay chips written by scripts/sync-recordings.mjs. Missing or broken means no recordings. */
function readRecordings(): RecordingChip[] {
  try {
    const raw: unknown = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'public', 'recordings', 'index.json'), 'utf8'))
    if (!Array.isArray(raw)) return []
    return raw.filter(
      (r): r is RecordingChip =>
        !!r && typeof r === 'object' && typeof r.name === 'string' && typeof r.question === 'string' &&
        typeof r.started_at === 'string',
    )
  } catch {
    return []
  }
}

type Params = Promise<{ replay?: string | string[]; site?: string | string[]; lat?: string | string[]; lon?: string | string[] }>

const one = (v: string | string[] | undefined): string | undefined => (typeof v === 'string' ? v : undefined)

export default async function DetectivePage({ searchParams }: { searchParams: Params }) {
  const params = await searchParams
  const replay = one(params.replay)
  const site = one(params.site)
  // `?lat=&lon=` (from a click on /explore): a point already picked. A solved case (`site`) wins over it.
  const point = site ? null : pointFromParams(one(params.lat), one(params.lon))
  const cases: CaseChip[] = readCases().map((s) => ({ id: s.id, name: shortName(s.name), bbox: s.bbox }))
  return (
    <DetectiveView cases={cases} recordings={readRecordings()} initialSite={site} initialPoint={point} replay={replay} />
  )
}
