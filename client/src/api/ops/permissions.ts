import { api } from '../client'

export type OpsAccessLevel = 'guest' | 'member' | 'reviewer' | 'operator' | 'admin'

export type OpsPermissionGrant = {
  user_id: string
  level: string
  granted_by: string | null
  name: string
  email: string
}

export type OpsSelfAccess = {
  level: OpsAccessLevel
  capabilities: string[]
  source: string
  can_manage: boolean
}

export function getMyOpsAccess() {
  return api.get<OpsSelfAccess>('/ops/permissions/me')
}

export function listOpsPermissions() {
  return api.get<OpsPermissionGrant[]>('/ops/permissions')
}

export function upsertOpsPermission(userId: string, level: OpsAccessLevel) {
  return api.put<OpsPermissionGrant>(`/ops/permissions/${userId}`, { level })
}

export function revokeOpsPermission(userId: string) {
  return api.delete<{ ok: boolean }>(`/ops/permissions/${userId}`)
}
