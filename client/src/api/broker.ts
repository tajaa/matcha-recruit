import { api } from './client'
import type {
  BrokerPortfolioResponse,
  BrokerHandbookCoverage,
  BrokerBatchCreateResponse,
  BrokerClientDetailResponse,
  BrokerLiteReferralToken,
  BrokerLiteReferralTokenListResponse,
  BrokerRiskAlertsResponse,
} from '../types/broker'

export function fetchBrokerPortfolio() {
  return api.get<BrokerPortfolioResponse>('/brokers/reporting/portfolio')
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
