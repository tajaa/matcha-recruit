import type { ScEmployeeImport, ScLocationImport } from '../../../types/scOnboarding'

export const LOCATION_COLUMNS = ['name', 'address', 'city', 'state', 'zipcode'] as const
export const EMPLOYEE_COLUMNS = ['email', 'first_name', 'last_name', 'work_state', 'job_title', 'department'] as const

function rows(text: string): string[][] {
  const result: string[][] = []
  let row: string[] = []
  let field = ''
  let quoted = false
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i]
    if (char === '"') {
      if (quoted && text[i + 1] === '"') { field += '"'; i += 1 } else quoted = !quoted
    } else if (char === ',' && !quoted) {
      row.push(field.trim()); field = ''
    } else if ((char === '\n' || char === '\r') && !quoted) {
      if (char === '\r' && text[i + 1] === '\n') i += 1
      row.push(field.trim()); field = ''
      if (row.some(Boolean)) result.push(row)
      row = []
    } else {
      field += char
    }
  }
  if (quoted) throw new Error('CSV contains an unclosed quoted value')
  row.push(field.trim())
  if (row.some(Boolean)) result.push(row)
  return result
}

function parse<T extends Record<string, string>>(text: string, expected: readonly string[]): T[] {
  const parsed = rows(text.replace(/^\uFEFF/, ''))
  if (!parsed.length) throw new Error('CSV is empty')
  const header = parsed[0].map((value) => value.toLowerCase())
  if (header.join(',') !== expected.join(',')) {
    throw new Error(`Expected header: ${expected.join(',')}`)
  }
  if (parsed.length === 1) throw new Error('CSV must contain at least one data row')
  if (parsed.length > 501) throw new Error('CSV cannot contain more than 500 data rows')
  return parsed.slice(1).map((values, index) => {
    if (values.length !== expected.length || values.some((value) => !value)) {
      throw new Error(`Row ${index + 2} must contain all ${expected.length} values`)
    }
    return Object.fromEntries(expected.map((column, i) => [column, values[i]])) as T
  })
}

function key(values: string[]) {
  return values.map((value) => value.trim().toLowerCase().replace(/\s+/g, ' ')).join('\u0000')
}

export function parseLocationsCsv(text: string): ScLocationImport[] {
  const locations = parse<ScLocationImport>(text, LOCATION_COLUMNS)
  const seen = new Set<string>()
  locations.forEach((location, index) => {
    const row = index + 2
    if (!/^[A-Za-z]{2}$/.test(location.state)) throw new Error(`Row ${row} state must use a two-letter code`)
    if (!/^\d{5}(?:-\d{4})?$/.test(location.zipcode)) throw new Error(`Row ${row} zipcode must use 12345 or 12345-6789`)
    const locationKey = key(LOCATION_COLUMNS.map((column) => location[column]))
    if (seen.has(locationKey)) throw new Error(`Row ${row} duplicates an earlier location row`)
    seen.add(locationKey)
  })
  return locations
}

export function parseEmployeesCsv(text: string): ScEmployeeImport[] {
  const employees = parse<ScEmployeeImport>(text, EMPLOYEE_COLUMNS)
  const seenEmails = new Set<string>()
  employees.forEach((employee, index) => {
    const row = index + 2
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(employee.email)) throw new Error(`Row ${row} email is invalid`)
    if (!/^[A-Za-z]{2}$/.test(employee.work_state)) throw new Error(`Row ${row} work_state must use a two-letter code`)
    const email = employee.email.toLowerCase()
    if (seenEmails.has(email)) throw new Error(`Row ${row} duplicates an earlier employee email`)
    seenEmails.add(email)
  })
  return employees
}
