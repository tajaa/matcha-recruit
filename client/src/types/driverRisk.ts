// Driver-risk / MVR (gap-analysis #15).

export type DriverTier = 'clean' | 'marginal' | 'high_risk'
export type LicenseStatus = 'valid' | 'suspended' | 'expired' | 'unknown'
export type ReviewType = 'hire' | 'annual' | 'post_incident' | 'periodic'
export type MvrStatus = 'clear' | 'flagged' | 'pending'

export interface DriverRow {
  id: string
  driver_name: string
  employee_id: string | null
  review_type: ReviewType
  review_date: string | null
  status: MvrStatus
  next_due_date: string | null
  notes: string | null
  violation_count: number
  accident_count: number
  major_violation: boolean
  license_status: LicenseStatus
  overdue: boolean
  tier: DriverTier
  points: number
}

export interface FleetSummary {
  total_drivers: number
  clean: number
  marginal: number
  high_risk: number
  overdue_reviews: number
  clean_pct: number
  grade: string
}

export interface Fleet {
  company_id: string
  company_name: string
  drivers: DriverRow[]
  summary: FleetSummary
}

export interface DriverPayload {
  driver_name?: string
  review_type?: ReviewType
  review_date?: string | null
  status?: MvrStatus
  next_due_date?: string | null
  notes?: string | null
  violation_count?: number
  accident_count?: number
  major_violation?: boolean
  license_status?: LicenseStatus
}

export const TIER_TONE: Record<DriverTier, string> = {
  clean: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  marginal: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
  high_risk: 'text-red-400 bg-red-500/10 border-red-500/20',
}
export const TIER_LABEL: Record<DriverTier, string> = {
  clean: 'Clean', marginal: 'Marginal', high_risk: 'High risk',
}
export const GRADE_TONE: Record<string, string> = {
  A: 'text-emerald-400', B: 'text-emerald-400', C: 'text-amber-400', D: 'text-red-400', 'n/a': 'text-zinc-500',
}
