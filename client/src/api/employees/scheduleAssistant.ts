import { api } from '../client'
import type { MWMessage } from '../../work/types'
import type { ScheduleVoiceTranscript } from '../../types/scheduleAssistant'

export interface ScheduleHuumeSession {
  session_id: string
  thread_id: string
  location_id: string
  week_start: string
  week_end: string
  title: string
  messages: MWMessage[]
  current_state: Record<string, unknown>
  version: number
}

export interface ScheduleHuumeSessionSummary {
  session_id: string
  thread_id: string
  title: string
  message_count: number
  created_at: string
  last_activity_at: string
}

export interface ScheduleSuggestionStatus {
  available: boolean
  generation_run_id: string | null
  week_start: string | null
  created_at: string | null
}

/** Omit `sessionId` to start a new chat; pass one to reopen a previous chat. */
export function getScheduleHuumeSession(locationId: string, weekStart: string, sessionId?: string | null) {
  return api.post<ScheduleHuumeSession>('/employee-schedule/assistant/sessions', {
    location_id: locationId,
    week_start: weekStart,
    session_id: sessionId ?? null,
  })
}

export function listScheduleHuumeSessions(locationId: string, weekStart: string) {
  const params = new URLSearchParams({ location_id: locationId, week_start: weekStart })
  return api.get<{ sessions: ScheduleHuumeSessionSummary[] }>(`/employee-schedule/assistant/sessions?${params}`)
}

export function archiveScheduleHuumeSession(sessionId: string) {
  return api.post<{ session_id: string; archived: boolean }>(
    `/employee-schedule/assistant/sessions/${sessionId}/archive`,
    {},
  )
}

/** Schedule Pilot "Stage this": make a fill scenario (a proposal the caller
 *  previewed) the thread's staged schedule change. Returns the thread's new
 *  `current_state`, whose `huume_action` the review pane and card render. */
export function adoptScheduleProposal(sessionId: string, proposalId: string) {
  return api.post<{ current_state: Record<string, unknown>; version: number; confirm_id: string }>(
    `/employee-schedule/assistant/sessions/${sessionId}/adopt-proposal`,
    { proposal_id: proposalId },
  )
}

export function getScheduleSuggestionStatus(locationId: string, weekStart: string) {
  const params = new URLSearchParams({ location_id: locationId, week_start: weekStart })
  return api.get<ScheduleSuggestionStatus>(`/employee-schedule/assistant/suggestions?${params}`)
}

export function transcribeScheduleVoice(wav: Blob) {
  const form = new FormData()
  form.append('file', wav, 'schedule-request.wav')
  return api.upload<ScheduleVoiceTranscript>('/employee-schedule/assistant/voice-transcribe', form)
}
