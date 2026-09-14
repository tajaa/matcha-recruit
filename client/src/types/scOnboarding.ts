export type CompanySize = '1-10' | '11-50' | '51-100' | '101-250' | '251-500' | '501+'

/** Industry is owned by signup (INDUSTRY_OPTIONS) and never re-sent here. */
export type ScCompanySetup = {
  company_size: CompanySize
  naics_code: string
}

export type ScLocationImport = {
  name: string
  address: string
  city: string
  state: string
  zipcode: string
}

export type ScEmployeeImport = {
  email: string
  first_name: string
  last_name: string
  work_state: string
  job_title: string
  department: string
}

export type ScCertificateSetup = {
  name: string
  is_required: boolean
  schedule_blocking: boolean
}

export type ScJobSetup = {
  name: string
  credential_grace_days: number
  certificates: ScCertificateSetup[]
}

export type ScOnboardingSubmission = {
  company: ScCompanySetup
  locations: ScLocationImport[]
  employees: ScEmployeeImport[]
  jobs: ScJobSetup[]
}

export type ScOnboardingStatus = {
  company_name: string
  completed: boolean
  completed_at: string | null
  /** Expected CSV headers, owned by the server's parser. Optional so a blue/green
   *  window where the old backend is still serving does not crash the wizard. */
  csv_columns?: { locations: string[]; employees: string[] }
}
