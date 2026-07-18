export type ClientSetup = {
  id: string
  company_name: string
  contact_name: string | null
  contact_email: string | null
  status: string
  invite_token: string | null
  invite_expires_at: string | null
  created_at: string
  notes?: string
  locations?: { city: string; state: string; type: string }[]
  onboarding_stage?: 'submitted' | 'under_review' | 'configuring' | 'live'
}

export type LocationEntry = { city: string; state: string; type: string }

export type SetupForm = {
  company_name: string
  contact_name: string
  contact_email: string
  contact_phone: string
  industry: string
  company_size: string
  headcount: string
  invite_immediately: boolean
  locations: LocationEntry[]
  notes: string
  specialties: string
}

export type CsvRow = {
  company_name: string
  contact_name: string
  contact_email: string
  contact_phone: string
  industry: string
  company_size: string
  headcount: string
  notes: string
}
