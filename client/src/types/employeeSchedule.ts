// Employee scheduling (feature: employee_schedule).

export type ShiftStatus = 'draft' | 'published' | 'cancelled'
export type AssignmentStatus = 'assigned' | 'confirmed' | 'declined'
export type RequestType = 'swap' | 'drop' | 'unavailable'
export type RequestStatus = 'pending' | 'approved' | 'denied' | 'cancelled'

export interface ShiftAssignment {
  employee_id: string
  name: string
  job_title: string | null
  status: AssignmentStatus
}

export interface Shift {
  id: string
  location_id: string | null
  template_id: string | null
  series_id: string | null
  role: string | null
  department: string | null
  starts_at: string
  ends_at: string
  break_minutes: number
  required_staff: number
  color: string | null
  notes: string | null
  status: ShiftStatus
  published_at: string | null
  assignments: ShiftAssignment[]
}

export interface ScheduleSummary {
  total_shifts: number
  published: number
  draft: number
  open_shifts: number
  assigned: number
}

export interface RosterEmployee {
  id: string
  name: string
  job_title: string | null
  department: string | null
}

export interface WeekResponse {
  week_start: string
  shifts: Shift[]
  roster: RosterEmployee[]
  summary: ScheduleSummary
}

export interface ShiftPayload {
  starts_at: string
  ends_at: string
  role?: string | null
  department?: string | null
  location_id?: string | null
  break_minutes?: number
  required_staff?: number
  color?: string | null
  notes?: string | null
  employee_ids?: string[]
  status?: ShiftStatus
}

export interface ShiftTemplate {
  id: string
  name: string
  role: string | null
  department: string | null
  location_id: string | null
  start_time: string
  end_time: string
  break_minutes: number
  required_staff: number
  days_of_week: number[]
  color: string | null
  notes: string | null
}

export interface TemplatePayload {
  name?: string
  role?: string | null
  department?: string | null
  location_id?: string | null
  start_time?: string
  end_time?: string
  break_minutes?: number
  required_staff?: number
  days_of_week?: number[]
  color?: string | null
  notes?: string | null
}

export interface ScheduleRequest {
  id: string
  employee_id: string
  employee_name: string
  request_type: RequestType
  shift_id: string | null
  shift_starts_at: string | null
  shift_ends_at: string | null
  target_employee_id: string | null
  unavailable_start: string | null
  unavailable_end: string | null
  reason: string | null
  status: RequestStatus
  review_notes: string | null
  reviewed_at: string | null
  created_at: string
}

// 0 = Sunday .. 6 = Saturday (matches the backend weekday mask).
export const WEEKDAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

export const STATUS_TONE: Record<ShiftStatus, string> = {
  draft: 'text-zinc-400 bg-zinc-500/10 border-zinc-500/20',
  published: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  cancelled: 'text-red-400 bg-red-500/10 border-red-500/20',
}

export const REQUEST_TONE: Record<RequestStatus, string> = {
  pending: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
  approved: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  denied: 'text-red-400 bg-red-500/10 border-red-500/20',
  cancelled: 'text-zinc-400 bg-zinc-500/10 border-zinc-500/20',
}

// ---- shared formatting (admin grid + employee portal render the same shifts) ----
//
// UTC wall-clock by convention: shifts are stored as the time an admin typed,
// so both surfaces read them back in UTC rather than the viewer's local zone.
// Keep these in one place — a fix applied to only one page silently gives the
// admin and the employee different times for the same shift.

export function fmtTime(iso: string): string {
  const d = new Date(iso)
  let h = d.getUTCHours()
  const m = d.getUTCMinutes()
  const ap = h >= 12 ? 'p' : 'a'
  h = h % 12 || 12
  return m ? `${h}:${String(m).padStart(2, '0')}${ap}` : `${h}${ap}`
}

export function toISODate(d: Date): string {
  return d.toISOString().slice(0, 10)
}

export function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + n)
  return toISODate(d)
}

export function startOfWeekSunday(d: Date): Date {
  const c = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()))
  c.setUTCDate(c.getUTCDate() - c.getUTCDay())
  return c
}

/** "Mon 7/13" — takes a YYYY-MM-DD day key or a full ISO timestamp. */
export function fmtDayLabel(iso: string): string {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`)
  return `${WEEKDAY_LABELS[d.getUTCDay()]} ${d.getUTCMonth() + 1}/${d.getUTCDate()}`
}

/** Human-readable text for any thrown API error (ApiError detail, or a fallback). */
export function errorMessage(err: unknown): string {
  const body = (err as { body?: { detail?: unknown } } | null)?.body
  const detail = body?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail) {
    const message = (detail as { message?: unknown }).message
    if (typeof message === 'string') return message
  }
  if (err instanceof Error && err.message) return err.message
  return 'Something went wrong. Please try again.'
}
