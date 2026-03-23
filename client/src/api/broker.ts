import { api } from './client'
import type {
  BrokerPortfolioResponse,
  BrokerHandbookCoverage,
} from '../types/broker'

export function fetchBrokerPortfolio() {
  return api.get<BrokerPortfolioResponse>('/brokers/reporting/portfolio')
}

export function fetchBrokerHandbookCoverage() {
  return api.get<BrokerHandbookCoverage[]>('/brokers/reporting/handbook-coverage')
}
