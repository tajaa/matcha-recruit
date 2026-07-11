import { api } from './client'

export type TcorComponent = { key: string; amount: number; share_pct: number }
export type RetentionRow = {
  retention: number
  expected_retained: number
  volatility: number
  expected_transferred: number
  premium: number
  expected_total_cost: number
  risk_adjusted_cost: number
}
export type TcorResult = {
  company_id: string
  tcor: { components: TcorComponent[]; total: number }
  retained_losses_basis: 'modeled' | 'none'
  current_retention: number
  optimization: {
    candidates: RetentionRow[]
    recommended_retention: number | null
    basis: string
  } | null
  has_inputs: boolean
}
export type TcorInput = {
  line: string
  annual_premium?: number | null
  fees?: number | null
  risk_mitigation_spend?: number | null
  current_retention?: number | null
  policy_year?: number | null
}

export function getTcor() {
  return api.get<TcorResult>('/tcor')
}
export function upsertTcorInput(body: TcorInput) {
  return api.put<TcorResult>('/tcor/inputs', body)
}
export function deleteTcorInput(line: string, policyYear?: number) {
  const q = policyYear != null ? `&policy_year=${policyYear}` : ''
  return api.delete<TcorResult>(`/tcor/inputs?line=${encodeURIComponent(line)}${q}`)
}
