/**
 * Scope + gap-analysis workflow — expand/resolve the scope, dispatch research,
 * run the gap-check, finalize, and fetch/download the report.
 */

import { api } from '../../client'
import type {
  DispatchResearchResponse,
  ExpandScopeResponse,
  FinalizeResponse,
  GapAnalysisDossier,
  GapCheckResponse,
  ResolveScopeResponse,
} from './types'

const BASE = '/admin/onboarding'

export const scopeApi = {
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
