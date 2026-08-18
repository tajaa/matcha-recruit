import { api } from '../client'

export type SafetyMeetingStatus = 'recording' | 'review' | 'signed'

export type ActionItem = {
  description: string
  owner?: string | null
}

export type SafetyMeeting = {
  id: string
  company_id: string
  location_id?: string | null
  location_name?: string | null
  title: string
  topic?: string | null
  status: SafetyMeetingStatus
  started_at: string
  ended_at?: string | null
  transcript_segments: { idx: number; text: string; audio_path?: string | null }[]
  transcript?: string | null
  summary?: string | null
  topics: string[]
  action_items: ActionItem[]
  attendee_names: string[]
  manager_notes?: string | null
  summary_model?: string | null
  created_by?: string | null
  signed_by?: string | null
  signed_at?: string | null
  signature_name?: string | null
  created_at: string
  updated_at: string
}

export type SafetyMeetingListItem = {
  id: string
  title: string
  status: SafetyMeetingStatus
  location_name?: string | null
  attendee_count: number
  started_at: string
  ended_at?: string | null
  signed_at?: string | null
  signature_name?: string | null
}

export type LocationOption = {
  id: string
  name: string
  city?: string | null
  state?: string | null
}

export async function listSafetyMeetings() {
  return api.get<{ meetings: SafetyMeetingListItem[] }>('/safety-meetings')
}

export async function listSafetyMeetingLocations() {
  return api.get<{ locations: LocationOption[] }>('/safety-meetings/locations')
}

export async function createSafetyMeeting(body: {
  title: string
  topic?: string | null
  location_id?: string | null
  attendee_names: string[]
}) {
  return api.post<SafetyMeeting>('/safety-meetings', body)
}

export async function getSafetyMeeting(id: string) {
  return api.get<SafetyMeeting>(`/safety-meetings/${id}`)
}

export async function uploadSafetyMeetingChunk(id: string, blob: Blob, index: number) {
  const form = new FormData()
  form.append('file', blob, `meeting-chunk-${index}.wav`)
  form.append('chunk_index', String(index))
  return api.upload<{ idx: number; transcript?: string | null; available: boolean }>(
    `/safety-meetings/${id}/chunks`,
    form,
  )
}

export async function finishSafetyMeeting(id: string) {
  return api.post<SafetyMeeting>(`/safety-meetings/${id}/finish`)
}

export async function updateSafetyMeeting(id: string, body: {
  title?: string
  topic?: string | null
  summary?: string | null
  manager_notes?: string | null
  attendee_names?: string[]
  topics?: string[]
  action_items?: ActionItem[]
}) {
  return api.patch<SafetyMeeting>(`/safety-meetings/${id}`, body)
}

export async function signSafetyMeeting(id: string, signature_name: string) {
  return api.post<SafetyMeeting>(`/safety-meetings/${id}/sign`, {
    signature_name,
    confirm: true,
  })
}

export async function deleteSafetyMeeting(id: string) {
  return api.delete<void>(`/safety-meetings/${id}`)
}
