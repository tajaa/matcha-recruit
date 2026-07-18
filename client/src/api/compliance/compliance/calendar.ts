import { api } from '../../client'
import type { ComplianceCalendarItem } from './types'

// ── Compliance Calendar ──

export function fetchComplianceCalendar(params?: {
  from?: string
  to?: string
  location_id?: string
}) {
  const qs = new URLSearchParams()
  if (params?.from) qs.set('from', params.from)
  if (params?.to) qs.set('to', params.to)
  if (params?.location_id) qs.set('location_id', params.location_id)
  const query = qs.toString()
  return api.get<ComplianceCalendarItem[]>(
    `/compliance/calendar${query ? '?' + query : ''}`
  )
}
