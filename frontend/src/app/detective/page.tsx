import fs from 'node:fs'
import path from 'node:path'
import type { Metadata } from 'next'
import DetectiveView from '../../features/detective/DetectiveView'
import type { CaseChip } from '../../features/detective/DetectiveView'
import type { RecordingChip } from '../../features/detective/replay'
import { shortName } from '../../lib/cases'
import { readCases } from '../../lib/readSites'

export const metadata: Metadata = {
  title: 'Your case · Alibi',
  description: 'Pick any place on Earth, ask in plain words, and watch the detective test it with NASA data, scene by scene.',
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

export default async function DetectivePage({ searchParams }: { searchParams: Promise<{ replay?: string; site?: string }> }) {
  const params = await searchParams
  const replay = typeof params.replay === 'string' ? params.replay : undefined
  const site = typeof params.site === 'string' ? params.site : undefined
  const cases: CaseChip[] = readCases().map((s) => ({ id: s.id, name: shortName(s.name), bbox: s.bbox }))
  return <DetectiveView cases={cases} recordings={readRecordings()} initialSite={site} replay={replay} />
}
