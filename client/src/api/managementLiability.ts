import { api } from './client'

export type DoStatus = 'in_place' | 'partial' | 'gap' | 'unknown'
export type DoFactor = {
  key: string
  label: string
  weight: number
  score: number
  status: string
  contribution: number
  detail: string
  assessed: boolean
  attestation?: { status: DoStatus } | null
}
export type DoReadiness = {
  company_id: string
  score: number
  band: string
  coverage: number
  factors: DoFactor[]
  top_gap: { key: string; label: string; score: number } | null
  factor_catalog: Array<{ key: string; label: string; weight: number }>
}

export function getDoReadiness() {
  return api.get<DoReadiness>('/management-liability')
}
export function upsertDoAttestation(body: { item_key: string; status: DoStatus; note?: string }) {
  return api.put<DoReadiness>('/management-liability/attestations', body)
}
