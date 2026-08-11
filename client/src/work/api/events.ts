import { api } from '../../api/client'

// ── Types ──

export type EmsEventCategory =
  | 'behavioral'
  | 'safety'
  | 'operational'
  | 'equipment'
  | 'property'
  | 'guest_experience'
  | 'uncategorized'

export type EmsEventStatus = 'logged' | 'completed' | 'promoted' | 'dismissed'

export interface EmsEvent {
  id: string
  company_id: string
  channel_id: string | null
  channel_name: string | null
  location_id: string | null
  location_name: string | null
  message_id: string | null
  reporter_user_id: string | null
  reporter_name: string | null
  title: string | null
  category: EmsEventCategory
  severity_hint: 'low' | 'medium' | 'high' | null
  doc: Record<string, string>
  narrative: string
  incident_recommendation: boolean
  incident_reasoning: string | null
  suggested_incident_type: string | null
  suggested_severity: string | null
  urgency: 'osha' | 'severe' | null
  protocol_qualifies: boolean | null
  protocol_reasoning: string | null
  status: EmsEventStatus
  resolved_by?: string | null
  resolved_at?: string | null
  resolution_note?: string | null
  resolution_code?: 'handled' | 'not_event' | 'duplicate' | 'informational' | null
  duplicate_of_event_id?: string | null
  incident_id: string | null
  // True while Huume has posted a follow-up question in-channel that hasn't
  // been answered yet (ems_events.clarify_message_id IS NOT NULL server-side).
  awaiting_reply: boolean
  clarification_rounds: number
  created_at: string
  updated_at: string
}

export interface EmsEventListResponse {
  events: EmsEvent[]
  total: number
}

export interface EmsEventFilters {
  status?: string
  category?: string
  channel_id?: string
  limit?: number
  offset?: number
}

export interface EmsEventUpdate {
  title?: string
  category?: string
  doc?: Record<string, string>
  dismissed?: boolean
}

export interface EmsEventDraft {
  id: string
  company_id: string
  channel_id: string
  source_message_id: string
  confirmation_message_id: string | null
  reporter_user_id: string | null
  location_id: string | null
  narrative: string
  classified: Record<string, unknown>
  urgency: 'osha' | 'severe' | null
  status: 'pending' | 'confirmed' | 'rejected' | 'expired'
  event_id: string | null
  decided_by: string | null
  decided_at: string | null
  expires_at: string
  created_at: string
  updated_at: string
}

export interface EmsEventDraftRejectRequest {
  reason?: string
}

export interface EmsEventResolveRequest {
  resolution: 'completed' | 'no_action'
  note?: string
  resolution_code?: 'handled' | 'not_event' | 'duplicate' | 'informational'
  duplicate_of_event_id?: string
}

export interface EmsPromoteRequest {
  title?: string
  incident_type?: string
  severity?: string
  occurred_at?: string
  location?: string
  witnesses?: string[]
}

export interface EmsPromoteResponse {
  incident_id: string
}

export const EMS_CATEGORY_LABELS: Record<EmsEventCategory, string> = {
  behavioral: 'Behavioral',
  safety: 'Safety',
  operational: 'Operational',
  equipment: 'Equipment',
  property: 'Property',
  guest_experience: 'Guest Experience',
  uncategorized: 'Uncategorized',
}

// ── API calls ──

export function listEvents(filters: EmsEventFilters = {}) {
  const params = new URLSearchParams()
  if (filters.status) params.set('status', filters.status)
  if (filters.category) params.set('category', filters.category)
  if (filters.channel_id) params.set('channel_id', filters.channel_id)
  params.set('limit', String(filters.limit ?? 50))
  params.set('offset', String(filters.offset ?? 0))
  return api.get<EmsEventListResponse>(`/ems/events?${params}`)
}

export function getEvent(id: string) {
  return api.get<EmsEvent>(`/ems/events/${id}`)
}

export function updateEvent(id: string, body: EmsEventUpdate) {
  return api.put<EmsEvent>(`/ems/events/${id}`, body)
}

export function promoteEvent(id: string, overrides: EmsPromoteRequest = {}) {
  return api.post<EmsPromoteResponse>(`/ems/events/${id}/promote`, overrides)
}

export function getEventDraft(id: string) {
  return api.get<EmsEventDraft>(`/ems/event-drafts/${id}`)
}

export function confirmEventDraft(id: string) {
  return api.post<EmsEvent>(`/ems/event-drafts/${id}/confirm`, {})
}

export function rejectEventDraft(id: string, body: EmsEventDraftRejectRequest = {}) {
  return api.post<EmsEventDraft>(`/ems/event-drafts/${id}/reject`, body)
}

export function resolveEvent(id: string, body: EmsEventResolveRequest) {
  return api.post<EmsEvent>(`/ems/events/${id}/resolve`, body)
}
