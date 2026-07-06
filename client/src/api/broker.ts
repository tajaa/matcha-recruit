import { api } from './client'
import type {
  BrokerPortfolioResponse,
  BrokerHandbookCoverage,
  BrokerBatchCreateResponse,
  BrokerClientDetailResponse,
  BrokerLiteReferralToken,
  BrokerLiteReferralTokenListResponse,
  BrokerRiskAlertsResponse,
  BrokerReferredClientsResponse,
  EligibilityExceptionsResponse,
  RenewalRadarResponse,
  RenewalRadarDetail,
  WcPortfolioResponse,
  WcClientDetailResponse,
  WcMod, WcModWorksheetDraft,
  WcStateRate,
  WcClassCode,
  WcClassExposure,
  EplPortfolioResponse,
  EplReadiness,
  EplAttestationStatus,
  ExternalClient,
  ExternalClientRow,
  ExternalClientDetail,
  ExternalPropertyPayload,
  PropertyPortfolioResponse,
  CoverageGap,
  SubmissionNotes,
  SubmissionPreview,
  OutreachResponse,
  BrokerSeatsResponse,
  BrokerClientInvite,
  BrokerClientInviteListResponse,
  ClientInviteTier,
  BrokerMemberListResponse,
  BrokerMemberCreateResponse,
} from '../types/broker'
import type { ControlsRegister } from '../types/controlsEvidence'
import type { LimitReview } from '../types/limitAdequacy'
import type { LossDevelopment, LossRunDraft, LossRunCommit, LossRatioData, LossPremiumBody } from '../types/lossDevelopment'

export function fetchPropertyPortfolio() {
  return api.get<PropertyPortfolioResponse>('/broker/property-portfolio')
}

export function fetchBrokerPortfolio() {
  return api.get<BrokerPortfolioResponse>('/brokers/reporting/portfolio')
}

// --- WC portfolio (per-client TRIR / DART / premium) ---

export function fetchWcPortfolio() {
  return api.get<WcPortfolioResponse>('/broker/wc-portfolio')
}

// --- WC depth: per-client detail + experience-mod entry + NCCI overlay ---

export function fetchWcClientDetail(companyId: string) {
  return api.get<WcClientDetailResponse>(`/broker/wc-portfolio/${companyId}`)
}

export function recordWcMod(companyId: string, payload: {
  policy_period_start: string
  policy_period_end?: string
  experience_mod: number
  carrier?: string
  annual_premium?: number
  note?: string
  source?: 'manual' | 'worksheet'
}) {
  return api.post<WcMod>(`/broker/wc-portfolio/${companyId}/mods`, payload)
}

// Upload the bureau experience-rating worksheet PDF → auto-extract the real mod
// (a draft the broker confirms via recordWcMod with source='worksheet').
export function parseWcModWorksheet(companyId: string, file: File) {
  const fd = new FormData()
  fd.append('file', file)
  return api.upload<WcModWorksheetDraft>(`/broker/wc-portfolio/${companyId}/mods/parse`, fd)
}

export function deleteWcMod(companyId: string, modId: string) {
  return api.delete<{ status: string }>(`/broker/wc-portfolio/${companyId}/mods/${modId}`)
}

export function fetchWcStateRates() {
  return api.get<{ rates: WcStateRate[] }>('/broker/wc-state-rates')
}

// --- WC class codes (wcclass01) ---

export function fetchWcClassCodes() {
  return api.get<{ class_codes: WcClassCode[] }>('/broker/wc-class-codes')
}
export function fetchWcClassExposures(companyId: string) {
  return api.get<{ exposures: WcClassExposure[] }>(`/broker/wc-portfolio/${companyId}/class-exposures`)
}
export function recordWcClassExposure(companyId: string, payload: {
  class_code: string; state?: string; payroll?: number | null; headcount?: number | null; note?: string | null
}) {
  return api.post<{ exposures: WcClassExposure[] }>(`/broker/wc-portfolio/${companyId}/class-exposures`, payload)
}
export function deleteWcClassExposure(companyId: string, exposureId: string) {
  return api.delete<{ status: string }>(`/broker/wc-portfolio/${companyId}/class-exposures/${exposureId}`)
}

export interface ClassAutoMap {
  proposed: Array<{ class_code: string; description: string | null; state: string; payroll: number; headcount: number }>
  unmapped: string[]
  employee_count: number
}
export function autoMapClassExposures(companyId: string) {
  return api.post<ClassAutoMap>(`/broker/wc-portfolio/${companyId}/class-exposures/auto`, {})
}

// --- EPL readiness ---

export function fetchEplPortfolio() {
  return api.get<EplPortfolioResponse>('/broker/epl-portfolio')
}

export function fetchEplClientDetail(companyId: string) {
  return api.get<EplReadiness>(`/broker/epl-portfolio/${companyId}`)
}

export function recordEplAttestation(
  companyId: string,
  itemKey: string,
  payload: { status: EplAttestationStatus; note?: string },
) {
  return api.put<EplReadiness>(`/broker/epl-portfolio/${companyId}/attestations/${itemKey}`, payload)
}

// --- Off-platform broker clients (Broker Pro) ---

export type ExternalClientPayload = {
  name: string
  industry?: string | null
  headcount?: number | null
  primary_state?: string | null
  note?: string | null
}

export function fetchExternalClients() {
  return api.get<{ clients: ExternalClientRow[] }>('/broker/external-clients')
}

export function createExternalClient(payload: ExternalClientPayload) {
  return api.post<ExternalClient>('/broker/external-clients', payload)
}

export function fetchExternalClientDetail(id: string) {
  return api.get<ExternalClientDetail>(`/broker/external-clients/${id}`)
}

export function updateExternalClient(id: string, payload: ExternalClientPayload) {
  return api.put<ExternalClient>(`/broker/external-clients/${id}`, payload)
}

export function deleteExternalClient(id: string) {
  return api.delete<{ status: string }>(`/broker/external-clients/${id}`)
}

export function saveExternalWc(id: string, payload: Record<string, unknown>) {
  return api.put<ExternalClientDetail>(`/broker/external-clients/${id}/wc`, payload)
}

export function saveExternalProperty(id: string, payload: ExternalPropertyPayload) {
  return api.put<ExternalClientDetail>(`/broker/external-clients/${id}/property`, payload)
}

export interface ParsedLossRun {
  fields: Record<string, number | string | null>
  available: boolean
  model: string
}
export function parseExternalLossRun(id: string, file: File) {
  const fd = new FormData()
  fd.append('file', file)
  return api.upload<ParsedLossRun>(`/broker/external-clients/${id}/loss-run`, fd)
}

export interface IntakeLink {
  token: string
  expires_at: string
  path: string
}
export function createExternalIntakeLink(id: string) {
  return api.post<IntakeLink>(`/broker/external-clients/${id}/intake-link`, {})
}

export function saveExternalEplAttestation(
  id: string,
  itemKey: string,
  payload: { status: EplAttestationStatus; note?: string },
) {
  return api.put<ExternalClientDetail>(`/broker/external-clients/${id}/epl/${itemKey}`, payload)
}

// --- Submission packet + coverage-gap ---

export function downloadTenantSubmission(companyId: string) {
  return api.download(`/broker/clients/${companyId}/submission.pdf`, `submission-${companyId}.pdf`)
}

export function fetchTenantCoverageGap(companyId: string, currentCoverage?: Record<string, unknown>) {
  return api.post<CoverageGap>(`/broker/clients/${companyId}/coverage-gap`, { current_coverage: currentCoverage ?? null })
}

export function downloadExternalSubmission(clientId: string) {
  return api.download(`/broker/external-clients/${clientId}/submission.pdf`, `submission-${clientId}.pdf`)
}

export function fetchExternalCoverageGap(clientId: string, currentCoverage?: Record<string, unknown>) {
  return api.post<CoverageGap>(`/broker/external-clients/${clientId}/coverage-gap`, { current_coverage: currentCoverage ?? null })
}

// --- Broker commentary notes + submission preview (edit before download) ---

export function fetchTenantSubmissionPreview(companyId: string) {
  return api.get<SubmissionPreview>(`/broker/clients/${companyId}/submission`)
}
export function fetchTenantSubmissionNotes(companyId: string) {
  return api.get<SubmissionNotes>(`/broker/clients/${companyId}/submission-notes`)
}
export function saveTenantSubmissionNotes(companyId: string, notes: SubmissionNotes) {
  return api.put<SubmissionNotes>(`/broker/clients/${companyId}/submission-notes`, {
    cover_note: notes.cover_note, annotations: notes.annotations,
  })
}

export function fetchExternalSubmissionPreview(clientId: string) {
  return api.get<SubmissionPreview>(`/broker/external-clients/${clientId}/submission`)
}
export function fetchExternalSubmissionNotes(clientId: string) {
  return api.get<SubmissionNotes>(`/broker/external-clients/${clientId}/submission-notes`)
}
export function saveExternalSubmissionNotes(clientId: string, notes: SubmissionNotes) {
  return api.put<SubmissionNotes>(`/broker/external-clients/${clientId}/submission-notes`, {
    cover_note: notes.cover_note, annotations: notes.annotations,
  })
}

// --- controls-evidence (proof-of-controls) + claims-readiness for a client --

export function fetchClientControls(companyId: string) {
  return api.get<ControlsRegister>(`/broker/clients/${companyId}/controls-evidence`)
}

export function downloadClientControls(companyId: string) {
  return api.download(`/broker/clients/${companyId}/controls.pdf`, `proof-of-controls-${companyId}.pdf`)
}

export interface DefenseIncident {
  id: string; incident_number: string | null; title: string | null
  incident_type: string | null; severity: string | null; status: string | null; occurred_at: string | null
}
export interface DefenseErCase {
  id: string; case_number: string | null; title: string | null
  status: string | null; category: string | null; outcome: string | null; created_at: string | null
}

export function fetchClientDefenseIncidents(companyId: string) {
  return api.get<{ incidents: DefenseIncident[] }>(`/broker/clients/${companyId}/defense/incidents`)
}
export function downloadDefenseIncident(companyId: string, incidentId: string, num?: string | null) {
  return api.download(`/broker/clients/${companyId}/defense/incidents/${incidentId}.pdf`, `claims-readiness-${num ?? incidentId}.pdf`)
}
export function fetchClientDefenseErCases(companyId: string) {
  return api.get<{ cases: DefenseErCase[] }>(`/broker/clients/${companyId}/defense/er-cases`)
}
export function downloadDefenseErCase(companyId: string, caseId: string, num?: string | null) {
  return api.download(`/broker/clients/${companyId}/defense/er-cases/${caseId}.pdf`, `claims-readiness-${num ?? caseId}.pdf`)
}

// --- limit-adequacy / contract review for a client --------------------------

export function fetchClientLimitAdequacy(companyId: string) {
  return api.get<LimitReview>(`/broker/clients/${companyId}/limit-adequacy`)
}
export function downloadClientLimits(companyId: string) {
  return api.download(`/broker/clients/${companyId}/limits.pdf`, `limit-adequacy-${companyId}.pdf`)
}

// --- loss-run triangulation / development for a client ----------------------

export function fetchClientLossDevelopment(companyId: string) {
  return api.get<LossDevelopment>(`/broker/clients/${companyId}/loss-development`)
}
export function parseClientLossRun(companyId: string, file: File) {
  const fd = new FormData()
  fd.append('file', file)
  return api.upload<LossRunDraft>(`/broker/clients/${companyId}/loss-runs/parse`, fd)
}
export function commitClientLossRun(companyId: string, body: LossRunCommit) {
  return api.post<LossDevelopment>(`/broker/clients/${companyId}/loss-runs`, body)
}
export function deleteClientLossRunSnapshot(companyId: string, snapshotId: string) {
  return api.delete<LossDevelopment>(`/broker/clients/${companyId}/loss-runs/${snapshotId}`)
}
export function downloadClientLossDevelopment(companyId: string) {
  return api.download(`/broker/clients/${companyId}/loss-development.pdf`, `loss-development-${companyId}.pdf`)
}

// --- loss ratio (projected ultimate ÷ paid premium) -------------------------

export function fetchClientLossRatio(companyId: string) {
  return api.get<LossRatioData>(`/broker/clients/${companyId}/loss-ratio`)
}
export function recordClientLossPremium(companyId: string, body: LossPremiumBody) {
  return api.put<LossRatioData>(`/broker/clients/${companyId}/loss-ratio/premium`, body)
}
export function fetchExternalLossRatio(clientId: string) {
  return api.get<LossRatioData>(`/broker/external-clients/${clientId}/loss-ratio`)
}
export function recordExternalLossPremium(clientId: string, body: LossPremiumBody) {
  return api.put<LossRatioData>(`/broker/external-clients/${clientId}/loss-ratio/premium`, body)
}

// external-client loss-development triangle (off-platform, Broker Pro)
export function fetchExternalLossDevelopment(clientId: string) {
  return api.get<LossDevelopment>(`/broker/external-clients/${clientId}/loss-development`)
}
export function parseExternalLossRunDevelopment(clientId: string, file: File) {
  const fd = new FormData()
  fd.append('file', file)
  return api.upload<LossRunDraft>(`/broker/external-clients/${clientId}/loss-runs/parse`, fd)
}
export function commitExternalLossRun(clientId: string, body: LossRunCommit) {
  return api.post<LossDevelopment>(`/broker/external-clients/${clientId}/loss-runs`, body)
}
export function deleteExternalLossRunSnapshot(clientId: string, snapshotId: string) {
  return api.delete<LossDevelopment>(`/broker/external-clients/${clientId}/loss-runs/${snapshotId}`)
}
export function downloadExternalLossDevelopment(clientId: string) {
  return api.download(`/broker/external-clients/${clientId}/loss-development.pdf`, `loss-development-${clientId}.pdf`)
}

// --- Action Center: outreach ---

export function fetchActionCenterOutreach(companyId: string, refresh = false) {
  return api.get<OutreachResponse>(
    `/broker/action-center/outreach/${companyId}${refresh ? '?refresh=true' : ''}`,
  )
}

export function fetchBrokerHandbookCoverage() {
  return api.get<BrokerHandbookCoverage[]>('/brokers/reporting/handbook-coverage')
}

export function createBatchClientSetups(clients: any[]) {
  return api.post<BrokerBatchCreateResponse>('/brokers/client-setups/batch', { clients })
}

export function fetchBrokerClientDetail(companyId: string) {
  return api.get<BrokerClientDetailResponse>(`/brokers/companies/${companyId}`)
}

export function fetchLiteReferralTokens() {
  return api.get<BrokerLiteReferralTokenListResponse>('/brokers/lite-referral-tokens')
}

export function createLiteReferralToken(label?: string, expiresDays?: number, payer: 'broker' | 'business' = 'business') {
  return api.post<BrokerLiteReferralToken>('/brokers/lite-referral-tokens', {
    label: label || undefined,
    expires_days: expiresDays || undefined,
    payer,
  })
}

export function deactivateLiteReferralToken(tokenId: string) {
  return api.delete<{ status: string }>(`/brokers/lite-referral-tokens/${tokenId}`)
}

// --- Seat allocation: pool + company-pinned client invites ---

export function fetchBrokerSeats() {
  return api.get<BrokerSeatsResponse>('/brokers/seats')
}

export function createClientInvite(payload: {
  company_name: string
  seat_count: number
  tier: ClientInviteTier
  expires_days?: number
}) {
  return api.post<BrokerClientInvite>('/brokers/client-invites', payload)
}

export function listClientInvites(includeRevoked = false) {
  return api.get<BrokerClientInviteListResponse>(
    `/brokers/client-invites${includeRevoked ? '?include_revoked=true' : ''}`,
  )
}

export function revokeClientInvite(inviteId: string) {
  return api.delete<{ status: string }>(`/brokers/client-invites/${inviteId}`)
}

// --- Broker team members ---

export function fetchBrokerMembers() {
  return api.get<BrokerMemberListResponse>('/brokers/members')
}

export function createBrokerMember(payload: {
  name: string
  email: string
  role: 'admin' | 'member'
  password?: string
}) {
  return api.post<BrokerMemberCreateResponse>('/brokers/members', payload)
}

export function deactivateBrokerMember(memberId: string) {
  return api.delete<{ status: string }>(`/brokers/members/${memberId}`)
}

export function fetchBrokerRiskAlerts(includeResolved = false) {
  return api.get<BrokerRiskAlertsResponse>(
    `/brokers/risk-alerts${includeResolved ? '?include_resolved=true' : ''}`,
  )
}

export function scanBrokerThemeAlerts() {
  return api.post<{ clients_scanned: number; theme_alerts: number }>('/brokers/risk-alerts/scan-themes', {})
}

export function markBrokerRiskAlertRead(alertId: string) {
  return api.post<{ status: string }>(`/brokers/risk-alerts/${alertId}/read`, {})
}

// --- Referred clients (company picker) ---

export function fetchBrokerClientsLite() {
  return api.get<BrokerReferredClientsResponse>('/brokers/referred-clients')
}

// --- Employee Benefits: eligibility exceptions ---

export function fetchBenefitEligibilityExceptions() {
  return api.get<EligibilityExceptionsResponse>('/broker/benefits/eligibility-exceptions')
}

export function nudgeEligibilityException(id: string) {
  return api.post<{ status: string }>(`/broker/benefits/eligibility-exceptions/${id}/nudge`, {})
}

export function resolveEligibilityException(id: string, note?: string) {
  return api.post<{ status: string }>(`/broker/benefits/eligibility-exceptions/${id}/resolve`, { note })
}

export function dismissEligibilityException(id: string, note?: string) {
  return api.post<{ status: string }>(`/broker/benefits/eligibility-exceptions/${id}/dismiss`, { note })
}

export function downloadBenefitRosterTemplate() {
  return api.download('/broker/benefits/roster/template', 'benefit_roster_template.csv')
}

export function uploadBenefitRoster(companyId: string, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return api.upload<{ status: string; created?: number; updated?: number }>(
    `/broker/benefits/roster/upload?company_id=${companyId}`,
    formData,
  )
}

// --- Employee Benefits: renewal risk radar ---

export function fetchRenewalRadar() {
  return api.get<RenewalRadarResponse>('/broker/benefits/renewal-radar')
}

export function fetchRenewalRadarDetail(companyId: string) {
  return api.get<RenewalRadarDetail>(`/broker/benefits/renewal-radar/${companyId}`)
}

export function downloadStabilizationKit(companyId: string) {
  return api.download(
    `/broker/benefits/renewal-radar/${companyId}/stabilization-kit.pdf`,
    'stabilization-kit.pdf',
  )
}
