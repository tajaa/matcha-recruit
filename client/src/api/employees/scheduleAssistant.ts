import { api } from '../client'
import type { MWMessage } from '../../work/types'
import type { ScheduleVoiceTranscript } from '../../types/scheduleAssistant'

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

export interface ScheduleSuggestionStatus {
  available: boolean
  generation_run_id: string | null
  week_start: string | null
  created_at: string | null
}

export function getScheduleHuumeSession(locationId: string, weekStart: string) {
  return api.post<ScheduleHuumeSession>('/employee-schedule/assistant/sessions', {
    location_id: locationId,
    week_start: weekStart,
  })
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
