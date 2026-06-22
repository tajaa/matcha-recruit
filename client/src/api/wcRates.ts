import { api } from './client'

export interface WcRateSummary {
  state_rates: Record<string, number>
  class_codes: Record<string, number>
}
export interface ImportResult {
  imported: number
  errors: string[]
}

export function fetchWcRateSummary() {
  return api.get<WcRateSummary>('/admin/wc-rates/summary')
}

export interface WcStateRateRow {
  state: string
  loss_cost_change_pct: number | null
  effective_date: string | null
  trend: string
  source: string
  note: string | null
  updated_at: string | null
}
export interface WcClassCodeRow {
  state: string
  class_code: string
  description: string | null
  base_rate: number | null
  source: string
}
export function fetchWcStateRatesList() {
  return api.get<{ rows: WcStateRateRow[] }>('/admin/wc-rates/state-rates')
}
export function fetchWcClassCodesList() {
  return api.get<{ rows: WcClassCodeRow[] }>('/admin/wc-rates/class-codes')
}

function importCsv(path: string, file: File, source: string) {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('source', source)
  return api.upload<ImportResult>(path, fd)
}
export function importWcStateRates(file: File, source: string) {
  return importCsv('/admin/wc-rates/state-rates', file, source)
}
export function importWcClassCodes(file: File, source: string) {
  return importCsv('/admin/wc-rates/class-codes', file, source)
}

export function downloadWcRateTemplate(kind: 'state-rates' | 'class-codes') {
  return api.download(`/admin/wc-rates/template/${kind}`, `wc_${kind.replace('-', '_')}_template.csv`)
}
