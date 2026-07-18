// Shared label + badge-variant maps for the Labor Relations surface.
import type { BadgeVariant } from '../components/ui'
import type {
  CBAStatus, ClauseCategory, GrievanceResolution, GrievanceStatus,
  GrievanceType, StepOutcome, StepStatus,
} from '../api/labor/laborClient'

export const GRIEVANCE_STATUS_VARIANT: Record<GrievanceStatus, BadgeVariant> = {
  draft: 'neutral',
  filed: 'warning',
  in_progress: 'warning',
  advanced: 'warning',
  arbitration: 'danger',
  resolved: 'success',
  settled: 'success',
  withdrawn: 'neutral',
  denied: 'danger',
}

export const GRIEVANCE_STATUS_LABEL: Record<GrievanceStatus, string> = {
  draft: 'Draft',
  filed: 'Filed',
  in_progress: 'In Progress',
  advanced: 'Advanced',
  arbitration: 'Arbitration',
  resolved: 'Resolved',
  settled: 'Settled',
  withdrawn: 'Withdrawn',
  denied: 'Denied',
}

export const CBA_STATUS_VARIANT: Record<CBAStatus, BadgeVariant> = {
  draft: 'neutral',
  active: 'success',
  expired: 'danger',
  superseded: 'neutral',
  in_negotiation: 'warning',
}

export const STEP_STATUS_VARIANT: Record<StepStatus, BadgeVariant> = {
  pending: 'neutral',
  active: 'warning',
  responded: 'success',
  advanced: 'neutral',
  resolved: 'success',
  skipped: 'neutral',
  missed_deadline: 'danger',
}

export const CLAUSE_CATEGORY_LABEL: Record<ClauseCategory, string> = {
  wages: 'Wages',
  hours: 'Hours',
  seniority: 'Seniority',
  grievance_procedure: 'Grievance Procedure',
  discipline: 'Discipline',
  just_cause: 'Just Cause',
  overtime: 'Overtime',
  benefits: 'Benefits',
  union_security: 'Union Security',
  management_rights: 'Management Rights',
  health_safety: 'Health & Safety',
  layoff_recall: 'Layoff / Recall',
  holidays_leave: 'Holidays / Leave',
  other: 'Other',
}

export const GRIEVANCE_TYPE_OPTIONS: { value: GrievanceType; label: string }[] = [
  { value: 'discipline', label: 'Discipline' },
  { value: 'discharge', label: 'Discharge' },
  { value: 'contract_interpretation', label: 'Contract Interpretation' },
  { value: 'pay_wages', label: 'Pay / Wages' },
  { value: 'seniority', label: 'Seniority' },
  { value: 'overtime', label: 'Overtime' },
  { value: 'working_conditions', label: 'Working Conditions' },
  { value: 'health_safety', label: 'Health & Safety' },
  { value: 'management_rights', label: 'Management Rights' },
  { value: 'past_practice', label: 'Past Practice' },
  { value: 'other', label: 'Other' },
]

export const RESOLUTION_OPTIONS: { value: GrievanceResolution; label: string }[] = [
  { value: 'granted', label: 'Granted' },
  { value: 'partially_granted', label: 'Partially Granted' },
  { value: 'denied', label: 'Denied' },
  { value: 'settled', label: 'Settled' },
  { value: 'withdrawn', label: 'Withdrawn' },
  { value: 'arbitrated_win', label: 'Arbitrated — Win' },
  { value: 'arbitrated_loss', label: 'Arbitrated — Loss' },
]

export const STEP_OUTCOME_OPTIONS: { value: StepOutcome; label: string }[] = [
  { value: 'granted', label: 'Granted' },
  { value: 'partially_granted', label: 'Partially Granted' },
  { value: 'denied', label: 'Denied' },
  { value: 'advanced', label: 'No resolution (advance separately)' },
]

export const CLAUSE_CATEGORY_OPTIONS: { value: ClauseCategory; label: string }[] =
  (Object.keys(CLAUSE_CATEGORY_LABEL) as ClauseCategory[]).map((k) => ({
    value: k, label: CLAUSE_CATEGORY_LABEL[k],
  }))

export function personName(
  e: { first_name?: string | null; last_name?: string | null } | null | undefined,
  fallback = '',
): string {
  if (!e) return fallback
  const n = [e.first_name || '', e.last_name || ''].join(' ').trim()
  return n || fallback
}
