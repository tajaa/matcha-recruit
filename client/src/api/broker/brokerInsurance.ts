import { api } from '../client'
import type { Quote, QuotableLine, QuotePayload } from '../risk/insurance'

// A broker-placed quote adds placement metadata on top of the base client quote.
export type BrokerQuote = Quote & {
  placement?: string
  presented_at?: string | null
  commission_bps?: number | null
  broker_note?: string | null
  external_client_id?: string | null
}

export type BrokerPrefill = {
  line: string
  payload: QuotePayload
  mock_mode: boolean
  can_bind: boolean
}

export type BrokerQuoteInput = {
  line: QuotableLine
  legal_name?: string | null
  naics?: string | null
  state?: string | null
  zip_code?: string | null
  headcount?: number | null
  annual_payroll?: number | null
  annual_revenue?: number | null
  commission_bps?: number | null
  broker_note?: string | null
}

export type CreditLever = {
  key: string
  label: string
  status: 'realized' | 'available'
  est_credit_bps: number
  basis: string
}
export type RiskToRate = {
  levers: CreditLever[]
  realized_credit_bps: number
  available_credit_bps: number
  total_credit_bps: number
  readiness_score: number | null
}

export type LossRun = {
  policy_year: number
  claims: number
  incurred_cents: number
  paid_cents: number
  open: number
}
export type Claim = {
  id: string
  kind: string
  carrier: string
  claim_ref: string | null
  status: string
  incident_id: string | null
  amount_cents: number | null
  created_at: string | null
}

export type BookPolicy = {
  id: string
  line: string
  client_name: string | null
  on_platform: boolean
  premium_cents: number | null
  commission_bps: number | null
  est_commission_cents: number
  policy_expiry: string | null
}
export type InsuranceBook = {
  policies: BookPolicy[]
  count: number
  total_premium_cents: number
  est_commission_cents: number
}
export type Renewal = {
  id: string
  line: string
  client_name: string | null
  on_platform: boolean
  premium_cents: number | null
  policy_expiry: string | null
}

// --- on-platform (tenant) clients ---------------------------------------------
export function brokerPrefill(companyId: string, line: QuotableLine) {
  return api.get<BrokerPrefill>(`/broker/clients/${companyId}/insurance/prefill?line=${line}`)
}
export function brokerListQuotes(companyId: string) {
  return api.get<{ quotes: BrokerQuote[] }>(`/broker/clients/${companyId}/insurance/quotes`)
}
export function brokerCreateQuote(companyId: string, input: BrokerQuoteInput) {
  return api.post<BrokerQuote>(`/broker/clients/${companyId}/insurance/quote`, input)
}
export function brokerPresentQuote(companyId: string, quoteId: string, body: { commission_bps?: number | null; broker_note?: string | null }) {
  return api.post<BrokerQuote>(`/broker/clients/${companyId}/insurance/quotes/${quoteId}/present`, body)
}
export function brokerBindQuote(companyId: string, quoteId: string) {
  return api.post<BrokerQuote>(`/broker/clients/${companyId}/insurance/quotes/${quoteId}/bind`)
}
export function fetchRiskToRate(companyId: string) {
  return api.get<RiskToRate>(`/broker/clients/${companyId}/insurance/risk-to-rate`)
}
export function syncRiskToRate(companyId: string) {
  return api.post<{ synced: boolean; mock_mode: boolean; levers_pushed: number; available_credit_bps: number; realized_credit_bps: number }>(`/broker/clients/${companyId}/insurance/risk-to-rate/sync`)
}
export function fetchLossRuns(companyId: string) {
  return api.get<{ loss_runs: LossRun[]; mock_mode: boolean }>(`/broker/clients/${companyId}/insurance/loss-runs`)
}
export function fileFnol(companyId: string, body: { incident_id: string; description?: string | null }) {
  return api.post<Claim>(`/broker/clients/${companyId}/insurance/fnol`, body)
}

// --- off-platform (Broker Pro) clients ----------------------------------------
export function brokerExternalPrefill(clientId: string, line: QuotableLine) {
  return api.get<BrokerPrefill>(`/broker/external-clients/${clientId}/insurance/prefill?line=${line}`)
}
export function brokerExternalListQuotes(clientId: string) {
  return api.get<{ quotes: BrokerQuote[] }>(`/broker/external-clients/${clientId}/insurance/quotes`)
}
export function brokerExternalCreateQuote(clientId: string, input: BrokerQuoteInput) {
  return api.post<BrokerQuote>(`/broker/external-clients/${clientId}/insurance/quote`, input)
}
export function brokerExternalBindQuote(clientId: string, quoteId: string) {
  return api.post<BrokerQuote>(`/broker/external-clients/${clientId}/insurance/quotes/${quoteId}/bind`)
}

// --- broker book-level rollups ------------------------------------------------
export function fetchInsuranceBook() {
  return api.get<InsuranceBook>('/broker/insurance/book')
}
export function fetchInsuranceRenewals(days = 90) {
  return api.get<{ renewals: Renewal[]; window_days: number }>(`/broker/insurance/renewals?days=${days}`)
}
