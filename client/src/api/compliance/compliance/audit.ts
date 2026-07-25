import { api } from '../../client'
import type { ComplianceAuditOverview } from '../../../types/compliance'

// ── Company-wide audit overview (the Audit tab) ──

export function fetchComplianceAudit(companyId?: string) {
  const qs = companyId ? `?company_id=${encodeURIComponent(companyId)}` : ''
  return api.get<ComplianceAuditOverview>(`/compliance/audit${qs}`)
}
