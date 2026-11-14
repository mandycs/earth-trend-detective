import type { Metadata } from 'next'
import InvestigateView from '../../features/investigate/InvestigateView'

export const metadata: Metadata = {
  title: 'Ask the detective · Earth Trend Detective',
  description: 'Pick a place, ask a question, and watch the detective run its NASA checks one by one.',
}

export default async function InvestigatePage({ searchParams }: { searchParams: Promise<{ site?: string }> }) {
  const { site } = await searchParams
  return <InvestigateView initialSite={site} />
}
