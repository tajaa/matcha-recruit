import { api } from '../../client'
import type { CompanyCredential } from './types'

// ── Certifications & Licenses (per-company, joined to catalog) ──

export function fetchCompanyCertifications(companyId?: string) {
  const qs = companyId ? `?company_id=${encodeURIComponent(companyId)}` : ''
  return api.get<CompanyCredential[]>(`/compliance/certifications${qs}`)
}

export function fetchCompanyLicenses(companyId?: string) {
  const qs = companyId ? `?company_id=${encodeURIComponent(companyId)}` : ''
  return api.get<CompanyCredential[]>(`/compliance/licenses${qs}`)
}
