/**
 * Per-company enrichment + persistent gap dashboard reads — roster enrichment,
 * the live gap dashboard, the statutory fit-map, requirement drill-ins, and the
 * companies overview.
 */

import { api } from '../../client'
import type {
  EnrichRosterResponse,
  FitMapResponse,
  GapDashboardResponse,
  GapOverviewRow,
  GapRequirementDetail,
} from './types'

const BASE = '/admin/onboarding'

export const dashboardApi = {
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
}
