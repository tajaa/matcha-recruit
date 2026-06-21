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
