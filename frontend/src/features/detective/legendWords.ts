// Legend labels in plain words (UX checklist: no statistics jargon in the main UI). Pure.
// Case files and trend_map legends say "Faded = not statistically significant (Mann-Kendall p ≥ 0.05)"; the screen
// says what that means for the person instead.

export const FADED_PLAIN = "Faded = could be chance at this pixel";

const JARGON = /mann[-\s]?kendall|p[-\s]?value|\bp\s*[≥>=<≤]|significan/i;

/** A label with statistics jargon: the "faded" one becomes `FADED_PLAIN`; any other is dropped (null). */
export function plainLegendLabel(label: string): string | null {
  if (!JARGON.test(label)) return label;
  return /faded/i.test(label) ? FADED_PLAIN : null;
}

/** Every label in plain words, order kept, jargon-only labels dropped, no duplicates. */
export function plainLegendLabels(labels: readonly string[]): string[] {
  const out: string[] = [];
  for (const l of labels) {
    const p = plainLegendLabel(l);
    if (p !== null && !out.includes(p)) out.push(p);
  }
  return out;
}
