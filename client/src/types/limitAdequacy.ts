// Limit-adequacy + contract review (gap-analysis #6/#28).

export type LimitStatus = 'no_coverage' | 'shortfall' | 'directional_low' | 'not_carried' | 'ok'

export interface CarriedLine {
  per_occurrence: number | null
  aggregate: number | null
  retention: number | null
  carrier: string | null
  expiry_date: string | null
  additional_insured: boolean
  waiver_of_subrogation: boolean
  primary_noncontributory: boolean
}

export interface Baseline {
  per_occurrence: number | null
  aggregate: number | null
  basis: string
}

export interface EndorsementGap { key: string; label: string }

export interface ContractSource {
  contract: string | null
  counterparty: string | null
  per_occurrence: number | null
  aggregate: number | null
}

export interface ReviewLine {
  key: string
  label: string
  carried: CarriedLine | null
  contract_required: { per_occurrence: number | null; aggregate: number | null } | null
  contract_sources: ContractSource[]
  baseline: Baseline | null
  status: LimitStatus
  gap: string | null
  endorsement_gaps: EndorsementGap[]
}

export interface ContractRequirement {
  line: string
  per_occurrence: number | null
  aggregate: number | null
  additional_insured: boolean
  waiver_of_subrogation: boolean
  primary_noncontributory: boolean
  note: string | null
}

export interface ContractRecord {
  id: string
  name: string
  counterparty: string | null
  status: string
  ai_available: boolean
  requirements: ContractRequirement[]
  source_filename?: string | null
  created_at?: string
  updated_at?: string
}

export interface LimitReview {
  lines: ReviewLine[]
  summary: {
    contract_shortfalls: number
    baseline_lows: number
    lines_carried: number
    contracts: number
    endorsement_gaps: number
  }
  contracts: ContractRecord[]
  company_id: string
  company_name: string
  headcount: number | null
  industry: string | null
  venue_tier: string | null
}

export interface CoverageRow {
  line: string
  carrier: string | null
  per_occurrence: number | null
  aggregate: number | null
  retention: number | null
  additional_insured: boolean
  waiver_of_subrogation: boolean
  primary_noncontributory: boolean
  effective_date: string | null
  expiry_date: string | null
  note: string | null
  updated_at?: string
}

export interface CoverageCatalogEntry { key: string; label: string; endorsements: boolean }
export interface EndorsementDef { key: string; label: string }

export interface CoverageList {
  lines: CoverageRow[]
  catalog: CoverageCatalogEntry[]
  endorsements: EndorsementDef[]
}

export const LIMIT_STATUS_TONE: Record<string, string> = {
  no_coverage: 'text-red-400 bg-red-500/10 border-red-500/20',
  shortfall: 'text-red-400 bg-red-500/10 border-red-500/20',
  directional_low: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
  not_carried: 'text-zinc-500 bg-white/5 border-white/10',
  ok: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
}

export const LIMIT_STATUS_LABEL: Record<string, string> = {
  no_coverage: 'No coverage',
  shortfall: 'Shortfall',
  directional_low: 'Low',
  not_carried: 'Not carried',
  ok: 'OK',
}

export const ENDORSEMENT_KEYS = ['additional_insured', 'waiver_of_subrogation', 'primary_noncontributory'] as const

/** Format whole-dollar limits as $1M / $1.5M / $500K. */
export function fmtMoney(v: number | null | undefined): string {
  if (v == null) return '—'
  if (v >= 1_000_000) {
    const n = v / 1_000_000
    return n === Math.floor(n) ? `$${n}M` : `$${n.toFixed(1)}M`
  }
  if (v >= 1_000) return `$${Math.round(v / 1_000)}K`
  return `$${v}`
}
