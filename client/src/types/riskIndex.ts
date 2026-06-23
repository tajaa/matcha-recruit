// Composite risk index — client portal + broker rollup.

export interface RiskComponent {
  key: string
  label: string
  weight: number
  score: number
  detail: string
}

export interface RiskIndex {
  company_id: string
  company_name?: string
  index: number | null
  band: string | null
  components: RiskComponent[]
  top_fixes: string[]
}

export interface RiskIndexPortfolioRow {
  company_id: string
  company_name: string
  industry: string | null
  index: number
  band: string
  components: RiskComponent[]
}

export interface RiskIndexPortfolio {
  summary: {
    client_count: number
    strong: number
    adequate: number
    developing: number
    exposed: number
    avg_index: number
  }
  companies: RiskIndexPortfolioRow[]
}

export const RISK_BAND_TONE: Record<string, string> = {
  strong: 'text-emerald-400',
  adequate: 'text-zinc-200',
  developing: 'text-amber-400',
  exposed: 'text-red-400',
}

// --- Book Risk Curve (broker, exposure-weighted) ---
export type ExposureBasis = 'headcount' | 'premium'

export interface BookRiskClient {
  id: string
  source: 'platform' | 'external'
  name: string
  industry: string | null
  index: number
  band: string
  headcount: number | null
  annual_premium: number | null
}

export interface WeightedBookRisk {
  basis: ExposureBasis
  weighted_mean: number | null
  equal_weight_mean: number | null
  weighted_band: string | null
  total_weight: number
  scored_count: number
  weighted_count: number
  missing_basis_count: number
  band_mix: Record<string, number>
}

export interface BookRiskCurve {
  is_pro: boolean
  clients: BookRiskClient[]
  default_aggregate: WeightedBookRisk
  counts: { platform: number; external: number; missing_headcount: number; missing_premium: number }
}

export interface EplBandZone { key: string; min: number; max: number; label: string; color: string }
// EPL band thresholds (mirror epl_readiness.readiness_band) — for the FE recompute
// + the chart's shaded band zones.
export const EPL_BANDS: EplBandZone[] = [
  { key: 'exposed', min: 0, max: 35, label: 'Exposed', color: '#ef4444' },
  { key: 'developing', min: 35, max: 60, label: 'Developing', color: '#f59e0b' },
  { key: 'adequate', min: 60, max: 80, label: 'Adequate', color: '#a1a1aa' },
  { key: 'strong', min: 80, max: 100, label: 'Strong', color: '#10b981' },
]

// Submission-readiness — data→price completeness loop (folded into the portal).
export interface ReadinessItem {
  key: string
  label: string
  weight: number
  done: boolean
  fix: string
}

export interface SubmissionReadiness {
  score: number
  band: string
  items: ReadinessItem[]
  top_fixes: string[]
  summary: { done: number; total: number }
}

export const READINESS_BAND_TONE: Record<string, string> = {
  ready: 'text-emerald-400',
  developing: 'text-amber-400',
  thin: 'text-red-400',
}

// Venue / nuclear-verdict severity — casualty exposure dimension.
export interface VenueLocation {
  city: string | null
  state: string
  county: string | null
  tier: string
  score: number | null
  source: string | null
  note: string | null
}

export interface VenueExposure {
  locations: VenueLocation[]
  summary: {
    worst_tier: string
    worst_score: number | null
    severe_high_count: number
    rated_locations: number
    total_locations: number
    tier_counts: Record<string, number>
  }
}

export const VENUE_TIER_TONE: Record<string, string> = {
  severe: 'text-red-400', high: 'text-red-400', elevated: 'text-amber-400',
  moderate: 'text-emerald-400', low: 'text-emerald-400', unknown: 'text-zinc-500',
}

// Grounded emerging-exclusion exposure (casualty).
export interface ExclusionItem {
  key: string
  label: string
  lines: string[]
  creep: string
  mitigation: string
  status: string
}

export interface ExclusionGap {
  exclusions: ExclusionItem[]
  summary: { exposed: number; monitor: number; mitigated: number; total: number }
}

export const EXCLUSION_TONE: Record<string, string> = {
  exposed: 'text-red-400', monitor: 'text-amber-400', mitigated: 'text-emerald-400',
}
