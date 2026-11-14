'use client'

import { useState } from 'react'

import type { BeforeAfterPair } from './beforeAfterPair'

export type { BeforeAfterPair }


/** Then-and-now pair with a draggable split. The range input does the work, so keyboard and touch both drive it. */
export function BeforeAfter({ pair, alt }: { pair: BeforeAfterPair; alt: string }) {
  const [split, setSplit] = useState(50)
  return (
    <figure className="ba">
      <div className="ba-frame">
        <img src={pair.after.src} alt={`${alt}, ${pair.after.year}`} className="ba-img" />
        <img
          src={pair.before.src}
          alt={`${alt}, ${pair.before.year}`}
          className="ba-img ba-before"
          style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}
        />
        <span className="ba-handle" style={{ left: `${split}%` }} aria-hidden="true" />
        <span className="ba-year ba-year-left narrow">{pair.before.year}</span>
        <span className="ba-year ba-year-right narrow">{pair.after.year}</span>
        <input
          type="range"
          min={0}
          max={100}
          value={split}
          onChange={(event) => setSplit(Number(event.target.value))}
          aria-label={`Slide between ${pair.before.year} and ${pair.after.year}`}
        />
      </div>
      {pair.note || pair.source ? (
        <figcaption className="ba-caption">
          {pair.note}
          {pair.source ? ` ${pair.source}.` : ''}
        </figcaption>
      ) : null}
    </figure>
  )
}
