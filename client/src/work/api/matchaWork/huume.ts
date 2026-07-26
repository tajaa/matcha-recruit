import { api } from '../../../api/client'
import type { HuumePlan } from '../../types'

export function approveHuumePlan(threadId: string, stepKeys?: string[]) {
  return api.post<{ plan: HuumePlan }>(`/matcha-work/threads/${threadId}/huume/plan/approve`, {
    step_keys: stepKeys && stepKeys.length > 0 ? stepKeys : undefined,
  })
}

export function executeHuumePlan(threadId: string) {
  return api.post<{ plan: HuumePlan; summary: string }>(`/matcha-work/threads/${threadId}/huume/plan/execute`)
}
