// Cappe ↔ matcha IR bridge — typed wrappers over /api/cappe/ir/*.
//
// A Cappe account with `matcha_features.incidents` can use matcha's IR
// incident-reporting feature through a cappe-native adapter (backend:
// server/app/cappe/routes/ir.py). Types below mirror matcha's IR response
// shapes (server/app/matcha/models/ir_incident.py) but are declared locally so
// cappe never imports matcha page/component types.

import { cappeApi } from './cappeClient'

// --- Shared enums -------------------------------------------------------------

export type CappeIrIncidentType = 'safety' | 'behavioral' | 'property' | 'near_miss' | 'other'
export type CappeIrSeverity = 'critical' | 'high' | 'medium' | 'low'
export type CappeIrStatus = 'reported' | 'investigating' | 'action_required' | 'resolved' | 'closed'
export type CappeIrDocumentType = 'photo' | 'form' | 'statement' | 'other'

export const CAPPE_IR_INCIDENT_TYPES: CappeIrIncidentType[] = ['safety', 'behavioral', 'property', 'near_miss', 'other']
export const CAPPE_IR_SEVERITIES: CappeIrSeverity[] = ['critical', 'high', 'medium', 'low']
export const CAPPE_IR_STATUSES: CappeIrStatus[] = ['reported', 'investigating', 'action_required', 'resolved', 'closed']

// --- Locations (cappe-owned helper surface) -----------------------------------

export type CappeIrLocation = {
  id: string
  name: string | null
  address: string | null
  city: string
  state: string
  zipcode: string
}

export type CappeIrLocationInput = {
  name?: string | null
  address?: string | null
  city: string
  state: string // 2-letter
  zipcode: string
}

// --- Incidents ----------------------------------------------------------------

export type CappeIrWitness = {
  name: string
  contact?: string | null
  statement?: string | null
}

export type CappeIrInvolvedPerson = {
  id: string
  display_name: string
  role: 'reporter' | 'involved' | 'witness' | 'interviewee'
}

export type CappeIrIncident = {
  id: string
  incident_number: string
  title: string
  description: string | null
  incident_type: CappeIrIncidentType
  severity: CappeIrSeverity
  status: CappeIrStatus
  occurred_at: string
  location: string | null
  location_id: string | null
  location_name?: string | null
  location_city?: string | null
  location_state?: string | null
  reported_by_name: string
  reported_by_email: string | null
  reported_at: string
  witnesses: CappeIrWitness[]
  root_cause: string | null
  corrective_actions: string | null
  // No-roster people linked to the incident; populated on single GET only.
  involved_people: CappeIrInvolvedPerson[]
  document_count: number
  created_at: string
  updated_at: string
  resolved_at: string | null
}

export type CappeIrIncidentList = {
  incidents: CappeIrIncident[]
  total: number
}

export type CappeIrIncidentCreate = {
  description: string
  occurred_at: string // ISO string
  reported_by_name: string
  location_id: string // required — one of the account's /ir/locations ids
  title?: string
  incident_type?: CappeIrIncidentType
  severity?: CappeIrSeverity
  location?: string
  reported_by_email?: string
  witnesses?: CappeIrWitness[]
  corrective_actions?: string
}

export type CappeIrIncidentUpdate = {
  title?: string
  description?: string
  incident_type?: CappeIrIncidentType
  severity?: CappeIrSeverity
  status?: CappeIrStatus
  occurred_at?: string
  location?: string
  location_id?: string
  witnesses?: CappeIrWitness[]
  root_cause?: string
  corrective_actions?: string
}

export type CappeIrIncidentFilters = {
  status?: CappeIrStatus
  incident_type?: CappeIrIncidentType
  severity?: CappeIrSeverity
  search?: string
  limit?: number
  offset?: number
}

// --- Corrective actions (CAPA) -------------------------------------------------

export type CappeIrActionStatus = 'open' | 'in_progress' | 'completed' | 'verified' | 'cancelled'
export type CappeIrActionPriority = 'immediate' | 'short_term' | 'long_term'

export const CAPPE_IR_ACTION_STATUSES: CappeIrActionStatus[] = ['open', 'in_progress', 'completed', 'verified', 'cancelled']
export const CAPPE_IR_ACTION_PRIORITIES: CappeIrActionPriority[] = ['immediate', 'short_term', 'long_term']

export type CappeIrCorrectiveAction = {
  id: string
  incident_id: string
  description: string
  action_type: 'corrective' | 'preventive'
  priority: CappeIrActionPriority
  // No-roster owner name (write via `assignee_name`); assigned_to_name is the
  // hydrated roster display name (unused for cappe accounts — no roster).
  assignee_name: string | null
  assigned_to_name: string | null
  due_date: string | null
  status: CappeIrActionStatus
  completed_at: string | null
  overdue: boolean
  created_at: string
  updated_at: string
}

export type CappeIrCorrectiveActionList = {
  actions: CappeIrCorrectiveAction[]
  total: number
}

export type CappeIrCorrectiveActionCreate = {
  description: string
  priority?: CappeIrActionPriority
  assignee_name?: string
  due_date?: string // YYYY-MM-DD
}

export type CappeIrCorrectiveActionUpdate = {
  description?: string
  priority?: CappeIrActionPriority
  assignee_name?: string
  due_date?: string
  status?: CappeIrActionStatus
}

export type CappeIrOpenAction = CappeIrCorrectiveAction & {
  incident_number: string
  incident_title: string
}

export type CappeIrOpenActionsResponse = {
  actions: CappeIrOpenAction[]
  total: number
  overdue_count: number
}

// --- Documents ------------------------------------------------------------------

export type CappeIrDocument = {
  id: string
  incident_id: string
  document_type: CappeIrDocumentType
  filename: string
  mime_type: string | null
  file_size: number | null
  created_at: string
}

export type CappeIrDocumentUploadResponse = {
  document: CappeIrDocument
  message: string
}

// --- Helpers ---------------------------------------------------------------------

/** A 403 from /ir/* means the bridged feature isn't enabled for the account.
 * cappeClient surfaces errors as message-only, so match the gate's detail text. */
export function isIrFeatureDisabledError(err: unknown): boolean {
  return err instanceof Error && err.message.includes('feature is not enabled for this account')
}

function qs(filters: CappeIrIncidentFilters): string {
  const p = new URLSearchParams()
  if (filters.status) p.set('status', filters.status)
  if (filters.incident_type) p.set('incident_type', filters.incident_type)
  if (filters.severity) p.set('severity', filters.severity)
  if (filters.search) p.set('search', filters.search)
  if (filters.limit != null) p.set('limit', String(filters.limit))
  if (filters.offset != null) p.set('offset', String(filters.offset))
  const s = p.toString()
  return s ? `?${s}` : ''
}

// --- API -----------------------------------------------------------------------

export const cappeIr = {
  // Locations
  listLocations: () => cappeApi.get<CappeIrLocation[]>('/ir/locations'),
  createLocation: (input: CappeIrLocationInput) =>
    cappeApi.post<CappeIrLocation>('/ir/locations', input),
  deleteLocation: (locationId: string) =>
    cappeApi.delete<null>(`/ir/locations/${locationId}`),

  // Incidents
  listIncidents: (filters: CappeIrIncidentFilters = {}) =>
    cappeApi.get<CappeIrIncidentList>(`/ir/incidents${qs(filters)}`),
  getIncident: (incidentId: string) =>
    cappeApi.get<CappeIrIncident>(`/ir/incidents/${incidentId}`),
  createIncident: (input: CappeIrIncidentCreate) =>
    cappeApi.post<CappeIrIncident>('/ir/incidents', input),
  updateIncident: (incidentId: string, patch: CappeIrIncidentUpdate) =>
    cappeApi.put<CappeIrIncident>(`/ir/incidents/${incidentId}`, patch),
  deleteIncident: (incidentId: string) =>
    cappeApi.delete<unknown>(`/ir/incidents/${incidentId}`),

  // Corrective actions
  listActions: (incidentId: string) =>
    cappeApi.get<CappeIrCorrectiveActionList>(`/ir/incidents/${incidentId}/corrective-actions`),
  createAction: (incidentId: string, input: CappeIrCorrectiveActionCreate) =>
    cappeApi.post<CappeIrCorrectiveAction>(`/ir/incidents/${incidentId}/corrective-actions`, input),
  updateAction: (actionId: string, patch: CappeIrCorrectiveActionUpdate) =>
    cappeApi.put<CappeIrCorrectiveAction>(`/ir/incidents/corrective-actions/${actionId}`, patch),
  deleteAction: (actionId: string) =>
    cappeApi.delete<null>(`/ir/incidents/corrective-actions/${actionId}`),
  listOpenActions: () =>
    cappeApi.get<CappeIrOpenActionsResponse>('/ir/incidents/corrective-actions/open'),

  // Documents
  listDocuments: (incidentId: string) =>
    cappeApi.get<CappeIrDocument[]>(`/ir/incidents/${incidentId}/documents`),
  uploadDocument: (incidentId: string, file: File, documentType: CappeIrDocumentType = 'other') => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('document_type', documentType)
    return cappeApi.upload<CappeIrDocumentUploadResponse>(`/ir/incidents/${incidentId}/documents`, fd)
  },
  deleteDocument: (incidentId: string, documentId: string) =>
    cappeApi.delete<unknown>(`/ir/incidents/${incidentId}/documents/${documentId}`),
}
