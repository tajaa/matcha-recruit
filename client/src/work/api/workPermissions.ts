import { api } from '../../api/client'

export type WorkAccessLevel = 'guest' | 'member' | 'reviewer' | 'operator' | 'admin'

export interface WorkAccess {
  level: WorkAccessLevel
  capabilities: string[]
}

export interface WorkPermission {
  company_id?: string
  user_id: string
  email?: string
  role?: string
  level: Exclude<WorkAccessLevel, 'guest'>
  granted_by?: string | null
  created_at?: string
  updated_at?: string
}

export function listWorkPermissions(companyId?: string) {
  const query = companyId ? `?company_id=${encodeURIComponent(companyId)}` : ''
  return api.get<{ company_id: string; permissions: WorkPermission[] }>(`/matcha-work/permissions${query}`)
}

export function setWorkPermission(userId: string, level: Exclude<WorkAccessLevel, 'guest'>, companyId?: string) {
  const query = companyId ? `?company_id=${encodeURIComponent(companyId)}` : ''
  return api.put<WorkPermission>(`/matcha-work/permissions/${userId}${query}`, { level })
}

export function deleteWorkPermission(userId: string, companyId?: string) {
  const query = companyId ? `?company_id=${encodeURIComponent(companyId)}` : ''
  return api.delete(`/matcha-work/permissions/${userId}${query}`)
}
