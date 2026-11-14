import type { SiteVariable } from '../../story/types'

export interface InvPlace {
  id: string
  name: string
  lat: number
  lon: number
  tags: string[]
  years: [number, number]
}

export interface PlanStep {
  id: string
  title: string
  why: string
  seconds: number
}

export interface Plan {
  source: 'llm' | 'default' | string
  steps: PlanStep[]
}

export type StepLayer =
  | { kind: 'point'; center: [number, number] }
  | { kind: 'footprint'; center: [number, number]; width_km: number }
  | { kind: 'wms'; layer: string; bbox: [number, number, number, number]; years: number[] }

export interface Source {
  id?: string
  title?: string
  name?: string
  url?: string
}

export interface VariablesResult {
  variables: SiteVariable[]
  missing?: Record<string, string>
  status?: string
  sources?: Source[]
  layer?: StepLayer
}

export interface LandCoverSide {
  year: number
  dominant: string
  shares: Record<string, number>
}

export interface LandCoverResult {
  before: LandCoverSide | null
  after: LandCoverSide | null
  changes: Array<{ class: string; before: number; after: number; change: number }>
  tags?: string[]
  source?: Source
  status?: string
  layer?: StepLayer
}

export interface PictureSide {
  year: number
  date: string
  url: string
  cloud_or_gap_share?: number
}

export interface ThenNowResult {
  layer: string
  bbox: [number, number, number, number]
  status: string
  before: PictureSide | null
  after: PictureSide | null
}

export interface ExplainResult {
  text: string | null
  note?: string
  source?: string
  validation?: { ok?: boolean }
}

export type StepState =
  | { status: 'pending' }
  | { status: 'running'; startedAt: number }
  | { status: 'done'; seconds: number; result: unknown }
  | { status: 'failed'; message: string }

export type InvEvent =
  | { event: 'place'; data: InvPlace }
  | { event: 'plan'; data: Plan }
  | { event: 'step_start'; data: { index: number; id: string; title: string } }
  | { event: 'step_done'; data: { index: number; id: string; seconds: number; result: unknown } }
  | { event: 'step_failed'; data: { index: number; id: string; message: string } }
  | { event: 'done'; data: unknown }
