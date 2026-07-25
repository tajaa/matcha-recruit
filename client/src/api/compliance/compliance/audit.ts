import { api } from '../../client'
import type { ComplianceAuditOverview } from '../../../types/compliance'

// ── Company-wide audit overview (the Audit tab) ──

export function fetchComplianceAudit() {
  return api.get<ComplianceAuditOverview>('/compliance/audit')
}
