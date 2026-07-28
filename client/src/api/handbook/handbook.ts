import { api } from '../client'
import type {
  HandbookListItem,
  HandbookDetail,
  HandbookCreate,
  HandbookUpdate,
  HandbookChangeRequest,
  HandbookDistributionResult,
  HandbookDistributionRecipient,
  HandbookAcknowledgementSummary,
  HandbookFreshnessCheck,
  HandbookCoverage,
  CompanyHandbookProfile,
  CompanyHandbookProfileInput,
  HandbookGuidedDraftRequest,
  HandbookGuidedDraftResponse,
  HandbookWizardDraft,
  HandbookWizardDraftState,
  HandbookPublishResponse,
  HandbookShareLink,
  HandbookSection,
} from '../../types/handbook'

export const handbooks = {
  list: () => api.get<HandbookListItem[]>('/handbooks'),
  get: (id: string) => api.get<HandbookDetail>(`/handbooks/${id}`),
  create: (data: HandbookCreate) => api.post<HandbookDetail>('/handbooks', data),
  update: (id: string, data: HandbookUpdate) => api.put<HandbookDetail>(`/handbooks/${id}`, data),
  publish: (id: string) => api.post<HandbookPublishResponse>(`/handbooks/${id}/publish`),
  archive: (id: string) => api.post<{ message: string }>(`/handbooks/${id}/archive`),

  getProfile: () => api.get<CompanyHandbookProfile>('/handbooks/profile'),
  updateProfile: (data: CompanyHandbookProfileInput) =>
    api.put<CompanyHandbookProfile>('/handbooks/profile', data),
  getAutoScopes: () => api.get<{ state: string; city: string | null }[]>('/handbooks/auto-scopes'),

  uploadFile: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.upload<{ url: string; filename: string; company_id: string }>('/handbooks/upload', fd)
  },
  downloadPdf: (id: string, title: string) =>
    api.download(`/handbooks/${id}/pdf`, `${title}.pdf`),

  // Public read-only share link. Only a published handbook can be shared;
  // getShareLink resolves to null when the handbook has never been shared.
  getShareLink: (id: string) => api.get<HandbookShareLink | null>(`/handbooks/${id}/share`),
  createShareLink: (id: string, expiresInDays?: number) =>
    api.post<HandbookShareLink>(`/handbooks/${id}/share`, { expires_in_days: expiresInDays ?? null }),
  revokeShareLink: (id: string) => api.delete<{ status: string }>(`/handbooks/${id}/share`),

  generateGuidedDraft: (data: HandbookGuidedDraftRequest) =>
    api.post<HandbookGuidedDraftResponse>('/handbooks/guided-draft', data),
  getWizardDraft: () => api.get<HandbookWizardDraft | null>('/handbooks/wizard-draft'),
  saveWizardDraft: (state: HandbookWizardDraftState) =>
    api.put<HandbookWizardDraft>('/handbooks/wizard-draft', { state }),
  clearWizardDraft: () => api.delete<{ deleted: boolean }>('/handbooks/wizard-draft'),

  listChanges: (id: string) => api.get<HandbookChangeRequest[]>(`/handbooks/${id}/changes`),
  acceptChange: (handbookId: string, changeId: string) =>
    api.post<HandbookChangeRequest>(`/handbooks/${handbookId}/changes/${changeId}/accept`),
  rejectChange: (handbookId: string, changeId: string) =>
    api.post<HandbookChangeRequest>(`/handbooks/${handbookId}/changes/${changeId}/reject`),

  distribute: (id: string, employeeIds?: string[]) =>
    api.post<HandbookDistributionResult>(
      `/handbooks/${id}/distribute`,
      employeeIds ? { employee_ids: employeeIds } : undefined,
    ),
  listDistributionRecipients: (id: string) =>
    api.get<HandbookDistributionRecipient[]>(`/handbooks/${id}/distribution-recipients`),
  acknowledgements: (id: string) => api.get<HandbookAcknowledgementSummary>(`/handbooks/${id}/acknowledgements`),

  getLatestFreshnessCheck: (id: string) =>
    api.get<HandbookFreshnessCheck | null>(`/handbooks/${id}/freshness-check/latest`),
  runFreshnessCheck: (id: string) => api.post<HandbookFreshnessCheck>(`/handbooks/${id}/freshness-check`),

  getCoverage: (id: string) => api.get<HandbookCoverage>(`/handbooks/${id}/coverage`),
  markSectionReviewed: (handbookId: string, sectionId: string) =>
    api.post<HandbookSection>(`/handbooks/${handbookId}/sections/${sectionId}/mark-reviewed`),
}
