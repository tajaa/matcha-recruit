// Commercial property — Statement of Values (tenant).

export type ConstructionType =
  | 'frame' | 'joisted_masonry' | 'non_combustible'
  | 'masonry_non_combustible' | 'modified_fire_resistive' | 'fire_resistive'

export const CONSTRUCTION_LABEL: Record<string, string> = {
  frame: 'Frame',
  joisted_masonry: 'Joisted Masonry',
  non_combustible: 'Non-Combustible',
  masonry_non_combustible: 'Masonry Non-Combustible',
  modified_fire_resistive: 'Modified Fire-Resistive',
  fire_resistive: 'Fire-Resistive',
}

export type PerilTier = 'severe' | 'high' | 'elevated' | 'moderate' | 'low'

export interface PropertyPeril {
  peril: string            // flood / quake / wildfire / wind
  zone: string | null
  score: number | null
  tier: PerilTier | null
  source: string | null
  error: string | null
  fetched_at: string | null
}

export interface PropertyBuilding {
  id: string
  location_id: string | null
  name: string | null
  address: string | null
  city: string | null
  state: string | null
  zipcode: string | null
  county: string | null
  occupancy: string | null
  construction_type: ConstructionType | null
  year_built: number | null
  sq_ft: number | null
  stories: number | null
  roof_year: number | null
  sprinklered: boolean
  protection_class: string | null
  building_value: number | null
  contents_value: number | null
  bi_value: number | null
  replacement_cost: number | null
  insured_value: number | null
  lat: number | null
  lng: number | null
  geocoded_at: string | null
  cat_refreshed_at: string | null
  note: string | null
  // deeper capture (propd01)
  valuation_basis: 'RCV' | 'ACV' | null
  coinsurance_pct: number | null
  ordinance_law: string | null
  bi_months: number | null
  blanket: boolean
  aop_deductible: number | null
  wind_deductible_pct: number | null
  named_storm_deductible_pct: number | null
  quake_deductible_pct: number | null
  roof_type: string | null
  wiring_year: number | null
  central_station_alarm: boolean
  cooking_nfpa96: boolean
  hot_work: boolean
  hazmat: boolean
  policy_detail: Record<string, unknown> | null
  // computed
  cope_grade: string
  cope_score: number
  tiv: number
  itv_ratio: number | null
  perils: PropertyPeril[]
}

export interface PropertyRollup {
  building_count: number
  tiv: number
  values: { building: number; contents: number; bi: number; insured: number; replacement: number }
  avg_cope_score: number | null
  worst_cope_grade: string | null
  itv: { portfolio_ratio: number | null; under_count: number; rated_count: number }
}

export interface PropertyReadinessItem {
  key: string
  label: string
  weight: number
  done: boolean
  fix: string
}

export interface PropertyReadiness {
  score: number
  band: string
  items: PropertyReadinessItem[]
  top_fixes: string[]
  summary: { done: number; total: number }
}

export interface PropertyBuildingExposure {
  aal: number
  worst_pml: number
  coinsurance_shortfall: number
  by_peril: Record<string, { aal: number; pml: number; tier: string }>
}

export interface PropertyExposure {
  total_aal: number
  worst_pml: number
  worst_pml_peril: string | null
  coinsurance_shortfall: number
  by_peril: Record<string, { aal: number; pml: number }>
  buildings: Record<string, PropertyBuildingExposure>
  basis: string
}

export type FixSeverity = 'high' | 'medium' | 'low'

export interface PropertyFix {
  key: string
  label: string
  severity: FixSeverity
  detail: string
  impact?: string
  building_id?: string | null
  building_name?: string | null
}

export interface PropertyPlan {
  fixes: PropertyFix[]
  summary: { total: number; by_severity: Record<string, number>; shown: number }
}

export interface PropertyRiskDriver {
  factor: string
  detail: string
  delta: number
}

export interface PropertyBuildingRisk {
  score: number | null
  grade: string | null
  risk_level: string | null
  worst_cat: string | null
  drivers: PropertyRiskDriver[]
}

export interface PropertyTopRisk {
  building_id: string
  name: string | null
  tiv: number
  score: number
  grade: string
  risk_level: string
  worst_cat: string | null
  drivers: PropertyRiskDriver[]
}

export interface PropertyRisk {
  score: number | null
  grade: string | null
  risk_level: string | null
  by_building: Record<string, PropertyBuildingRisk>
  top_risks: PropertyTopRisk[]
  rated: number
}

export interface PropertySov {
  company_id: string
  buildings: PropertyBuilding[]
  rollup: PropertyRollup
  readiness?: PropertyReadiness
  exposure?: PropertyExposure
  plan?: PropertyPlan
  risk?: PropertyRisk
}

export const RISK_LEVEL_TONE: Record<string, string> = {
  low: 'text-emerald-400', moderate: 'text-zinc-200', elevated: 'text-amber-400', high: 'text-red-400',
}

export const FIX_SEVERITY_TONE: Record<string, string> = {
  high: 'bg-red-500/15 text-red-300', medium: 'bg-amber-500/15 text-amber-300', low: 'bg-zinc-700/40 text-zinc-400',
}

export const READINESS_TONE: Record<string, string> = {
  ready: 'text-emerald-400', developing: 'text-amber-400', thin: 'text-red-400',
}

// create/edit payload
export interface BuildingPayload {
  name: string | null
  address: string | null
  city: string | null
  state: string | null
  zipcode: string | null
  occupancy: string | null
  construction_type: ConstructionType | null
  year_built: number | null
  sq_ft: number | null
  stories: number | null
  roof_year: number | null
  sprinklered: boolean
  protection_class: string | null
  building_value: number | null
  contents_value: number | null
  bi_value: number | null
  replacement_cost: number | null
  insured_value: number | null
  note: string | null
  // deeper capture (propd01)
  valuation_basis?: 'RCV' | 'ACV' | null
  coinsurance_pct?: number | null
  ordinance_law?: string | null
  bi_months?: number | null
  blanket?: boolean
  aop_deductible?: number | null
  wind_deductible_pct?: number | null
  named_storm_deductible_pct?: number | null
  quake_deductible_pct?: number | null
  roof_type?: string | null
  wiring_year?: number | null
  central_station_alarm?: boolean
  cooking_nfpa96?: boolean
  hot_work?: boolean
  hazmat?: boolean
  policy_detail?: Record<string, unknown> | null
}

// SOV ingestion (CSV bulk upload + Gemini parse of an uploaded SOV file).
export interface BulkUploadResult {
  total_rows: number
  created: number
  failed: number
  errors: { row: number; name: string; error: string }[]
  ids: string[]
}

export interface SovParseResult {
  buildings: BuildingPayload[]
  available: boolean
  model: string
}

export const COPE_TONE: Record<string, string> = {
  A: 'text-emerald-400', B: 'text-zinc-200', C: 'text-amber-400', D: 'text-red-400',
}
export const PERIL_TONE: Record<string, string> = {
  severe: 'text-red-400', high: 'text-red-400', elevated: 'text-amber-400',
  moderate: 'text-emerald-400', low: 'text-emerald-400',
}
