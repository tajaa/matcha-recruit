import { api } from '../client'
import type {
  LimitReview, CoverageList, CoverageRow, ContractRecord, ContractRequirement,
  ContractReview, ContractType, RiskTransfer,
} from '../../types/limitAdequacy'

export function fetchLimitReview() {
  return api.get<LimitReview>('/limit-adequacy/review')
}

export function fetchCoverage() {
  return api.get<CoverageList>('/limit-adequacy/coverage')
}

export type CoveragePayload = Partial<Omit<CoverageRow, 'line' | 'updated_at'>>

export function upsertCoverage(line: string, payload: CoveragePayload) {
  return api.put<LimitReview>(`/limit-adequacy/coverage/${encodeURIComponent(line)}`, payload)
}

export function deleteCoverage(line: string) {
  return api.delete<LimitReview>(`/limit-adequacy/coverage/${encodeURIComponent(line)}`)
}

export function fetchContracts() {
  return api.get<{ contracts: ContractRecord[] }>('/limit-adequacy/contracts')
}

export function uploadContract(file: File) {
  const fd = new FormData()
  fd.append('file', file)
  return api.upload<ContractRecord>('/limit-adequacy/contracts/upload', fd)
}

export type ContractPayload = {
  name?: string
  counterparty?: string | null
  requirements?: ContractRequirement[]
  contract_type?: ContractType | null
  governing_state?: string | null
  project_state?: string | null
  risk_transfer?: RiskTransfer | null
}

export function createContract(payload: ContractPayload & { name: string; requirements: ContractRequirement[] }) {
  return api.post<ContractRecord>('/limit-adequacy/contracts', payload)
}

export function updateContract(id: string, payload: ContractPayload) {
  return api.put<ContractRecord>(`/limit-adequacy/contracts/${id}`, payload)
}

export function deleteContract(id: string) {
  return api.delete<{ deleted: boolean }>(`/limit-adequacy/contracts/${id}`)
}

/** Vouch for the extracted terms — lifts the "provisional" label off the verdict. */
export function confirmContract(id: string) {
  return api.post<ContractRecord>(`/limit-adequacy/contracts/${id}/confirm`, {})
}

export function fetchContractReview(id: string) {
  return api.get<ContractReview>(`/limit-adequacy/contracts/${id}/review`)
}

export function downloadContractReviewPdf(id: string, name: string) {
  return api.download(`/limit-adequacy/contracts/${id}/review.pdf`, `contract-review-${name}.pdf`)
}

/** Time-limited link to the retained source PDF. 404s when it wasn't retained. */
export function fetchContractSourceUrl(id: string) {
  return api.get<{ url: string }>(`/limit-adequacy/contracts/${id}/file`)
}

export function downloadReviewPdf() {
  return api.download('/limit-adequacy/review.pdf', 'limit-adequacy.pdf')
}
