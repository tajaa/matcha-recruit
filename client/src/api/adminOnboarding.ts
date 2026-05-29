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
  }
}

// Drift signals computed cheaply on the persistent dashboard — how much the
// company has changed since the last (Gemini) analysis ran.
export type GapDrift = {
  last_analyzed_at?: string | null
  new_locations: number
  new_jurisdictions: number
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
