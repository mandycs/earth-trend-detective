/**
 * Copies the repo's top-level `sites/` folder into `public/sites`, which is the
 * only place Next serves static files from. `sites/` stays the single source of
 * truth for the data pipeline (Mandy writes there, nobody copies by hand here).
 *
 * Missing source is not an error: a fresh clone without the pipeline output still
 * builds, and the UI shows its "this case has no assets yet" state.
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const source = path.resolve(here, '../../sites')
const target = path.resolve(here, '../public/sites')

if (!fs.existsSync(source)) {
  console.warn(`[sync-sites] no sites folder at ${source} — skipping`)
  process.exit(0)
}

fs.rmSync(target, { recursive: true, force: true })
fs.cpSync(source, target, {
  recursive: true,
  filter: (entry) => !/\.(py|md)$/i.test(entry),
})

let files = 0
let bytes = 0
const walk = (dir) => {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) walk(full)
    else {
      files += 1
      bytes += fs.statSync(full).size
    }
  }
}
walk(target)
console.log(`[sync-sites] ${files} files, ${(bytes / 1024 / 1024).toFixed(1)} MB -> public/sites`)
