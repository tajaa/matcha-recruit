import { api } from '../client'

export type CoiLine = {
  line: string
  per_occurrence: number | null
  aggregate: number | null
  effective_date: string | null
  expiry_date: string | null
  additional_insured?: boolean
  waiver_of_subrogation?: boolean
}
export type CoiStatus = 'active' | 'expiring' | 'expired' | 'unknown'
export type Certificate = {
  id: string
  holder_name: string | null
  carrier: string | null
  certificate_number: string | null
  lines: CoiLine[]
  expiry_date: string | null
  status: CoiStatus
  contract_id: string | null
  ai_available: boolean
  source_filename: string | null
  verification: {
    lines: Array<{ key: string; label: string; status: string }>
    summary: { contract_shortfalls?: number }
  } | null
}
export type CoiList = {
  certificates: Certificate[]
  summary: { total: number; active: number; expiring: number; expired: number; unknown: number; with_gaps: number }
}

export function listCois() {
  return api.get<CoiList>('/coi')
}
export function uploadCoi(file: File, holderName?: string, contractId?: string) {
  const fd = new FormData()
  fd.append('file', file)
  if (holderName) fd.append('holder_name', holderName)
  if (contractId) fd.append('contract_id', contractId)
  return api.upload<CoiList>('/coi', fd)
}
export function deleteCoi(id: string) {
  return api.delete<CoiList>(`/coi/${id}`)
}
