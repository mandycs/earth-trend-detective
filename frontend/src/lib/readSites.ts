import fs from 'node:fs'
import path from 'node:path'
import type { Site } from '../story/types'
import { CASE_IDS } from './cases'

/**
 * Reads the pipeline's `site.json` files at build time. `scripts/sync-sites.mjs`
 * copies them into `public/sites` before every build, so this is the same file
 * the browser loads. A case without output is skipped, never invented.
 */
export function readCases(): Site[] {
  const root = path.join(process.cwd(), 'public', 'sites')
  const sites: Site[] = []
  for (const id of CASE_IDS) {
    try {
      const raw = fs.readFileSync(path.join(root, id, 'site.json'), 'utf8')
      sites.push(JSON.parse(raw) as Site)
    } catch {
      /* not generated yet */
    }
  }
  return sites
}

export interface LayerLegend {
  label: string
  kind: 'trend' | 'anomaly'
  unit: string
  vmin: number
  vmax: number
  stops: string[]
  legend: { more?: string; less?: string; faded?: string; transparent?: string }
  source?: string
}

export function readLegend(siteId: string, file: string): LayerLegend | null {
  try {
    const raw = fs.readFileSync(path.join(process.cwd(), 'public', 'sites', siteId, file), 'utf8')
    return JSON.parse(raw) as LayerLegend
  } catch {
    return null
  }
}
