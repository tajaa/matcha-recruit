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
  BrokerMilestonesResponse,
  OutreachResponse,
} from '../types/broker'

export function fetchBrokerPortfolio() {
  return api.get<BrokerPortfolioResponse>('/brokers/reporting/portfolio')
}

// --- WC portfolio (per-client TRIR / DART / premium) ---

export function fetchWcPortfolio() {
  return api.get<WcPortfolioResponse>('/broker/wc-portfolio')
}

// --- Action Center: milestones + outreach ---

export function fetchActionCenterMilestones(includeSuperseded = false) {
  return api.get<BrokerMilestonesResponse>(
    `/broker/action-center/milestones${includeSuperseded ? '?include_superseded=true' : ''}`,
  )
}

export function markMilestoneRead(milestoneId: string) {
  return api.post<{ status: string }>(`/broker/action-center/milestones/${milestoneId}/read`, {})
}

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

export function fetchBrokerRiskAlerts(includeResolved = false) {
  return api.get<BrokerRiskAlertsResponse>(
    `/brokers/risk-alerts${includeResolved ? '?include_resolved=true' : ''}`,
  )
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
