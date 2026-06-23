// Loss-run triangulation / chain-ladder development (gap-analysis #5/#23).

export interface LossPoint {
  maturity: number
  valuation_date: string | null
  paid: number
  reserved: number
  incurred: number
  claim_count: number
  open_count: number
}

export interface LossPeriod {
  period_label: string
  period_start: string | null
  points: LossPoint[]
  latest_maturity: number | null
  latest_incurred: number
  cdf: number
  ultimate: number
  adverse_development: number
}

export interface LossFactor {
  from_maturity: number
  to_maturity: number
  factor: number
  n: number
}

export interface LossLineSummary {
  total_latest_incurred: number
  total_ultimate: number
  total_adverse_development: number
  adverse_pct: number
  periods: number
  valuations: number
  max_maturity: number
}

export interface LossLine {
  line: string
  label: string
  periods: LossPeriod[]
  factors: LossFactor[]
  summary: LossLineSummary
}

export interface LossSnapshot {
  id: string
  line: string
  policy_period_label: string
  policy_period_start: string | null
  valuation_date: string
  claim_count: number
  open_count: number
  paid: number
  reserved: number
  source: string | null
  note: string | null
  created_at?: string
}

export interface LossDevelopment {
  lines: LossLine[]
  has_data: boolean
  subject_kind: string
  subject_id: string
  subject_name: string
  snapshots: LossSnapshot[]
}

// Loss ratio = projected ultimate ÷ paid premium (per line per policy year).
export type LossRatioStatus = 'favorable' | 'adverse' | 'na'

export interface LossRatioRow {
  line: string
  label: string
  period_label: string
  period_start: string | null
  projected_ultimate: number
  paid_premium: number | null
  loss_ratio: number | null
  status: LossRatioStatus
}

export interface LossRatioYear {
  period_label: string
  period_start: string | null
  total_ultimate: number
  total_premium: number | null
  loss_ratio: number | null
  status: LossRatioStatus
}

export interface LossRatioData {
  rows: LossRatioRow[]
  years: LossRatioYear[]
  target: number
  has_data: boolean
  subject_kind: string
  subject_id: string
  subject_name: string
}

export interface LossPremiumBody {
  line: string
  policy_period_label: string
  paid_premium: number | null
}

// Parsed draft from an uploaded loss-run PDF.
export interface LossRunDraftPeriod {
  policy_period_label: string
  policy_period_start: string | null
  claim_count: number
  open_count: number
  paid: number
  reserved: number
}

export interface LossRunDraft {
  valuation_date: string | null
  line: string
  periods: LossRunDraftPeriod[]
  available: boolean
  model?: string
}

export interface LossRunCommit {
  valuation_date: string
  line: string
  source?: string | null
  periods: LossRunDraftPeriod[]
}

export const LOSS_LINES = [
  { key: 'wc', label: "Workers' Comp" },
  { key: 'gl', label: 'General Liability' },
  { key: 'auto', label: 'Commercial Auto' },
]
