import { api } from './client'
import type { RiskIndex, RiskIndexPortfolio } from '../types/riskIndex'

// Client-facing portal (own company)
export function fetchRiskProfile() {
  return api.get<RiskIndex>('/risk-profile')
}

// Broker views
export function fetchRiskIndexPortfolio() {
  return api.get<RiskIndexPortfolio>('/broker/risk-index')
}
export function fetchRiskIndexClient(companyId: string) {
  return api.get<RiskIndex>(`/broker/risk-index/${companyId}`)
}
