import { api } from '../client'

export type QuotableLine = 'bop' | 'gl' | 'wc' | 'professional'
// 'presented' = a broker placed this quote and presented it for the client to accept.
export type QuoteStatus = 'draft' | 'quoted' | 'presented' | 'bound' | 'expired' | 'error'

export type QuotePayload = {
  product: string
  line: string
  business: { legal_name: string | null; naics: string | null; industry: string | null; state: string | null; zip: string | null }
  exposure: { headcount: number | null; annual_payroll: number | null; annual_revenue: number | null }
}

export type Prefill = { line: string; payload: QuotePayload; mock_mode: boolean }

export type Quote = {
  id: string
  line: string
  carrier: string
  status: QuoteStatus
  quote_ref: string | null
  premium_cents: number | null
  expires_at: string | null
  error_message: string | null
  certificate_id: string | null
  created_at: string | null
  // present when a broker placed the quote (broker-in-the-middle path)
  placement?: string
  presented_at?: string | null
  commission_bps?: number | null
  broker_note?: string | null
}

export type QuoteInput = {
  line: QuotableLine
  legal_name?: string | null
  naics?: string | null
  state?: string | null
  zip_code?: string | null
  headcount?: number | null
  annual_payroll?: number | null
  annual_revenue?: number | null
}

export function getPrefill(line: QuotableLine) {
  return api.get<Prefill>(`/insurance/prefill?line=${line}`)
}
export function listQuotes() {
  return api.get<{ quotes: Quote[] }>('/insurance/quotes')
}
export function createQuote(input: QuoteInput) {
  return api.post<Quote>('/insurance/quote', input)
}
export function bindQuote(id: string) {
  return api.post<Quote>(`/insurance/quotes/${id}/bind`)
}
