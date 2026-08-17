import { api } from '../client'
import type { ScheduleChatApplyResponse, ScheduleChatTurnResponse } from '../../types/scheduleChat'

export function sendScheduleChatMessage(body: {
  message: string
  week_start?: string
  location_id?: string | null
  edit_published?: boolean
  existing_proposal_id?: string
}) {
  return api.post<ScheduleChatTurnResponse>('/employee-schedule/chat', body)
}

export function applyScheduleChat(proposalId: string, body: {
  as_draft: boolean
  edit_published: boolean
}) {
  return api.post<ScheduleChatApplyResponse>(`/employee-schedule/chat/${proposalId}/apply`, body)
}

export function discardScheduleChat(proposalId: string) {
  return api.post<{ ok: boolean }>(`/employee-schedule/chat/${proposalId}/discard`)
}
