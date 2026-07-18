// ── Types (mirror the matrix + scope-registry endpoints) ─────────────────────

export type CategoryEntry = {
  slug: string
  name: string
  group: string
  source: 'base' | 'triggered' | 'specialty' | 'focused'
  triggered_by: string[]
  jurisdiction_count: number
  requirement_count: number
  has_data: boolean
  registry_source?: 'engine' | 'bank'
  engine_codified?: number | null
  engine_to_codify?: number | null
  engine_expected?: number | null
}

export type MatrixResponse = {
  summary: {
    total: number; with_data: number; missing_data: number
    engine_cells?: number; engine_to_codify?: number
  }
  scoped_to: { state: string; city: string | null; city_found: boolean | null } | null
  registry_definitive?: boolean
  categories: CategoryEntry[]
}

export type Specialty = {
  industry_tag: string
  slug: string
  label: string
  category_count: number
}

export type ResolveItem = {
  citation: string
  heading: string | null
  regulation_key: string | null
  disposition: string
  item_id?: string | null
  has_body?: boolean
  source_url?: string | null
}

export type ResolveResult = {
  coordinate: { category_chain: string[]; state_found: boolean; city_found: boolean }
  codified: ResolveItem[]
  uncodified: ResolveItem[]
  counts: {
    applicable: number; codified: number; uncodified: number
    provisional: number; conditional_skipped: number
  }
  unmodeled_coordinates: { kind: string; value: string; note: string }[]
}

// ── Labor scope (jurisdiction-first, industry-agnostic) ──────────────────────

export type RequirementPenalties = {
  enforcing_agency?: string | null
  civil_penalty_min?: number | string | null
  civil_penalty_max?: number | string | null
  per_violation?: boolean | string | null
  annual_cap?: number | string | null
  criminal?: string | null
  summary?: string | null
  grounding?: string | null
}

export type LaborScopeRequirement = {
  title?: string | null
  key_definition_id?: string | null
  current_value?: string | null
  source_url?: string | null
  source_name?: string | null
  jurisdiction_name?: string | null
  jurisdiction_level?: string | null
  last_verified_at?: string | null
  codified_at?: string | null
  codify_source?: string | null
  effective_date?: string | null
  expiration_date?: string | null
  penalties?: RequirementPenalties | null
}

export type JurisdictionScope = { level: string; names: string[] }

export type CodifiedEntry = {
  citation: string; heading: string | null; regulation_key: string | null
  source_url?: string | null; item_id?: string | null; has_body?: boolean
  severity?: string | null; jurisdiction_scope?: JurisdictionScope | null
  requirement?: LaborScopeRequirement | null
}
export type UncodifiedEntry = {
  citation: string; heading: string | null; regulation_key: string | null
  source_url?: string | null; item_id?: string | null; has_body?: boolean
  severity?: string | null; jurisdiction_scope?: JurisdictionScope | null
}

export type LaborScopeLevel = {
  codified: CodifiedEntry[]
  uncodified: UncodifiedEntry[]
  counts: { codified: number; uncodified: number; provisional: number }
}

export type LaborExhaustiveness = {
  basis: 'enumerated' | 'curated' | 'none'
  note: string
  indexes: {
    slug: string; name: string; source_type: string | null
    enumerable: boolean; item_count: number; unclassified_count: number
  }[]
  enumeration?: { indexes: number; enumerated: number; classified: number; unclassified: number }
}

export type LaborScopeResponse = {
  coordinate: { state: string | null; city: string | null; state_found: boolean; city_found: boolean }
  core: {
    items: { category: string; key: string; present: boolean; level: string | null }[]
    present: number; total: number; complete: boolean
  }
  registry: {
    levels: { federal: LaborScopeLevel; state: LaborScopeLevel; city: LaborScopeLevel }
    skipped: { category_specific: number; conditional: number }
  }
  exhaustiveness: { federal: LaborExhaustiveness; state: LaborExhaustiveness; city: LaborExhaustiveness }
}

// Research progress — pulse-dot live header + a real fill bar (completed/total).
export type ResearchState = {
  source: 'gap' | 'queue'
  running: boolean; message: string; completed: number; total: number; error: string | null
}

// Industry-agnostic (core-labor) coverage STATE for this coordinate —
// covered / empty (researched-nothing) / unchecked (never researched). The
// point is to stop rendering never-checked categories as a silent green.
export type GeneralCoverage = {
  summary: { covered: number; empty: number; unchecked: number; total: number }
  categories: { slug: string; name: string; status: 'covered' | 'empty' | 'unchecked' }[]
}

// Statute reader — full regulation text in a right drawer.
export type ItemBody = {
  citation: string; heading: string | null; source_url: string | null
  body_text: string | null; body_source_url: string | null
  body_fetched_at: string | null; index_name: string | null
}
