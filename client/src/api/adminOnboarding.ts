/**
 * Typed wrappers for the master-admin onboarding wizard backend.
 *
 * Mirrors the 10 endpoints exposed at /api/admin/onboarding/*. Each
 * function returns the same shape the backend Pydantic models emit
 * (see server/app/core/models/admin_onboarding.py).
 */

import { api } from './client'

export type OnboardingStep =
  | 'basics'
  | 'size'
  | 'locations'
  | 'scope'
  | 'gaps'
  | 'review'
  | 'done'

export type OnboardingStatus = 'in_progress' | 'finalized' | 'abandoned'

export type BasicsPayload = {
  business_name: string
  industry: string
  specialty?: string | null
  description?: string | null
  owner_email: string
  owner_name?: string | null
  entity_type?: string | null
}

export type SizePayload = {
  full_time: number
  part_time: number
  contractor: number
  unknown: number
  source: 'csv' | 'hris' | 'manual' | 'skipped'
  hris_provider?: string | null
}

export type LocationInput = {
  name?: string | null
  address?: string | null
  city?: string | null
  state?: string | null
  county?: string | null
  zipcode?: string | null
  facility_attributes?: Record<string, unknown>
}

export type AIScopeCategory = {
  category_slug: string
  scope: 'federal' | 'state' | 'county' | 'city'
  reason?: string | null
}

export type AIScopeCertification = {
  slug: string
  name: string
  issuing_authority?: string | null
  scope_level: 'federal' | 'state' | 'specialty'
  renewal_period_months?: number | null
}

export type AIScopeLicense = AIScopeCertification

export type AIScopeJurisdiction = {
  state?: string | null
  county?: string | null
  city?: string | null
}

export type AIScopePolicy = {
  slug: string
  name: string
  scope_level: 'federal' | 'state' | 'county' | 'city' | 'specialty'
  reason?: string | null
}

export type AIScopeCredential = {
  slug: string
  name: string
  issuing_authority?: string | null
  applies_to_role?: string | null
  scope_level: 'federal' | 'state' | 'specialty'
  renewal_period_months?: number | null
  reason?: string | null
}

export type AIScope = {
  naics_sector?: string | null
  compliance_categories: AIScopeCategory[]
  required_certifications: AIScopeCertification[]
  required_licenses: AIScopeLicense[]
  required_policies: AIScopePolicy[]
  required_credentials: AIScopeCredential[]
  applicable_jurisdictions: AIScopeJurisdiction[]
}

export type ResolvedScopeExisting = {
  requirement_id: string
  category_slug: string
  canonical_key?: string | null
  title?: string | null
  scope_level: string
  location_id?: string | null
}

export type ResolvedScopeMissing = {
  category_slug: string
  scope_level: string
  state?: string | null
  county?: string | null
  city?: string | null
  reason?: string | null
}

export type ResolvedScopeAmbiguous = {
  category_slug: string
  candidates: Array<Record<string, unknown>>
  why?: string | null
}

export type ResolvedScope = {
  existing: ResolvedScopeExisting[]
  missing: ResolvedScopeMissing[]
  ambiguous: ResolvedScopeAmbiguous[]
}

export type OnboardingSessionSummary = {
  id: string
  schema_version: number
  step: OnboardingStep
  status: OnboardingStatus
  business_name?: string | null
  industry?: string | null
  company_id?: string | null
  owner_email?: string | null
  created_by: string
  created_at: string
  updated_at: string
}

export type OnboardingSessionDetail = {
  id: string
  schema_version: number
  step: OnboardingStep
  status: OnboardingStatus
  created_by: string
  company_id?: string | null
  owner_email?: string | null
  owner_user_id?: string | null
  invite_token?: string | null
  idempotency_key?: string | null
  basics: Partial<BasicsPayload>
  size: Partial<SizePayload>
  locations: LocationInput[]
  ai_scope?: AIScope | null
  resolved_scope?: ResolvedScope | null
  gap_analysis?: GapAnalysisDossier | null
  created_at: string
  updated_at: string
}

export type CreateCompanyResponse = {
  session_id: string
  company_id: string
  company_wide_location_id: string
}

export type ExpandScopeResponse = {
  session_id: string
  ai_scope: AIScope
}

export type ResolveScopeResponse = {
  session_id: string
  resolved_scope: ResolvedScope
}

export type DispatchResearchResponse = {
  session_id: string
  dispatched: string[]
  skipped: string[]
}

export type SuggestedCategory = {
  category_slug: string
  scope: 'federal' | 'state' | 'county' | 'city'
  reason?: string | null
}

export type SuggestedCertification = {
  slug: string
  name: string
  reason?: string | null
}

export type SuggestedLicense = SuggestedCertification

export type SuggestedJurisdiction = {
  state?: string | null
  county?: string | null
  city?: string | null
  reason?: string | null
}

export type GapCheckResult = {
  suggested_compliance_categories: SuggestedCategory[]
  suggested_certifications: SuggestedCertification[]
  suggested_licenses: SuggestedLicense[]
  suggested_jurisdictions: SuggestedJurisdiction[]
  summary?: string | null
}

export type GapCheckResponse = {
  session_id: string
  gap_check: GapCheckResult
}

export type FinalizeResponse = {
  session_id: string
  company_id: string
  invite_token?: string | null
  scope_rows_written: number
  certifications_written: number
  licenses_written: number
}

export type EnrichRosterResponse = {
  session_id: string
  company_id: string
  employee_roles: string[]
  new_jurisdictions: Array<{ city?: string | null; state: string }>
  locations_filled: number
  scope_rows_written: number
  covered_count: number
  missing_count: number
  resolved_scope: ResolvedScope
}

export type GapAnalysisDossier = {
  generated_at?: string | null
  session_id?: string | null
  status?: string | null
  company: {
    name?: string | null
    industry?: string | null
    specialty?: string | null
    description?: string | null
    entity_type?: string | null
    owner_name?: string | null
    owner_email?: string | null
  }
  headcount: Record<string, unknown>
  locations: Array<Record<string, unknown>>
  scope: {
    naics_sector?: string | null
    compliance_categories?: AIScopeCategory[]
    required_certifications?: AIScopeCertification[]
    required_licenses?: AIScopeLicense[]
    required_policies?: AIScopePolicy[]
    required_credentials?: AIScopeCredential[]
    applicable_jurisdictions?: AIScopeJurisdiction[]
  }
  coverage: {
    covered: Array<Record<string, unknown>>
    gaps: ResolvedScopeMissing[]
    ambiguous: ResolvedScopeAmbiguous[]
  }
  ai_suggestions: Partial<GapCheckResult>
  counts: {
    covered: number
    gaps: number
    ambiguous: number
    certifications: number
    licenses: number
    policies: number
    credentials: number
    suggestions: number
    coverage_pct?: number
    // Engine overlay (additive). 'engine' when the scope-registry definitively
    // classifies every one of the company's coordinates; 'engine_partial' when
    // every coordinate has an engine verdict but at least one rests on a
    // partially-classified index (the keys are a floor, not the whole scope);
    // else 'bank'.
    coverage_source?: 'engine' | 'engine_partial' | 'bank'
    engine_coverage_pct?: number
    engine_covered?: number
    engine_gaps?: number
  }
}

// Scope-registry verdict for the company (present when the dashboard could run
// the engine overlay; null on failure). Additive — the dossier's bank arrays
// remain the actionable worklist.
export type GapEngineCoverage = {
  coverage_source: 'engine' | 'engine_partial' | 'bank'
  coverage_pct: number
  counts: {
    locations: number
    locations_failed: number
    codified: number
    uncodified: number
    provisional: number
  }
  gate: { total: number; engine: number; fallback: number }
  degraded: boolean
}

// Drift signals computed cheaply on the persistent dashboard — how much the
// company has changed since the last (Gemini) analysis ran.
export type GapDrift = {
  last_analyzed_at?: string | null
  new_locations: number
  new_jurisdictions: number
}

// GET /companies/{id}/fit-map — what a business HAS vs what it NEEDS, measured
// against the curated statutory checklist (compliance_evals.industry_keysets),
// NOT against a Gemini scope run. Deliberately a second opinion alongside the
// dossier below: this one's "missing" means "the law expects this of a business
// like yours", never "the model thought of it this time".
export type FitReason =
  | 'no_jurisdiction'       // location never resolved to a place; fix onboarding first
  | 'covered_by_stricter'   // in their chain, filtered on purpose (preemption) — not a gap
  | 'stale_projection'      // written since their last sync; run a compliance check
  | 'staged'                // in their chain but status='pending'; approve it
  | 'researched_elsewhere'  // exists for other jurisdictions; research here / re-parent
  | 'never_researched'      // nowhere in the catalog; research it

// `requirement_ids` / `location_ids` are the handles the FIX needs — present
// only on the reason that can use them (staged -> approve those rows,
// stale_projection -> re-check those locations). Everything else is researched
// via `research_targets` on the response.
export type FitMissing = {
  category: string
  regulation_key: string
  reason: FitReason
  requirement_ids?: string[]
  location_ids?: string[]
}

export type FitResearchTarget = { location_id: string; state: string | null; city: string | null }

// A withheld row. `catalog_id` is the jurisdiction_requirements row — what
// codification acts on; `id` is the per-location projection row. Seeding the
// codify chain with `id` would 404 on a row that plainly exists. Deduped
// server-side to the catalog: one row projected to five locations is one thing
// to codify, not five.
export type FitGatedRow = {
  id: string | null
  catalog_id: string
  category: string
  regulation_key: string | null
  title: string | null
  jurisdiction_name: string | null
  jurisdiction_level: string | null
  statute_citation: string | null
  // The codify modal scrapes a citation guess out of these to pre-fill its box
  // (utils.extractCitation). Without them the admin retypes every citation from
  // scratch.
  description: string | null
  current_value: string | null
  source_url: string | null
  source_name: string | null
  // A confirmed classification already covers this row's key, so reconcile can
  // codify it with no typing. False = no statute in the registry to bind to yet.
  auto_reconcilable: boolean
}

export type FitCounts = {
  visible: number          // projected + codified — what the tenant sees today
  gated: number            // projected, uncodified — tenant is waiting on us
  missing: number          // every expected key off the tab (incl. benign)
  gaps: number             // the subset that is actually somebody's problem
  // Of the withheld rows, how many ONE reconcile click releases. The rest need
  // a statute ingested into the registry (or a citation typed by hand) — a
  // different job, so the tile must not fold them into one number.
  codifiable_now: number
  covered_by_stricter: number
  beyond_core: number      // projected beyond the checklist — breadth, not excess
  expected: number
  projected: number
}

export type FitLocation = {
  location_id: string
  city: string | null
  state: string | null
  // False = the location has no jurisdiction_id, so it has no chain and nothing
  // can ever project to it. Every location is listed, including ones with zero
  // projected rows — those are the ones most worth seeing.
  has_jurisdiction: boolean
  counts: FitCounts
  missing: FitMissing[]
}

export type FitMapResponse = {
  company_name: string
  company_id: string
  industry: string | null
  // 'core:healthcare' | 'labor_floor_only' — provenance, so a floor-only check
  // is never presented as an industry verdict.
  keyset: string
  keyset_note: string | null
  counts: FitCounts
  missing: FitMissing[]
  // The withheld rows themselves, deduped to the catalog — what the codify
  // chain walks. counts.gated is per-projection and will be larger.
  gated: FitGatedRow[]
  // Locations that resolved to a jurisdiction — where a "research this" action
  // aims. An unresolved location isn't a target: there's no chain to research.
  research_targets: FitResearchTarget[]
  locations: FitLocation[]
}

// Persistent per-company gap dashboard payload. status='never_run' when the
// company has no analysis yet (UI shows a "Run first analysis" empty state).
export type GapDashboardResponse = {
  status: 'ok' | 'never_run'
  company: { id: string; name?: string | null }
  session_id?: string | null
  dossier: GapAnalysisDossier | null
  drift: GapDrift | null
  complexity?: ComplexityScore | null
  engine?: GapEngineCoverage | null
  baseline?: BaselineReadiness[] | null
}

// Base-layer labor readiness (federal + each state the company inherits), scored
// against the enumerated master-list by the `baseline` eval suite.
export type BaselineReadiness = {
  jurisdiction_id: string
  label: string
  level: string
  score: number | null
  present?: number | null
  expected?: number | null
  missing?: number | null
}

// Deterministic compliance-complexity score (0–100) + explainable breakdown.
export type ComplexityScore = {
  score: number
  band: string // Low | Moderate | High | Severe
  breakdown: {
    domain: number
    breadth: number
    scale: number
    load: number
    drivers: {
      industry?: string | null
      states: number
      jurisdictions: number
      headcount: number
      category_count: number
      requirement_count: number
    }
  }
}

// One company row on the gap-analysis landing dashboard (persisted counts +
// cheap drift + complexity). Sorted needs-attention-first server-side.
export type GapOverviewRow = {
  company_id: string
  company_name?: string | null
  company_status?: string | null
  session_status: OnboardingStatus
  covered: number
  gaps: number
  ambiguous: number
  coverage_pct: number
  complexity: number
  complexity_band: string
  last_analyzed_at?: string | null
  new_locations: number
}

// Rich detail for a covered requirement (drill-in), resolved from the shared bank.
export type GapRequirementDetail = {
  id: string
  category?: string | null
  jurisdiction_level?: string | null
  jurisdiction_name?: string | null
  title?: string | null
  description?: string | null
  current_value?: string | null
  rate_type?: string | null
  source_url?: string | null
  source_name?: string | null
  effective_date?: string | null
  expiration_date?: string | null
  requires_written_policy?: boolean | null
  implementation_steps?: string[] | null
}

const BASE = '/admin/onboarding'

// Absolute URL for the SSE enrichment stream — consumed via fetch + ReadableStream
// (not EventSource) so the Authorization header can be attached. Mirrors
// getComplianceCheckUrl in api/compliance.ts.
export function getEnrichStreamUrl(companyId: string): string {
  const base = import.meta.env.VITE_API_URL || '/api'
  return `${base}/admin/onboarding/enrich/${companyId}/stream`
}

// SSE selective gap-fill — researches only the chosen (jurisdiction, category)
// items. POST with a JSON body, consumed via fetch + ReadableStream.
export function getResearchGapsUrl(companyId: string): string {
  const base = import.meta.env.VITE_API_URL || '/api'
  return `${base}/admin/onboarding/research-gaps/${companyId}/stream`
}

/** Per-location compliance re-check. Answers with SSE, not JSON — the stream IS
 *  the work (the server projects as it yields), so callers must fetch+drain it
 *  rather than go through `api.post`, which would choke parsing `data: {...}`. */
export function getLocationCheckUrl(locationId: string, companyId: string): string {
  const base = import.meta.env.VITE_API_URL || '/api'
  return `${base}/compliance/locations/${locationId}/check?company_id=${companyId}`
}

export const adminOnboarding = {
  specialties: () =>
    api.get<Record<string, string[]>>(`${BASE}/specialties`),

  listSessions: (status?: OnboardingStatus) =>
    api.get<OnboardingSessionSummary[]>(
      status ? `${BASE}/sessions?status_filter=${status}` : `${BASE}/sessions`,
    ),

  getSession: (id: string) =>
    api.get<OnboardingSessionDetail>(`${BASE}/sessions/${id}`),

  createSession: (idempotency_key: string) =>
    api.post<OnboardingSessionDetail>(`${BASE}/sessions`, { idempotency_key }),

  patchSession: (
    id: string,
    body: {
      step?: OnboardingStep
      basics?: BasicsPayload
      size?: SizePayload
      locations?: { locations: LocationInput[] }
    },
  ) =>
    api.patch<OnboardingSessionDetail>(`${BASE}/sessions/${id}`, body),

  createCompany: (id: string) =>
    api.post<CreateCompanyResponse>(`${BASE}/sessions/${id}/create-company`),

  // Employee-sync enrichment for an EXISTING company: pulls the live roster's
  // work locations + roles, fills new jurisdictions, re-runs the scope engine,
  // and returns the per-company enrichment session id.
  enrichFromRoster: (companyId: string) =>
    api.post<EnrichRosterResponse>(`${BASE}/enrich/${companyId}`),

  // Persistent per-company gap dashboard — cheap live read (re-resolves the
  // persisted scope against the current bank; no Gemini). Re-run = enrich stream.
  getGapDashboard: (companyId: string) =>
    api.get<GapDashboardResponse>(`${BASE}/companies/${companyId}/gap-dashboard`),

  getFitMap: (companyId: string) =>
    api.get<FitMapResponse>(`${BASE}/companies/${companyId}/fit-map`),

  getRequirementDetail: (companyId: string, requirementId: string) =>
    api.get<GapRequirementDetail>(
      `${BASE}/companies/${companyId}/requirements/${requirementId}`,
    ),

  // Companies overview for the gap-analysis landing dashboard.
  getGapOverview: () => api.get<GapOverviewRow[]>(`${BASE}/gap-overview`),

  expand: (id: string) =>
    api.post<ExpandScopeResponse>(`${BASE}/sessions/${id}/expand`),

  resolve: (id: string) =>
    api.post<ResolveScopeResponse>(`${BASE}/sessions/${id}/resolve`),

  dispatchResearch: (id: string, approved_missing_ids: string[]) =>
    api.post<DispatchResearchResponse>(
      `${BASE}/sessions/${id}/dispatch-research`,
      { approved_missing_ids },
    ),

  gapCheck: (id: string) =>
    api.post<GapCheckResponse>(`${BASE}/sessions/${id}/gap-check`),

  finalize: (id: string) =>
    api.post<FinalizeResponse>(`${BASE}/sessions/${id}/finalize`),

  getReport: (id: string) =>
    api.get<GapAnalysisDossier>(`${BASE}/sessions/${id}/report`),

  downloadReportPdf: (id: string, filename?: string) =>
    api.download(`${BASE}/sessions/${id}/report.pdf`, filename),

  downloadReportMarkdown: (id: string, filename?: string) =>
    api.download(`${BASE}/sessions/${id}/report.md`, filename),

  abandon: (id: string) =>
    api.post(`${BASE}/sessions/${id}/abandon`),
}
