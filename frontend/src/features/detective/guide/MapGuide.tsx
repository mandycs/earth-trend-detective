'use client'

import { useEffect, useId, useMemo, useRef, useState } from 'react'
import type { DetEvent } from '../events'
import type { Investigation } from '../scenes'
import type { Target } from '../request'
import type { MapView } from '../map/mapView'
import { swatchBackground } from '../map/landCover'
import { CLUE_LINE, STACK_PLAIN, STACK_TECH, plainGuide, techGuide } from './guideModel'
import type { GuideMark, PlainItem, StampLine } from './guideModel'
import styles from './guide.module.css'

export interface MapGuideProps {
  view: MapView
  target: Target | null
  inv: Investigation | null
  events: readonly DetEvent[]
  /** "stack": opened from the evidence stack; it leads with how to read the stack. */
  variant?: 'map' | 'stack'
}

type Tier = 'plain' | 'tech'

/** "What am I looking at?": a chip that opens a drawer with two tiers, plain words first. Closed by default. */
export function MapGuide({ view, target, inv, events, variant = 'map' }: MapGuideProps) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [open, setOpen] = useState(false)
  const [tier, setTier] = useState<Tier>('plain')
  const titleId = useId()
  const panelId = useId()

  useEffect(() => {
    const d = dialog.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])

  const plain = useMemo(() => (open ? plainGuide(view, target, inv) : null), [open, view, target, inv])
  const tech = useMemo(() => (open && tier === 'tech' ? techGuide(view, inv, events) : null), [open, tier, view, inv, events])
  const stack = variant === 'stack'

  return (
    <>
      <button
        type="button"
        className={stack ? styles.textTrigger : styles.chip}
        aria-haspopup="dialog"
        onClick={() => setOpen(true)}
      >
        <span aria-hidden="true" className={styles.chipMark}>
          ?
        </span>
        {stack ? 'How to read the stack' : 'What am I looking at?'}
      </button>
      <dialog
        ref={dialog}
        className={styles.drawer}
        aria-labelledby={titleId}
        onClose={() => setOpen(false)}
        // Esc closes the guide only, not the evidence stack or a half-drawn box under it.
        onKeyDown={(e) => {
          if (e.key === 'Escape') e.stopPropagation()
        }}
        onClick={(e) => {
          // A click on the backdrop (the dialog box itself, outside the sheet) closes it.
          if (e.target === dialog.current) setOpen(false)
        }}
      >
        {open && plain ? (
          <div className={styles.sheet}>
            <div className={styles.head}>
              <h2 id={titleId} className={styles.title}>
                {stack ? 'How to read the stack' : 'What am I looking at?'}
              </h2>
              <button type="button" className={styles.close} onClick={() => setOpen(false)} aria-label="Close the guide">
                ✕
              </button>
            </div>
            <div className={styles.tabs} role="tablist" aria-label="Level of detail">
              {(['plain', 'tech'] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  role="tab"
                  aria-selected={tier === t}
                  aria-controls={panelId}
                  className={styles.tab}
                  onClick={() => setTier(t)}
                >
                  {t === 'plain' ? 'In plain words' : 'Under the hood'}
                </button>
              ))}
            </div>
            <div id={panelId} role="tabpanel" className={styles.body}>
              {tier === 'plain' ? (
                <>
                  {stack && (
                    <section className={styles.section}>
                      <h3 className={styles.h3}>The stack</h3>
                      {STACK_PLAIN.map((l) => (
                        <p key={l}>{l}</p>
                      ))}
                    </section>
                  )}
                  <p className={styles.framing}>{plain.framing}</p>
                  <section className={styles.section}>
                    <h3 className={styles.h3}>{plain.generic ? 'What you will see' : 'On the map right now'}</h3>
                    <ul className={styles.items}>
                      {plain.items.map((it) => (
                        <Item key={it.key} item={it} />
                      ))}
                    </ul>
                  </section>
                  <section className={styles.section}>
                    <h3 className={styles.h3}>The stamps</h3>
                    <p className={styles.muted}>On each record: is the change real?</p>
                    <Stamps lines={plain.stamps.verdicts} />
                    <p className={styles.muted}>On each suspect: does it explain the change?</p>
                    <Stamps lines={plain.stamps.suspects} />
                  </section>
                  <section className={styles.section}>
                    <h3 className={styles.h3}>How Alibi works</h3>
                    <ol className={styles.steps}>
                      {plain.steps.map((s, i) => (
                        <li key={s.title}>
                          <span className={styles.stepNo} aria-hidden="true">
                            {i + 1}
                          </span>
                          <div>
                            <p className={styles.stepTitle}>{s.title}</p>
                            <p>{s.text}</p>
                          </div>
                        </li>
                      ))}
                    </ol>
                    <p className={styles.muted}>{CLUE_LINE}</p>
                  </section>
                  <button type="button" className={styles.more} onClick={() => setTier('tech')}>
                    Curious? See what is under the hood <span aria-hidden="true">→</span>
                  </button>
                </>
              ) : tech ? (
                <>
                  {stack && (
                    <section className={styles.section}>
                      <h3 className={styles.h3}>The stack</h3>
                      {STACK_TECH.map((l) => (
                        <p key={l}>{l}</p>
                      ))}
                    </section>
                  )}
                  <section className={styles.section}>
                    <h3 className={styles.h3}>Drawn on the map</h3>
                    {tech.layers.length === 0 ? (
                      <p className={styles.muted}>Nothing yet: the globe is the base map with relief.</p>
                    ) : (
                      <dl className={styles.facts}>
                        {tech.layers.map((l) => (
                          <div key={l.key} className={styles.fact}>
                            <dt>{l.role}</dt>
                            <dd>
                              <strong>{l.title}</strong>
                              {l.source && <span>Source: {l.source}</span>}
                              {l.provider && <span>Served by: {l.provider}</span>}
                              {l.resolution && <span>Resolution: {l.resolution}</span>}
                              {l.when && <span>Time: {l.when}</span>}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    )}
                  </section>
                  <section className={styles.section}>
                    <h3 className={styles.h3}>Records tested</h3>
                    {tech.records.length === 0 ? (
                      <p className={styles.muted}>No record fetched yet. Ask a question and they appear here.</p>
                    ) : (
                      <dl className={styles.facts}>
                        {tech.records.map((r) => (
                          <div key={r.varId} className={styles.fact}>
                            <dt>{r.label}</dt>
                            <dd>
                              {r.dataset && (
                                <span>
                                  Dataset: <code>{r.dataset}</code>
                                </span>
                              )}
                              {r.instrument && <span>Satellite or model: {r.instrument}</span>}
                              {r.provider && <span>Served by: {r.provider}</span>}
                              {r.resolution && <span>Resolution: {r.resolution}</span>}
                              {r.period && <span>Period: {r.period}</span>}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    )}
                  </section>
                  <section className={styles.section}>
                    <h3 className={styles.h3}>Methods</h3>
                    <ul className={styles.methods}>
                      {tech.methods.map((m) => (
                        <li key={m.name}>
                          <p className={styles.stepTitle}>
                            {m.name}
                            {m.used && <span className={styles.used}> · used here</span>}
                          </p>
                          <p>{m.gloss}</p>
                        </li>
                      ))}
                    </ul>
                  </section>
                  <section className={styles.section}>
                    <h3 className={styles.h3}>Your question, as tool calls</h3>
                    <p className={styles.muted}>
                      The language model reads your words and calls these tools; the numbers come from the tools, never
                      from the model.
                    </p>
                    {tech.calls.length === 0 ? (
                      <p className={styles.muted}>No calls yet.</p>
                    ) : (
                      <ol className={styles.calls}>
                        {tech.calls.map((c) => (
                          <li key={c.key}>
                            <code>
                              {c.tool}({c.args})
                            </code>
                            {c.state !== 'done' && <span className={styles.muted}> · {c.state}</span>}
                          </li>
                        ))}
                      </ol>
                    )}
                  </section>
                </>
              ) : null}
            </div>
          </div>
        ) : null}
      </dialog>
    </>
  )
}

function Mark({ mark }: { mark: GuideMark }) {
  return <span aria-hidden="true" className={`${styles.mark} ${styles[`mark_${mark}`]}`} />
}

function Item({ item }: { item: PlainItem }) {
  return (
    <li className={styles.item}>
      <Mark mark={item.mark} />
      <div className={styles.itemText}>
        <p className={styles.stepTitle}>{item.title}</p>
        <p>{item.text}</p>
        {item.ramp.length >= 2 && (
          <div
            className={styles.ramp}
            role="img"
            aria-label="Color scale"
            style={{ background: `linear-gradient(to right, ${item.ramp.join(', ')})` }}
          />
        )}
        {item.classes.length > 0 && (
          <ul className={styles.swatches}>
            {item.classes.map((c) => (
              <li key={c.name}>
                <span aria-hidden="true" className={styles.swatch} style={{ background: swatchBackground(c) }} />
                {c.name}
              </li>
            ))}
          </ul>
        )}
        {item.lines.map((l) => (
          <p key={l} className={styles.muted}>
            {l}
          </p>
        ))}
      </div>
    </li>
  )
}

function Stamps({ lines }: { lines: StampLine[] }) {
  return (
    <ul className={styles.stamps}>
      {lines.map((s) => (
        <li key={s.text}>
          <span className={styles.stamp}>
            <span aria-hidden="true">{s.icon}</span> {s.text}
          </span>
          <span>{s.meaning}</span>
        </li>
      ))}
    </ul>
  )
}

export default MapGuide
