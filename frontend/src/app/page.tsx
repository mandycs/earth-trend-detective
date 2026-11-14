import Link from 'next/link'
import { readCases, readLayersFile, readLegend } from '../lib/readSites'
import { BeforeAfter } from '../lib/BeforeAfter'
import { pairFromLayers } from '../lib/beforeAfterPair'
import { leadVariable, pct, shortName, slopeText } from '../lib/cases'
import { Stamp } from '../lib/Stamp'
import { SeriesLine } from '../lib/SeriesLine'
import { HeroScan } from './landing/HeroScan'
import { RangeBar, SplitBar } from '../lib/Evidence'
import type { Site, SiteVariable } from '../story/types'
import styles from './landing/landing.module.css'

export const dynamic = 'force-static'

function yearsOf(site: Site): number {
  return site.years[1] - site.years[0] + 1
}

function HeroPicture({ site }: { site: Site }) {
  const yearlyVar = Object.keys(site.assets.yearly ?? {})[0]
  const pattern = yearlyVar ? site.assets.yearly?.[yearlyVar] : undefined
  const legend = pattern ? readLegend(site.id, pattern.replace(/_\{YYYY\}\.png$/, '.json')) : null
  const base = `/sites/${site.id}/`
  return (
    <HeroScan
      base={base + site.assets.base}
      framePattern={pattern && legend ? base + pattern : undefined}
      years={site.years}
      layerLabel={legend?.label}
      stops={legend?.stops}
      more={legend?.legend.more}
      less={legend?.legend.less}
      alt={`Satellite picture of ${shortName(site.name)}, ${site.country ?? ''}`}
    />
  )
}

function CaseTile({ site }: { site: Site }) {
  const lead = leadVariable(site)
  return (
    <li className={styles.case}>
      <Link href={`/story/${site.id}`} className={styles.caseLink}>
        <span className={styles.casePicture}>
          <img src={`/sites/${site.id}/${site.assets.base}`} alt="" loading="lazy" />
        </span>
        <span className={styles.caseText}>
          <span className={`${styles.caseName} narrow`}>{shortName(site.name)}</span>
          <span className={styles.caseWhere}>
            {site.country} · {site.years[0]}–{site.years[1]}
          </span>
          {lead ? <CaseFinding site={site} lead={lead} /> : null}
          <span className={styles.caseGo}>
            Open the case <span aria-hidden="true">→</span>
          </span>
        </span>
      </Link>
    </li>
  )
}

function CaseFinding({ site, lead }: { site: Site; lead: SiteVariable }) {
  const slope = slopeText(lead)
  return (
    <span className={styles.caseFinding}>
      <span className={styles.caseFindingTop}>
        <Stamp verdict={lead.verdict} direction={lead.direction} />
        <span className={styles.caseVar}>{lead.label}</span>
      </span>
      {slope ? <span className={styles.caseSlope}>{slope} per decade</span> : null}
      {lead.series && lead.series.length > 1 ? (
        <SeriesLine
          series={lead.series}
          years={site.years}
          width={320}
          height={56}
          className={styles.caseLine}
          label={`${lead.label}, yearly, ${site.years[0]} to ${site.years[1]}`}
        />
      ) : null}
      {lead.residual_pct_non_climate != null ? (
        <span className={styles.caseResidual}>
          <strong className="narrow">{pct(lead.residual_pct_non_climate)}</strong> of it the climate does not explain
        </span>
      ) : null}
    </span>
  )
}

export default function HomePage() {
  const cases = readCases()
  const hero = cases.find((s) => s.id === 'lake_mead') ?? cases[0]
  const lead = hero ? leadVariable(hero) : null
  const pair = hero ? pairFromLayers(hero.id, readLayersFile(hero.id) as Parameters<typeof pairFromLayers>[1]) : null
  const sources = Array.from(
    new Map(cases.flatMap((s) => s.sources ?? []).map((src) => [src.url, src])).values(),
  )

  return (
    <div className={styles.page}>
      <header className={styles.bar}>
        <Link href="/" className={`${styles.wordmark} wide`}>
          Earth Trend Detective
        </Link>
        <nav className={styles.nav} aria-label="Main">
          <a href="#cases">Solved cases</a>
          <a href="#method">How it works</a>
          <Link href="/explore" className="btn btn-primary">
            <span>
              Explore<span className={styles.hideSm}> any point</span>
            </span>
          </Link>
        </nav>
      </header>

      <main>
        <section className={styles.hero} aria-labelledby="hero-title">
          <div className={styles.heroText}>
            <h1 id="hero-title" className={`${styles.heroTitle} narrow rise`}>
              Is it the climate?
            </h1>
            <p className={`${styles.heroLede} rise`} style={{ animationDelay: '80ms' }}>
              Pick a place on Earth. We read {hero ? yearsOf(hero) : 'twenty-odd'} years of NASA satellite and climate
              records, test whether the change there is real, and show how much of it the climate leaves unexplained.
            </p>
            <div className={`${styles.heroActions} rise`} style={{ animationDelay: '160ms' }}>
              {hero ? (
                <Link href={`/story/${hero.id}`} className="btn btn-primary">
                  Open the {shortName(hero.name)} case
                </Link>
              ) : null}
              <Link href="/explore" className="btn">
                Investigate any point
              </Link>
            </div>
            {hero && lead ? (
              <div className={`${styles.heroFinding} rise`} style={{ animationDelay: '240ms' }}>
                <Stamp verdict={lead.verdict} direction={lead.direction} big />
                <p>
                  <strong>{lead.label}</strong> at {shortName(hero.name)}
                  {slopeText(lead) ? <>, {slopeText(lead)} per decade</> : null}.
                  {lead.residual_pct_non_climate != null ? (
                    <> About {pct(lead.residual_pct_non_climate)} of that change is not explained by the climate.</>
                  ) : null}
                </p>
              </div>
            ) : null}
          </div>
          {hero ? <HeroPicture site={hero} /> : null}
        </section>

        <section id="cases" className={styles.cases} aria-labelledby="cases-title">
          <h2 id="cases-title" className={`${styles.sectionTitle} narrow`}>
            Three solved cases
          </h2>
          <p className={styles.sectionLede}>
            A desert lake, an Alpine glacier, a coastal wetland. Each one walks the same three questions over a
            3D model of the real terrain.
          </p>
          <ul className={styles.caseList}>
            {cases.map((site) => (
              <CaseTile key={site.id} site={site} />
            ))}
          </ul>
        </section>

        {hero && lead ? (
          <section id="method" className={styles.method} aria-labelledby="method-title">
            <h2 id="method-title" className={`${styles.sectionTitle} narrow`}>
              Three questions, every time
            </h2>
            <ol className={styles.moves}>
              <li className={styles.move}>
                <div className={styles.moveText}>
                  <h3 className="narrow">What is changing?</h3>
                  <p>
                    We sweep every NASA record that applies to the place, year by year, and line them up.
                    At {shortName(hero.name)}, {lead.label.toLowerCase()} looks like this:
                  </p>
                </div>
                <div className={styles.moveVisual}>
                  {pair ? <BeforeAfter pair={pair} alt={`Satellite picture of ${shortName(hero.name)}`} /> : null}
                  {lead.series ? (
                    <SeriesLine
                      series={lead.series}
                      years={hero.years}
                      width={640}
                      height={160}
                      className={styles.moveLine}
                      label={`${lead.label} at ${shortName(hero.name)}, yearly values, ${hero.years[0]} to ${hero.years[1]}`}
                    />
                  ) : null}
                  <span className={styles.moveAxis}>
                    <span>{hero.years[0]}</span>
                    <span>{hero.years[1]}</span>
                  </span>
                </div>
              </li>
              <li className={styles.move}>
                <div className={styles.moveText}>
                  <h3 className="narrow">Is it real, or chance?</h3>
                  <p>
                    Every place has odd years. We only say “real” when the trend is far bigger than that wobble, and
                    we say “can’t tell yet” when it is not.
                  </p>
                </div>
                <div className={styles.moveVisual}>
                  <RangeBar variable={lead} />
                </div>
              </li>
              {lead.residual_pct_non_climate != null ? (
                <li className={styles.move}>
                  <div className={styles.moveText}>
                    <h3 className="narrow">Is it the climate?</h3>
                    <p>
                      Rain, heat and sunlight explain part of the change. The share they leave over is a lead worth
                      following, not proof of a cause.
                    </p>
                  </div>
                  <div className={styles.moveVisual}>
                    <SplitBar value={lead.residual_pct_non_climate} />
                  </div>
                </li>
              ) : null}
            </ol>
          </section>
        ) : null}

        <section className={styles.explore} aria-labelledby="explore-title">
          <img src="/img/blue-marble.jpg" alt="" className={styles.exploreImage} />
          <div className={styles.exploreText}>
            <h2 id="explore-title" className={`${styles.sectionTitle} narrow`}>
              Now pick your own place
            </h2>
            <p>
              Click any point on the globe. You get its climate records, which ones are changing
              for real, and which are still too noisy to call.
            </p>
            <Link href="/explore" className="btn btn-primary">
              Open the explorer
            </Link>
          </div>
        </section>
      </main>

      <footer className={styles.footer}>
        <p className={`${styles.footerName} wide`}>Earth Trend Detective</p>
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
              The share the climate does not explain is a lead, not an attribution. Factors we did not measure end up
              in it too.
            </p>
            <p className={styles.footerNote}>Built for NASA Space Apps 2026, Málaga.</p>
          </div>
        </div>
      </footer>
    </div>
  )
}

