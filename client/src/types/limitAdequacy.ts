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
  quote?: string | null
  page?: number | null
}

export type ContractType = 'lease' | 'construction' | 'vendor_service' | 'msa' | 'other'
export type IndemnityForm = 'broad' | 'intermediate' | 'limited' | 'unclear'
export type IndemnityDirection = 'we_indemnify_them' | 'they_indemnify_us' | 'mutual' | 'unclear'
export type IndemnityVerdict = 'likely_void_by_statute' | 'uninsurable_exposure' | 'insurable' | 'review'

export interface Indemnity {
  present: boolean
  form: IndemnityForm
  direction: IndemnityDirection
  covers_sole_negligence: boolean
  defense_obligation: boolean
  quote: string | null
  page: number | null
}

export interface RiskTransfer {
  indemnity: Indemnity
}

/** The engine's ruling on one contract's indemnity clause. */
export interface IndemnityAssessment {
  verdict: IndemnityVerdict
  basis: string
  statute: string | null
  controlling_state: string | null
}

export interface ContractRecord {
  id: string
  name: string
  counterparty: string | null
  status: string
  ai_available: boolean
  requirements: ContractRequirement[]
  source_filename?: string | null
  contract_type?: ContractType | null
  governing_state?: string | null
  project_state?: string | null
  risk_transfer?: RiskTransfer | null
  confirmed_at?: string | null
  /** Present on `build_review` rows; absent on bare CRUD responses. */
  indemnity?: IndemnityAssessment
  provisional?: boolean
  has_source?: boolean
  created_at?: string
  updated_at?: string
}

/** Per-contract, pre-signature review — compliant / exposed / actions. */
export interface ContractReview {
  contract: {
    id: string
    name: string
    counterparty: string | null
    contract_type: ContractType | null
    governing_state: string | null
    project_state: string | null
    status: string
    confirmed_at: string | null
    has_source: boolean
  }
  lines: ReviewLine[]
  indemnity: IndemnityAssessment
  risk_transfer: Partial<RiskTransfer>
  summary: {
    exposed: number
    compliant: number
    endorsement_gaps: number
    indemnity_verdict: IndemnityVerdict
  }
  actions: string[]
  provisional: boolean
  disclaimer: string
  company_name?: string
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
  disclaimer?: string
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

export const VERDICT_TONE: Record<IndemnityVerdict, string> = {
  likely_void_by_statute: 'text-red-400 bg-red-500/10 border-red-500/20',
  uninsurable_exposure: 'text-red-400 bg-red-500/10 border-red-500/20',
  insurable: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  review: 'text-zinc-400 bg-white/5 border-white/10',
}

export const VERDICT_LABEL: Record<IndemnityVerdict, string> = {
  likely_void_by_statute: 'Likely void by statute',
  uninsurable_exposure: 'Uninsurable exposure',
  insurable: 'Insurable',
  review: 'Needs review',
}

export const CONTRACT_TYPE_LABEL: Record<ContractType, string> = {
  lease: 'Lease',
  construction: 'Construction',
  vendor_service: 'Vendor / service',
  msa: 'Master service agreement',
  other: 'Other',
}

export const INDEMNITY_FORM_LABEL: Record<IndemnityForm, string> = {
  broad: 'Broad — covers their sole negligence',
  intermediate: 'Intermediate — covers their partial negligence',
  limited: 'Limited — our negligence only',
  unclear: 'Unclear',
}

export const INDEMNITY_DIRECTION_LABEL: Record<IndemnityDirection, string> = {
  we_indemnify_them: 'We indemnify them',
  they_indemnify_us: 'They indemnify us',
  mutual: 'Mutual',
  unclear: 'Unclear',
}

export const EMPTY_INDEMNITY: Indemnity = {
  present: false,
  form: 'unclear',
  direction: 'unclear',
  covers_sole_negligence: false,
  defense_obligation: false,
  quote: null,
  page: null,
}

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
