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

export interface PropertySov {
  company_id: string
  buildings: PropertyBuilding[]
  rollup: PropertyRollup
  readiness?: PropertyReadiness
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
}

export const COPE_TONE: Record<string, string> = {
  A: 'text-emerald-400', B: 'text-zinc-200', C: 'text-amber-400', D: 'text-red-400',
}
export const PERIL_TONE: Record<string, string> = {
  severe: 'text-red-400', high: 'text-red-400', elevated: 'text-amber-400',
  moderate: 'text-emerald-400', low: 'text-emerald-400',
}
