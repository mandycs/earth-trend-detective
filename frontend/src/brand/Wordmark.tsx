/**
 * The Alibi wordmark: the globe-and-thread symbol next to the name.
 * The symbol scales with the text (1.15em). Headers use the simple symbol (no meridian, no equator),
 * which stays legible at small sizes; pass `full` where the wordmark is large.
 */
export function BrandMark({ full = false }: { full?: boolean }) {
  const src = full ? '/brand/alibi-mark.svg' : '/brand/alibi-favicon.svg'
  return <img className="brand-mark" src={src} alt="" width={24} height={24} />
}

export function Wordmark({ full = false }: { full?: boolean }) {
  return (
    <span className="brand">
      <BrandMark full={full} />
      <span className="brand-name">Alibi</span>
    </span>
  )
}
