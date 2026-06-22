import { api } from './client'
import type { LimitReview, CoverageList, CoverageRow, ContractRecord, ContractRequirement } from '../types/limitAdequacy'

export function fetchLimitReview() {
  return api.get<LimitReview>('/limit-adequacy/review')
}

export function fetchCoverage() {
  return api.get<CoverageList>('/limit-adequacy/coverage')
}

export type CoveragePayload = Partial<Omit<CoverageRow, 'line' | 'updated_at'>>

export function upsertCoverage(line: string, payload: CoveragePayload) {
  return api.put<LimitReview>(`/limit-adequacy/coverage/${line}`, payload)
}

export function deleteCoverage(line: string) {
  return api.delete<LimitReview>(`/limit-adequacy/coverage/${line}`)
}

export function fetchContracts() {
  return api.get<{ contracts: ContractRecord[] }>('/limit-adequacy/contracts')
}

export function uploadContract(file: File) {
  const fd = new FormData()
  fd.append('file', file)
  return api.upload<ContractRecord>('/limit-adequacy/contracts/upload', fd)
}

export function createContract(payload: { name: string; counterparty?: string | null; requirements: ContractRequirement[] }) {
  return api.post<ContractRecord>('/limit-adequacy/contracts', payload)
}

export function updateContract(id: string, payload: { name?: string; counterparty?: string | null; requirements?: ContractRequirement[] }) {
  return api.put<ContractRecord>(`/limit-adequacy/contracts/${id}`, payload)
}

export function deleteContract(id: string) {
  return api.delete<{ deleted: boolean }>(`/limit-adequacy/contracts/${id}`)
}

export function downloadReviewPdf() {
  return api.download('/limit-adequacy/review.pdf', 'limit-adequacy.pdf')
}
