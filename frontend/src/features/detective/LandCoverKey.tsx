import type { LandCoverClass } from './map/landCover'
import { swatchBackground } from './map/landCover'
import styles from './landCoverKey.module.css'

/** Swatches with plain names for a classed layer (land cover). Nothing when the layer has no classes. */
export function LandCoverKey({ classes, compact = false }: { classes: readonly LandCoverClass[]; compact?: boolean }) {
  if (classes.length === 0) return null
  return (
    <span className={`${styles.key} ${compact ? styles.compact : ''}`} role="list" aria-label="What the colors mean">
      {classes.map((c) => (
        <span key={c.name} className={styles.item} role="listitem">
          <span className={styles.swatch} style={{ background: swatchBackground(c) }} aria-hidden="true" />
          <span>{c.name}</span>
        </span>
      ))}
    </span>
  )
}
