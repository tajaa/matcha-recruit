import { api } from '../client'
import type {
  ScheduleChatApplyResponse,
  ScheduleChatTurnResponse,
  ScheduleVoiceTranscript,
} from '../../types/scheduleChat'
import type { MWMessage } from '../../work/types'

export interface ScheduleHuumeSession {
  session_id: string
  thread_id: string
  location_id: string
  week_start: string
  week_end: string
  messages: MWMessage[]
  current_state: Record<string, unknown>
  version: number
}

export function getScheduleHuumeSession(locationId: string, weekStart: string) {
  return api.post<ScheduleHuumeSession>('/employee-schedule/assistant/sessions', {
    location_id: locationId,
    week_start: weekStart,
  })
}

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

export function transcribeScheduleVoice(wav: Blob) {
  const form = new FormData()
  form.append('file', wav, 'schedule-request.wav')
  return api.upload<ScheduleVoiceTranscript>('/employee-schedule/chat/voice-transcribe', form)
}
