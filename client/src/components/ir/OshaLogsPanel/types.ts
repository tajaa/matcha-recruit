export type LogEntry = {
  case_number: string
  employee_name: string
  job_title: string | null
  date_of_injury: string
  location: string | null
  description: string | null
  classification: string | null
  days_away: number
  days_restricted: number
  injury_type: string | null
  incident_id: string
  is_privacy_case: boolean
  privacy_case_reason: string | null
}

// Confidential privacy-case reference list row (admin/client-only endpoint).
export type PrivacyCaseRow = {
  case_number: string
  real_employee_name: string
  privacy_case_reason: string | null
  classification: string | null
  date_of_injury: string
  incident_id: string
}

export type Summary300A = {
  year: number
  establishment_name: string | null
  establishment_id: string | null
  ein: string | null
  naics: string | null
  address: string | null
  city: string | null
  state: string | null
  zipcode: string | null
  total_cases: number
  total_deaths: number
  total_days_away_cases: number
  total_restricted_cases: number
  total_other_recordable: number
  total_days_away: number
  total_days_restricted: number
  total_injuries: number
  total_skin_disorders: number
  total_respiratory: number
  total_poisonings: number
  total_hearing_loss: number
  total_other_illnesses: number
  average_employees: number | null
  total_hours_worked: number | null
  certified_by: string | null
  certified_title: string | null
  certified_date: string | null
  data_quality_warnings?: string[]
}

export type ItaProblem = {
  location_id: string | null
  establishment_name: string
  missing: string[]
}

export type ItaSubmissionRow = {
  id: string
  year: number
  status: string
  ita_submission_id: string | null
  establishment_count: number
  error_detail: string | null
  submitted_at: string
}

export type ItaCredentialStatus = { configured: boolean; updated_at: string | null }

export type ItaSubmitResponse = {
  status: string
  submission_id: string | null
  establishment_count: number
  error: string | null
}
