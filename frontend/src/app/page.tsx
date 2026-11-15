import fs from 'node:fs'
import path from 'node:path'
import Link from 'next/link'
import { Wordmark } from '../brand/Wordmark'
import { readCases } from '../lib/readSites'
import { shortName } from '../lib/cases'
import { chaptersFor } from '../lib/chapters'
import { CoverReel } from './landing/CoverReel'
import type { ReelCase } from './landing/CoverReel'
import styles from './landing/cover.module.css'

export const dynamic = 'force-static'

/** The sharper picture for a full-screen cover: base_hq when it is wider than base. */
function coverPicture(site: { id: string; assets: { base: string; base_hq?: string } }): string {
  const hq = site.assets.base_hq
  if (!hq) return site.assets.base
  try {
    const meta = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'public', 'sites', site.id, hq.replace(/\.jpg$/, '.json')), 'utf8'))
    const width = meta?.size_px?.[0] ?? meta?.width ?? 0
    return width >= 2400 ? hq : site.assets.base
  } catch {
    return site.assets.base
  }
}

export default function HomePage() {
  const cases = readCases()
  const reel: ReelCase[] = cases.map((site) => {
    const [one, , three] = chaptersFor(site)
    return {
      id: site.id,
      name: shortName(site.name),
      where: site.country ?? '',
      image: `/sites/${site.id}/${coverPicture(site)}`,
      headline: one.headline,
      line: three.headline.endsWith('climate') ? `${one.line} ${three.headline}. ${three.line}` : one.line,
    }
  })
  const span = cases[0] ? `${cases[0].years[0]}–${cases[0].years[1]}` : ''
  const sources = Array.from(new Map(cases.flatMap((s) => s.sources ?? []).map((src) => [src.url, src])).values())

  return (
    <div className={styles.page}>
      <main>
        <CoverReel cases={reel} years={span} />

        <section className={styles.own} aria-labelledby="own-title">
          <img src="/img/blue-marble.jpg" alt="" className={styles.ownImage} loading="lazy" />
          <div className={styles.ownShade} aria-hidden="true" />
          <div className={styles.ownText}>
            <h2 id="own-title" className={`${styles.ownTitle} narrow`}>
              Now ask about your own place
            </h2>
            <p>
              Pick any point on Earth and ask a question. The detective runs its NASA checks one by one and answers
              with what the data can and cannot say.
            </p>
            <div className={styles.ownActions}>
              <Link href="/investigate" className="btn btn-primary">
                Ask the detective
              </Link>
              <Link href="/explore" className={styles.quiet}>
                Or browse the map
              </Link>
            </div>
          </div>
        </section>
      </main>

      <footer className={styles.footer}>
        <p className={`${styles.footerName} wide`}>
          <Wordmark full />
        </p>
        <div className={styles.footerCols}>
          <div>
            <h2>Data</h2>
            <ul>
              {sources.map((src) => (
                <li key={src.url}>
                  <a href={src.url} target="_blank" rel="noreferrer noopener">
                    {src.title}
                  </a>
                </li>
              ))}
              <li>
                <a href="https://nasa-gibs.github.io/gibs-api-docs/" target="_blank" rel="noreferrer noopener">
                  Blue Marble imagery, NASA Earth Observatory via GIBS
                </a>
              </li>
            </ul>
          </div>
          <div>
            <h2>Read it right</h2>
            <p>
              The share the climate does not explain is a clue, not an attribution. Factors we did not measure end up
              in it too.
            </p>
            <p className={styles.footerNote}>Built for NASA Space Apps 2026, Málaga.</p>
          </div>
        </div>
      </footer>
    </div>
  )
}
