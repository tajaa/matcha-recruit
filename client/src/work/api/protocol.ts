import { api } from '../../api/client'

export interface EmsProtocol {
  notify_emails: string[]
  notify_all_admins: boolean
  incident_definition: string
  culture_notes: string
  corrective_actions: string
  updated_at: string | null
}

export function getProtocol() {
  return api.get<EmsProtocol>('/ems/protocol')
}

export function updateProtocol(body: Omit<EmsProtocol, 'updated_at'>) {
  return api.put<EmsProtocol>('/ems/protocol', body)
}
