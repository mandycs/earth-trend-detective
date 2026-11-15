/** What a running step says while it waits, by seconds elapsed. */
export const SLOW_AFTER_S = 15
export const VERY_SLOW_AFTER_S = 60

export function waitingNote(seconds: number): string | null {
  if (seconds >= VERY_SLOW_AFTER_S) return 'Still downloading. Some records come from NASA servers in many small pieces; a first visit to a place can take a few minutes.'
  if (seconds >= SLOW_AFTER_S) return 'Downloading satellite records. This can take a minute or two.'
  return null
}

/** "12 s" under a minute, "1 min 05 s" after. */
export function elapsedLabel(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  if (s < 60) return `${s} s`
  const m = Math.floor(s / 60)
  return `${m} min ${String(s % 60).padStart(2, '0')} s`
}
