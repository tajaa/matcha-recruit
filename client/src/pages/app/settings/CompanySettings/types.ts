export type Tab = 'profile' | 'locations'

export interface CompanyData {
  id: string
  name: string
  industry: string | null
  size: string | null
  logo_url: string | null
  headquarters_state: string | null
  headquarters_city: string | null
  work_arrangement: string | null
  default_employment_type: string | null
  healthcare_specialties: string[] | null
  legal_name: string | null
  ein: string | null
  naics: string | null
  address: string | null
  zip: string | null
  // OSHA 300A "Sign here" defaults — rendered on every 300A PDF cert block.
  executive_name: string | null
  executive_title: string | null
  executive_phone: string | null
}

export type EditableFieldProps = {
  label: string
  value: string | null
  onSave: (value: string) => Promise<void>
  type?: string
}

export type EditableSelectProps = {
  label: string
  value: string | null
  options: { value: string; label: string }[]
  onSave: (value: string) => Promise<void>
}
