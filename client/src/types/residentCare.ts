// Resident-care risk asset — safety programs + MVR reviews.

export type ProgramType =
  | 'fall_prevention' | 'infection_control' | 'abuse_prevention'
  | 'emergency_prep' | 'medication_safety' | 'other'
export type ProgramStatus = 'active' | 'inactive'
export type ReviewType = 'hire' | 'annual'
export type MvrStatus = 'clear' | 'flagged' | 'pending'

export interface SafetyProgram {
  id: string
  company_id: string
  program_type: ProgramType
  name: string
  status: ProgramStatus
  last_reviewed_date: string | null
  owner: string | null
  notes: string | null
  created_at: string
}

export interface MvrReview {
  id: string
  company_id: string
  driver_name: string
  employee_id: string | null
  review_type: ReviewType
  review_date: string | null
  status: MvrStatus
  next_due_date: string | null
  notes: string | null
  created_at: string
}

export interface ResidentCareSummary {
  programs: { active: number; total: number; active_types: string[] }
  mvr: { total: number; flagged: number; overdue: number; current: number }
  credentialing: { total: number; expired: number; current_pct: number | null }
}

export const PROGRAM_LABELS: Record<ProgramType, string> = {
  fall_prevention: 'Fall prevention',
  infection_control: 'Infection control',
  abuse_prevention: 'Abuse prevention',
  emergency_prep: 'Emergency preparedness',
  medication_safety: 'Medication safety',
  other: 'Other',
}

export const PROGRAM_TYPES: ProgramType[] = [
  'fall_prevention', 'infection_control', 'abuse_prevention',
  'emergency_prep', 'medication_safety', 'other',
]
