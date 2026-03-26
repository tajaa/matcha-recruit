import { api } from './client'
import type {
  BrokerPortfolioResponse,
  BrokerHandbookCoverage,
  BrokerBatchCreateResponse,
  BrokerClientDetailResponse,
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
