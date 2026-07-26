import { api } from '../../../api/client'
import type { HuumePlan } from '../../types'

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
