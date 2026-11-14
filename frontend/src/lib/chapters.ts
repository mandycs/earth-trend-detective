import type { Site } from '../story/types'
import { fmt, leadVariable, residualText, slopeText } from './cases'

/** One documentary chapter: a question, and a subtitle built only from site.json. */
export interface Chapter {
  name: string
  headline: string
  line: string
}

export const CHAPTER_NAMES = ['What is changing?', 'Is it real?', 'Is it the climate?'] as const

export function chaptersFor(site: Site): Chapter[] {
  const lead = leadVariable(site)
  const [first, last] = site.years
  if (!lead) {
    return CHAPTER_NAMES.map((name) => ({ name, headline: site.name, line: `${first}–${last}` }))
  }
  const label = lead.label
  const slope = slopeText(lead)
  const going = lead.direction === 'down' ? 'going down' : lead.direction === 'up' ? 'going up' : 'changing'

  // 1 · What is changing?
  const one: Chapter = {
    name: CHAPTER_NAMES[0],
    headline: lead.verdict === 'unknown' ? `${label}: no clear change yet` : `${label} is ${going}`,
    line: slope ? `${slope} per decade, ${first}–${last}.` : `${first}–${last}.`,
  }

  // 2 · Is it real?
  const range =
    lead.ci_low != null && lead.ci_high != null
      ? `Most likely between ${fmt(lead.ci_low, true)} and ${fmt(lead.ci_high, true)} ${lead.unit} per decade.`
      : ''
  const two: Chapter = {
    name: CHAPTER_NAMES[1],
    headline:
      lead.verdict === 'real'
        ? 'Real: too steady to be chance'
        : lead.verdict === 'likely'
          ? 'Likely: a strong hint, not yet proof'
          : "Can't tell yet: too noisy to call",
    line: range || (lead.years_needed ? `About ${lead.years_needed} more years of data would be needed.` : ''),
  }

  // 3 · Is it the climate?
  const residual = residualText(lead)
  const caveat = (site.caveats ?? []).find((c) => /split|climate/i.test(c) && !/clue/i.test(c))
  const three: Chapter = residual
    ? {
        name: CHAPTER_NAMES[2],
        headline: `${residual} is not explained by the climate`,
        line: `${lead.residual_pct_range ? 'Depending on the climate model. ' : ''}A clue, not proof.`,
      }
    : {
        name: CHAPTER_NAMES[2],
        headline: 'No climate split for this place',
        line: caveat ?? 'The trends stand; the share left by the climate is not computed here.',
      }

  return [one, two, three]
}
