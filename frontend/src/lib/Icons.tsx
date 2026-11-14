/** Small UI icons drawn in SVG, so they render the same everywhere. */
export function PlayPauseIcon({ playing }: { playing: boolean }) {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" focusable="false">
      {playing ? (
        <>
          <rect x="3" y="2" width="4" height="14" fill="currentColor" />
          <rect x="11" y="2" width="4" height="14" fill="currentColor" />
        </>
      ) : (
        <path d="M4 2 L16 9 L4 16 Z" fill="currentColor" />
      )}
    </svg>
  )
}

export function CloseIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <path d="M2 2 L14 14 M14 2 L2 14" stroke="currentColor" strokeWidth="2.5" />
    </svg>
  )
}
