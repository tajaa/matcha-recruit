import { api } from '../../../api/client'
import type { HuumeAsset, HuumePlan, HuumeRecordRef, HuumeRecordView, HuumeThreadOffer } from '../../types'

export function approveHuumePlan(threadId: string, offerId: string, stepKeys?: string[]) {
  return api.post<{ plan: HuumePlan; offer_id: string }>(`/matcha-work/threads/${threadId}/huume/plan/approve`, {
    offer_id: offerId,
    step_keys: stepKeys && stepKeys.length > 0 ? stepKeys : undefined,
  })
}

export function executeHuumePlan(threadId: string, offerId: string) {
  return api.post<{ plan: HuumePlan; summary: string; offer_id: string }>(`/matcha-work/threads/${threadId}/huume/plan/execute`, {
    offer_id: offerId,
  })
}

export function getHuumeRecord(threadId: string, recordType: string, recordId: string) {
  return api.get<HuumeRecordView>(
    `/matcha-work/threads/${threadId}/huume/record?record_type=${encodeURIComponent(recordType)}&record_id=${encodeURIComponent(recordId)}`,
  )
}

/** Company-scoped twin for the Assets page, which has no thread in scope
 * (an asset's thread_id is nullable — the thread may be gone). */
export function getHuumeRecordForCompany(recordType: string, recordId: string) {
  return api.get<HuumeRecordView>(
    `/matcha-work/huume/record?record_type=${encodeURIComponent(recordType)}&record_id=${encodeURIComponent(recordId)}`,
  )
}

export function closeHuumeRecord(threadId: string, recordType: string, recordId: string) {
  return api.delete<{ records: HuumeRecordRef[] }>(
    `/matcha-work/threads/${threadId}/huume/record?record_type=${encodeURIComponent(recordType)}&record_id=${encodeURIComponent(recordId)}`,
  )
}

export function listThreadOffers(threadId: string) {
  return api.get<{ offers: HuumeThreadOffer[] }>(`/matcha-work/threads/${threadId}/huume/offers`)
}

export function listHuumeAssets(threadId: string, scope: 'thread' | 'company' = 'thread') {
  return api.get<{ assets: HuumeAsset[] }>(
    `/matcha-work/threads/${threadId}/huume/assets?scope=${scope}`,
  )
}

/** Company-wide feed for the standalone Assets page — every asset Huume has
 * ever created, across every thread, not scoped to one chat. */
export function listCompanyHuumeAssets(opts?: { assetType?: string; query?: string }) {
  const params = new URLSearchParams()
  if (opts?.assetType) params.set('asset_type', opts.assetType)
  if (opts?.query) params.set('query', opts.query)
  const qs = params.toString()
  return api.get<{ assets: HuumeAsset[] }>(`/matcha-work/huume/assets${qs ? `?${qs}` : ''}`)
}
