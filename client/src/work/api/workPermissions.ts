import { api } from '../../api/client'

export type WorkAccessLevel = 'guest' | 'member' | 'reviewer' | 'operator' | 'admin'

export interface WorkAccess {
  level: WorkAccessLevel
  capabilities: string[]
  source?: string
}

export interface WorkPermissionRosterEntry {
  user_id: string
  email: string
  name: string | null
  role: string
  avatar_url: string | null
  eligible_via: string[]
  explicit_level: Exclude<WorkAccessLevel, 'guest'> | null
  effective_level: WorkAccessLevel
  effective_source: string
  capabilities: string[]
  granted_by: string | null
  created_at: string | null
  updated_at: string | null
  immutable: boolean
}

export interface WorkPermissionMutation {
  company_id: string
  user_id: string
  level: Exclude<WorkAccessLevel, 'guest'>
  granted_by: string | null
  created_at: string
  updated_at: string
}

export function listWorkPermissions(companyId?: string) {
  const query = companyId ? `?company_id=${encodeURIComponent(companyId)}` : ''
  return api.get<{ company_id: string; company_name: string | null; permissions: WorkPermissionRosterEntry[] }>(`/matcha-work/permissions${query}`)
}

export function setWorkPermission(userId: string, level: Exclude<WorkAccessLevel, 'guest'>, companyId?: string) {
  const query = companyId ? `?company_id=${encodeURIComponent(companyId)}` : ''
  return api.put<WorkPermissionMutation>(`/matcha-work/permissions/${userId}${query}`, { level })
}

export function deleteWorkPermission(userId: string, companyId?: string) {
  const query = companyId ? `?company_id=${encodeURIComponent(companyId)}` : ''
  return api.delete(`/matcha-work/permissions/${userId}${query}`)
}
