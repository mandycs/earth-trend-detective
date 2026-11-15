/**
 * Copies `backend/data/recordings/*.json` into `public/recordings` (Next only serves
 * `public/`) and writes `index.json`, the list of replay chips. Replay must work with
 * the backend down, so the front serves these files itself.
 * A missing folder is not an error, same as sync-sites.mjs.
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const NAME = /^[a-z0-9][a-z0-9_-]{0,63}$/ // keep in step with RECORDING_NAME in replay.ts
const here = path.dirname(fileURLToPath(import.meta.url))
const source = path.resolve(here, '../../backend/data/recordings')
const target = path.resolve(here, '../public/recordings')

if (!fs.existsSync(source)) {
  console.warn(`[sync-recordings] no recordings folder at ${source} — skipping`)
  process.exit(0)
}

fs.rmSync(target, { recursive: true, force: true })
fs.mkdirSync(target, { recursive: true })

const chips = []
for (const file of fs.readdirSync(source).filter((f) => f.endsWith('.json')).sort()) {
  const name = file.slice(0, -'.json'.length)
  if (!NAME.test(name)) {
    console.warn(`[sync-recordings] skipping ${file}: name not allowed`)
    continue
  }
  let rec
  try {
    rec = JSON.parse(fs.readFileSync(path.join(source, file), 'utf8'))
  } catch {
    console.warn(`[sync-recordings] skipping ${file}: not valid JSON`)
    continue
  }
  if (!rec || typeof rec.question !== 'string' || !Array.isArray(rec.events)) {
    console.warn(`[sync-recordings] skipping ${file}: no question/events`)
    continue
  }
  fs.copyFileSync(path.join(source, file), path.join(target, file))
  chips.push({ name, question: rec.question, started_at: typeof rec.started_at === 'string' ? rec.started_at : '' })
}

chips.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0))
fs.writeFileSync(path.join(target, 'index.json'), JSON.stringify(chips, null, 2))
console.log(`[sync-recordings] ${chips.length} recordings -> public/recordings`)
