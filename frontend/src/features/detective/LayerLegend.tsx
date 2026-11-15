'use client'

import { useId, useState } from 'react'
import { LandCoverKey } from './LandCoverKey'
import { legendModel } from './map/draw'
import type { MapView } from './map/mapView'
import styles from './detective.module.css'

/** Legend, source and resolution of every drawn layer. Folded by default (DESIGN: "Panels start folded"). */
/** `flat`: the relief failed to load, so the legend drops the "Heights ×N" claim. */
export function LayerLegend({ view, flat = false }: { view: MapView; flat?: boolean }) {
  const [open, setOpen] = useState(false)
  const panelId = useId()
  const model = legendModel(view, { flat })
  if (!model) return null
  return (
    <section className={styles.legend} aria-label="Layer and source">
      <button
        type="button"
        className={styles.legendToggle}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
      >
        <span aria-hidden="true" className={styles.legendChevron}>
          {open ? '−' : '+'}
        </span>
        Layer and source
      </button>
      {open ? (
        <div id={panelId} className={styles.legendPanel}>
          {model.curtain ? <p className={styles.legendCurtain}>{model.curtain}</p> : null}
          {model.entries.map((e) => (
            <div key={e.key} className={styles.legendEntry}>
              <p className={styles.legendRole}>{e.role}</p>
              <p className={styles.legendTitle}>{e.title}</p>
              {e.when ? <p>{e.when}</p> : null}
              {e.ramp.length >= 2 ? (
                <div
                  className={styles.legendRamp}
                  role="img"
                  aria-label={`Colour ramp${e.unit ? ` for ${e.unit}` : ''}`}
                  style={{ background: `linear-gradient(to right, ${e.ramp.join(', ')})` }}
                />
              ) : null}
              <LandCoverKey classes={e.classes} />
              {e.unit ? (
                <p>
                  {e.unit}
                  {e.range ? ` · ${e.range}` : ''}
                </p>
              ) : null}
              {e.labels.map((l) => (
                <p key={l} className={styles.legendMuted}>
                  {l}
                </p>
              ))}
              {e.source ? <p className={styles.legendMuted}>Source: {e.source}</p> : null}
              {e.resolution ? <p className={styles.legendMuted}>{e.resolution}</p> : null}
            </div>
          ))}
          {model.footprints.map((f) => (
            <div key={f.key} className={styles.legendEntry}>
              <p className={styles.legendRole}>
                <span aria-hidden="true" className={styles.dashSwatch} /> Data cell
              </p>
              <p className={styles.legendTitle}>{f.text}</p>
              {f.size ? <p className={styles.legendMuted}>Size: {f.size}</p> : null}
            </div>
          ))}
          <p className={styles.legendMuted}>{model.terrain}</p>
        </div>
      ) : null}
    </section>
  )
}

export default LayerLegend
