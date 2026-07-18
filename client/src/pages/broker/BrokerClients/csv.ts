import type { CsvRow } from './types'

export function parseCsv(text: string): CsvRow[] {
  const lines = text.split('\n').map((l) => l.trim()).filter(Boolean)
  if (lines.length < 2) return []
  const headers = lines[0].split(',').map((h) => h.trim().toLowerCase().replace(/\s+/g, '_'))
  return lines.slice(1).map((line) => {
    const values: string[] = []
    let current = ''
    let inQuotes = false
    for (const ch of line) {
      if (ch === '"') { inQuotes = !inQuotes; continue }
      if (ch === ',' && !inQuotes) { values.push(current.trim()); current = ''; continue }
      current += ch
    }
    values.push(current.trim())
    const row: any = {}
    headers.forEach((h, i) => { row[h] = values[i] || '' })
    return {
      company_name: row.company_name || '',
      contact_name: row.contact_name || '',
      contact_email: row.contact_email || '',
      contact_phone: row.contact_phone || '',
      industry: row.industry || '',
      company_size: row.company_size || '',
      headcount: row.headcount || '',
      notes: row.notes || '',
    } as CsvRow
  })
}
