import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import StoryApp from '../../../story/StoryApp'
import { CASE_IDS, isCaseId } from '../../../lib/cases'
import '../../../story/story.css'

export function generateStaticParams() {
  return CASE_IDS.map((id) => ({ id }))
}

export const dynamicParams = false

const TITLES: Record<string, string> = {
  lake_mead: 'Lake Mead',
  aletsch: 'Aletsch Glacier',
  donana: 'Doñana',
  great_barrier_reef: 'Great Barrier Reef',
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params
  return { title: `${TITLES[id] ?? 'Case'} · Alibi` }
}

export default async function StoryPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  if (!isCaseId(id)) notFound()
  return <StoryApp caseId={id} />
}
