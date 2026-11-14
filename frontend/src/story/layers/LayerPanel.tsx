import { useState } from 'react'
import type { LayerDef, StackEntry } from './model'
import { STATUS_WORDS, yearStatus } from './model'

export interface LayerPanelProps {
  layers: LayerDef[]
  stack: StackEntry[]
  onStack: (next: StackEntry[]) => void
  year: number
  /** The picture under everything, described honestly. */
  base: { title: string; note: string; status: LayerDef['status'] }
  whys: Record<string, string>
  caption: string | null
  onAsk: (question: string) => Promise<void>
  asking: boolean
  askError: string | null
  identify: boolean
  onIdentify: (on: boolean) => void
  /** Drone: coarse layers are drawn as blocks over a small crop. */
  cropKm?: number
  compareId: string | null
  onCompare: (id: string | null) => void
  /** Short note shown even when folded, e.g. "No map for this record". */
  notice?: string | null
}

function km(metres: number): string {
  const v = metres / 1000
  return v >= 10 ? `${Math.round(v)} km` : `${Math.round(v * 10) / 10} km`
}

function Legend({ def, cropKm }: { def: LayerDef; cropKm?: number }) {
  const g = def.legend
  return (
    <div className="lp-legend">
      {g?.stops && g.stops.length > 1 ? (
        <span className="lp-ramp" aria-hidden="true">
          {g.stops.map((c) => (
            <span key={c} style={{ background: c }} />
          ))}
        </span>
      ) : null}
      {g?.less || g?.more ? (
        <span className="lp-ends">
          <span>
            {g.less}
            {g.range && g.unit ? ` (${g.range[0]} ${g.unit})` : ''}
          </span>
          <span>
            {g.more}
            {g.range && g.unit ? ` (${g.range[1]} ${g.unit})` : ''}
          </span>
        </span>
      ) : null}
      {g?.unit && !(g.less || g.more) ? <span>Unit: {g.unit}</span> : null}
      {def.pixelM && def.pixelM >= 200 ? (
        <span>
          {km(def.pixelM)} pixels, smoothed for display
          {cropKm && def.pixelM / 1000 > cropKm / 3 ? ': coarser than this close-up' : ''}
        </span>
      ) : null}
      {g?.notes.map((n) => (
        <span key={n}>{n}</span>
      ))}
      {def.source?.name ? (
        <span>
          Source:{' '}
          {def.source.url ? (
            <a href={def.source.url} target="_blank" rel="noreferrer noopener">
              {def.source.name}
            </a>
          ) : (
            def.source.name
          )}
        </span>
      ) : null}
    </div>
  )
}

/**
 * QGIS-style layer list: one row per drapable layer, top of the list draws
 * last. Each row: on/off, status, what it shows this year, and when opened,
 * opacity, order and legend.
 */
export function LayerPanel({
  layers,
  stack,
  onStack,
  year,
  base,
  whys,
  caption,
  onAsk,
  asking,
  askError,
  identify,
  onIdentify,
  cropKm,
  compareId,
  onCompare,
  notice,
}: LayerPanelProps) {
  const [open, setOpen] = useState<string | null>(null)
  const [question, setQuestion] = useState('')
  const [dragging, setDragging] = useState<string | null>(null)
  const [folded, setFolded] = useState(true)
  const onCount = stack.filter((s) => s.on).length

  const update = (id: string, patch: Partial<StackEntry>) =>
    onStack(stack.map((s) => (s.id === id ? { ...s, ...patch } : s)))

  const move = (from: number, to: number) => {
    if (to < 0 || to >= stack.length || from === to) return
    const next = stack.slice()
    const [item] = next.splice(from, 1)
    next.splice(to, 0, item)
    onStack(next)
  }

  return (
    <section className={folded ? 'lp lp-folded' : 'lp'} aria-label="Map layers">
      <button type="button" className="lp-fold" aria-expanded={!folded} onClick={() => setFolded((f) => !f)}>
        <span>
          Layers{onCount ? ` · ${onCount} on` : ''}
          {notice ? <span className="lp-notice"> · {notice}</span> : null}
        </span>
        <span aria-hidden="true">{folded ? '+' : '−'}</span>
      </button>
      {folded ? null : (
        <>
      <form
        className="lp-ask"
        onSubmit={(e) => {
          e.preventDefault()
          if (question.trim()) void onAsk(question.trim())
        }}
      >
        <label htmlFor="lp-question" className="sr-only">
          Ask the map
        </label>
        <input
          id="lp-question"
          type="text"
          placeholder="Ask the map, e.g. is it getting less green?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={200}
        />
        <button type="submit" className="btn btn-primary" disabled={asking || !question.trim()}>
          {asking ? <span className="spinner" aria-hidden="true" /> : 'Ask'}
        </button>
      </form>
      {askError ? (
        <p className="lp-note" role="alert">
          {askError}
        </p>
      ) : null}
      {caption ? <p className="lp-caption">{caption}</p> : null}

      <ol className="lp-list">
        {stack.map((entry, index) => {
          const def = layers.find((l) => l.id === entry.id)
          if (!def) return null
          const status = yearStatus(def, year)
          const missing = status.startsWith('no data')
          const expanded = open === def.id
          return (
            <li
              key={def.id}
              className={`lp-row${entry.on ? ' lp-on' : ''}${dragging === def.id ? ' lp-dragging' : ''}`}
              draggable
              onDragStart={(e) => {
                setDragging(def.id)
                e.dataTransfer.effectAllowed = 'move'
              }}
              onDragEnd={() => setDragging(null)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault()
                const from = stack.findIndex((s) => s.id === dragging)
                move(from, index)
                setDragging(null)
              }}
            >
              <div className="lp-head">
                <label className="lp-check">
                  <input type="checkbox" checked={entry.on} onChange={(e) => update(def.id, { on: e.target.checked })} />
                  <span className="lp-title">{def.title}</span>
                </label>
                <button
                  type="button"
                  className="lp-more"
                  aria-expanded={expanded}
                  aria-label={`${expanded ? 'Hide' : 'Show'} details for ${def.title}`}
                  onClick={() => setOpen(expanded ? null : def.id)}
                >
                  {expanded ? '−' : '+'}
                </button>
              </div>
              <div className="lp-meta">
                <span className={`lp-chip lp-chip-${def.status}`}>{STATUS_WORDS[def.status]}</span>
                <span className={missing ? 'lp-year lp-missing' : 'lp-year'}>{status}</span>
              </div>
              {whys[def.id] ? <p className="lp-why">{whys[def.id]}</p> : null}
              {expanded ? (
                <div className="lp-body">
                  <label className="lp-opacity">
                    <span>Opacity</span>
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={entry.opacity}
                      onChange={(e) => update(def.id, { opacity: Number(e.target.value) })}
                    />
                  </label>
                  <div className="lp-order">
                    <button type="button" className="lp-btn" onClick={() => move(index, index - 1)} disabled={index === 0}>
                      Up
                    </button>
                    <button type="button" className="lp-btn" onClick={() => move(index, index + 1)} disabled={index === stack.length - 1}>
                      Down
                    </button>
                  </div>
                  <Legend def={def} cropKm={cropKm} />
                </div>
              ) : null}
            </li>
          )
        })}
        <li className="lp-row lp-base">
          <div className="lp-head">
            <span className="lp-title">{base.title}</span>
          </div>
          <div className="lp-meta">
            <span className={`lp-chip lp-chip-${base.status}`}>{STATUS_WORDS[base.status]}</span>
            <span className="lp-year">{base.note}</span>
          </div>
          {whys.__base ? <p className="lp-why">{whys.__base}</p> : null}
        </li>
      </ol>

      {(() => {
        const coloured = layers.filter((l) => l.role === 'overlay' && l.blend !== 'multiply')
        const main = stack.find((s) => s.on && coloured.some((c) => c.id === s.id))
        if (!main || coloured.length < 2) return null
        return (
          <label className="lp-compare">
            <span>Compare through a curtain</span>
            <select value={compareId ?? ''} onChange={(e) => onCompare(e.target.value || null)}>
              <option value="">No comparison</option>
              {coloured
                .filter((c) => c.id !== main.id)
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.title}
                  </option>
                ))}
            </select>
          </label>
        )
      })()}

      <button type="button" className={identify ? 'lp-identify lp-identify-on' : 'lp-identify'} aria-pressed={identify} onClick={() => onIdentify(!identify)}>
        {identify ? 'Identify is on: click the ground' : 'Identify: read values at a point'}
      </button>
        </>
      )}
    </section>
  )
}
