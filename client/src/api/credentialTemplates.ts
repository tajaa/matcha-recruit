import { api } from './client'
import type {
  CredentialType,
  RoleCategory,
  CredentialRequirementTemplate,
  CredentialResearchLog,
  EmployeeCredentialRequirement,
  PreviewResult,
} from '../types/credential-templates'

// ── Credential Types ──

export function fetchCredentialTypes() {
  return api.get<CredentialType[]>('/credential-templates/types')
}

// ── Role Categories ──

export function fetchRoleCategories() {
  return api.get<RoleCategory[]>('/credential-templates/role-categories')
}

// ── Templates ──

export function fetchTemplates(params?: {
  state?: string
  role_category_id?: string
  include_pending?: boolean
}) {
  const qs = new URLSearchParams()
  if (params?.state) qs.set('state', params.state)
  if (params?.role_category_id) qs.set('role_category_id', params.role_category_id)
  if (params?.include_pending !== undefined) qs.set('include_pending', String(params.include_pending))
  const q = qs.toString()
  return api.get<CredentialRequirementTemplate[]>(`/credential-templates/templates${q ? `?${q}` : ''}`)
}

export function createTemplate(data: {
  state: string
  city?: string
  role_category_id: string
  credential_type_id: string
  is_required?: boolean
  due_days?: number
  priority?: string
  notes?: string
}) {
  return api.post<CredentialRequirementTemplate>('/credential-templates/templates', data)
}

export function updateTemplate(id: string, data: {
  is_required?: boolean
  due_days?: number
  priority?: string
  notes?: string
}) {
  return api.put<CredentialRequirementTemplate>(`/credential-templates/templates/${id}`, data)
}

export function deleteTemplate(id: string) {
  return api.delete(`/credential-templates/templates/${id}`)
}

export function approveTemplate(id: string) {
  return api.post(`/credential-templates/templates/${id}/approve`)
}

export function rejectTemplate(id: string) {
  return api.post(`/credential-templates/templates/${id}/reject`)
}

export function bulkApproveTemplates(researchId: string) {
  return api.post(`/credential-templates/bulk-approve?research_id=${researchId}`)
}

// ── Research ──

export function triggerResearch(data: {
  state: string
  city?: string
  role_category_id: string
}) {
  return api.post<{ template_count: number; requirements: unknown[] }>('/credential-templates/research', data)
}

export function fetchResearchLogs(state?: string) {
  const qs = state ? `?state=${state}` : ''
  return api.get<CredentialResearchLog[]>(`/credential-templates/research${qs}`)
}

export function fetchResearchLog(id: string) {
  return api.get<CredentialResearchLog>(`/credential-templates/research/${id}`)
}

// ── Preview ──

export function previewRequirements(params: {
  state: string
  job_title: string
  city?: string
}) {
  const qs = new URLSearchParams({ state: params.state, job_title: params.job_title })
  if (params.city) qs.set('city', params.city)
  return api.get<PreviewResult>(`/credential-templates/preview?${qs}`)
}

// ── Employee Requirements ──

export function fetchEmployeeRequirements(employeeId: string) {
  return api.get<EmployeeCredentialRequirement[]>(
    `/credential-templates/employees/${employeeId}/requirements`
  )
}

export function waiveRequirement(employeeId: string, requirementId: string, reason: string) {
  return api.post(
    `/credential-templates/employees/${employeeId}/requirements/${requirementId}/waive`,
    { reason }
  )
}
