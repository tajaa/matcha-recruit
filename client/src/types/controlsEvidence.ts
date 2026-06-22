// Controls-evidence register — universal proof-of-controls (WTW p.85).

export type ControlStatus = 'strong' | 'partial' | 'gap' | 'na'

export interface ControlEntry {
  key: string
  label: string
  source: string
  status: ControlStatus
  override_status: ControlStatus | null
  score: number | null
  metric: string | null
  detail: string | null
  note: string | null
  verified: boolean
  verified_at: string | null
}

export interface ControlsSummary {
  total: number
  strong: number
  partial: number
  gap: number
  na: number
  verified: number
}

export interface ControlsRegister {
  company_id: string
  company_name: string
  controls: ControlEntry[]
  summary: ControlsSummary
}
