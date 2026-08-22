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

export function getScheduleHuumeSession(locationId: string, weekStart: string) {
  return api.post<ScheduleHuumeSession>('/employee-schedule/assistant/sessions', {
    location_id: locationId,
    week_start: weekStart,
  })
}

export function transcribeScheduleVoice(wav: Blob) {
  const form = new FormData()
  form.append('file', wav, 'schedule-request.wav')
  return api.upload<ScheduleVoiceTranscript>('/employee-schedule/assistant/voice-transcribe', form)
}
