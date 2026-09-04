// Employee scheduling (feature: employee_schedule).

export type ShiftStatus = 'draft' | 'published' | 'cancelled'
export type ShiftKind = 'work' | 'training'
export type AssignmentStatus = 'assigned' | 'confirmed' | 'declined'
export type RequestType = 'swap' | 'drop' | 'pickup' | 'unavailable'
export type RequestStatus = 'pending' | 'awaiting_counterparty' | 'awaiting_manager' | 'approved' | 'denied' | 'cancelled'
export type AvailabilityState = 'unconfirmed' | 'always_available' | 'windows'
export type QualificationStatus = 'active' | 'training' | 'suspended'
export type ScheduleAutomationCadence = 'weekly' | 'once'

export type BreakGuidanceRequirement = {
  kind: 'meal' | 'rest'
  ordinal: number
  duration_minutes: number
  paid: boolean
  waived: boolean
  earliest_local?: string | null
  recommended_local?: string | null
  deadline_local?: string | null
  citation?: string | null
}

export type AssignmentComplianceGuidance = {
  status: 'complete' | 'unmapped' | 'error'
  summary?: string | null
  requirements: BreakGuidanceRequirement[]
  advisories: string[]
  jurisdiction?: string | null
}

/** One break period a manager reviewed and saved — the operational answer to
 *  "when", distinct from the legal requirement in compliance_guidance. */
export type PlannedBreak = {
  kind: 'meal' | 'rest'
  ordinal: number
  start_local: string
  duration_minutes: number
  source: 'suggested' | 'manager'
}

export type BreakStaggerStatus =
  | 'suggested'
  /** A time a manager already reviewed and saved — held fixed, not re-placed. */
  | 'saved'
  /** Placed, but the break cannot fit inside its legal window on this shift. */
  | 'deadline_conflict'
  | 'unresolved'
  | 'insufficient_coverage'

export type BreakStaggerResult = {
  employee_id: string
  kind: 'meal' | 'rest'
  ordinal: number
  status: BreakStaggerStatus
  duration_minutes: number
  suggested_start: string | null
  suggested_end: string | null
  reason: string | null
}

export type ShiftBreakStagger = {
  schema_version: number
  max_concurrent_breaks: number
  results: BreakStaggerResult[]
  advisories: { check: string; code: string; severity: string; message: string }[]
}

export type MealBreakWaiverAttestation = {
  employee_id: string
  on_file: boolean
  attested: boolean
  effective_from: string | null
  confirmed_at: string | null
  note: string | null
}

export type AssignmentNotePayload = {
  note: string | null
  visible_to_employee: boolean
  include_in_location_digest: boolean
  send_employee_notice: boolean
}

export interface ShiftAssignment {
  employee_id: string
  name: string
  job_title: string | null
  status: AssignmentStatus
  availability_overridden: boolean
  availability_override_at: string | null
  manager_note?: string | null
  manager_note_visible_to_employee?: boolean
  manager_note_include_in_location_digest?: boolean
  manager_note_send_employee_notice?: boolean
  compliance_guidance?: AssignmentComplianceGuidance | null
  planned_breaks?: PlannedBreak[] | null
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
  kind: ShiftKind
  training_requirement_id: string | null
  job_id: string | null
  published_at: string | null
  assignments: ShiftAssignment[]
}

export type ScheduleAuditAction =
  | 'shift.update'
  | 'shift.delete'
  | 'assignment.create'
  | 'assignment.delete'

export type ScheduleAuditEmployee = {
  id: string
  name: string | null
}

export type ScheduleAuditEntry = {
  id: string
  timestamp: string
  shift_id: string | null
  action: ScheduleAuditAction
  modifying_user: {
    id: string | null
    name: string | null
    email: string | null
  }
  assigned_employees: ScheduleAuditEmployee[]
  fields: string[]
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  details: Record<string, unknown>
}

export type ScheduleAuditResponse = {
  logs: ScheduleAuditEntry[]
  total: number
}

export type ScheduleAuditFilters = {
  start?: string
  end?: string
  shiftId?: string
  actorUserId?: string
  employeeId?: string
  limit?: number
  offset?: number
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
  job_ids: string[]
  job_qualifications?: Array<{
    job_id: string
    qualified_from: string | null
    qualified_until: string | null
  }>
}

export type JobCredentialRequirement = {
  id?: string
  credential_type_id: string
  credential_type_key?: string
  credential_type_label?: string
  has_expiration?: boolean
  is_required: boolean
  schedule_blocking: boolean
  effective_from?: string
  notes?: string | null
}

export type ScheduleJob = {
  id: string
  name: string
  location_id: string | null
  color: string | null
  notes: string | null
  credential_grace_days: number | null
  employee_ids: string[]
  credential_requirements: JobCredentialRequirement[]
}

export type EmployeeJobAssignment = {
  job_id: string
  job_name: string
  location_id: string | null
  is_primary: boolean
  qualification_status: QualificationStatus
  qualified_from: string | null
  qualified_until: string | null
  notes: string | null
  credential_requirements: JobCredentialRequirement[]
}

export type EmployeeJobAssignmentPayload = Omit<EmployeeJobAssignment, 'job_name' | 'location_id' | 'credential_requirements'>

export type EmployeeScheduleProfile = {
  employee_id: string
  availability_state: AvailabilityState
  availability_confirmed_at: string | null
  min_weekly_minutes: number | null
  target_weekly_minutes: number | null
  max_weekly_minutes: number | null
  max_consecutive_days: number | null
  allow_overtime: boolean
  prefer_extra_hours: boolean
}

export type EmployeeScheduleProfilePayload = Partial<Pick<EmployeeScheduleProfile,
  'min_weekly_minutes' | 'target_weekly_minutes' |
  'max_weekly_minutes' | 'max_consecutive_days' | 'allow_overtime' | 'prefer_extra_hours'
>>

export type JobPayload = {
  name?: string
  location_id?: string | null
  color?: string | null
  notes?: string | null
  employee_ids?: string[]
  credential_grace_days?: number | null
  credential_requirements?: JobCredentialRequirement[]
}

export interface ScheduleLocation {
  id: string
  name: string | null
  city: string
  state: string
  is_active: boolean
}

export interface AssignmentMovePayload {
  employee_id: string
  from_shift_id: string
  to_shift_id: string
}

export interface AssignmentMoveResponse {
  source_shift: Shift
  target_shift: Shift
}

// Per-employee lapse details for the roster picker. `null` = both `training`
// and `credential_templates` are off for this company (module-off, not
// "checked and clean" — an employee absent from the map has nothing lapsed).
export type RosterFlags = Record<string, {
  overdue_training: number
  lapsed_credentials: number
  warnings?: string[]
  blocking_credentials?: string[]
  credential_warnings?: string[]
  credential_expirations?: { label: string; expires_at: string }[]
}>

export interface WeekResponse {
  week_start: string
  location_id: string
  shifts: Shift[]
  roster: RosterEmployee[]
  roster_flags: RosterFlags | null
  summary: ScheduleSummary
}

export interface ShiftPayload {
  starts_at: string
  ends_at: string
  role?: string | null
  department?: string | null
  location_id?: string | null
  break_minutes?: number
  break_mode?: 'auto' | 'manual'
  required_staff?: number
  color?: string | null
  notes?: string | null
  employee_ids?: string[]
  status?: ShiftStatus
  kind?: ShiftKind
  training_requirement_id?: string | null
  job_id?: string | null
}

export interface TemplateBlock {
  id: string
  week_template_id: string | null
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
  job_id: string | null
}

export interface WeekTemplate {
  id: string
  name: string
  location_id: string | null
  color: string | null
  notes: string | null
  blocks: TemplateBlock[]
}

export interface BlockPayload {
  name?: string
  role?: string | null
  department?: string | null
  start_time?: string
  end_time?: string
  break_minutes?: number
  required_staff?: number
  days_of_week?: number[]
  color?: string | null
  notes?: string | null
  job_id?: string | null
}

export interface WeekTemplatePayload {
  name?: string
  location_id?: string | null
  color?: string | null
  notes?: string | null
  blocks?: BlockPayload[]
}

export interface WeekTemplateReplacePayload {
  name: string
  blocks: WeekTemplateBlockReplacePayload[]
}

export interface WeekTemplateBlockReplacePayload {
  id?: string
  name: string
  role: string | null
  start_time: string
  end_time: string
  break_minutes: number
  required_staff: number
  days_of_week: number[]
}

export interface ScheduleAutomationRule {
  id: string
  location_id: string
  location_name: string | null
  timezone: string
  enabled: boolean
  cadence: ScheduleAutomationCadence
  week_template_id: string | null
  week_template_name: string | null
  run_weekday: number | null
  run_date: string | null
  run_time: string
  target_weeks_ahead: number | null
  target_week_start: string | null
  next_run_at: string | null
  last_attempt_at: string | null
  last_completed_at: string | null
  last_status: string | null
  last_message: string | null
  last_generation_run_id: string | null
}

export interface ScheduleAutomationPayload {
  enabled: boolean
  cadence: ScheduleAutomationCadence
  week_template_id: string
  run_weekday: number | null
  run_date: string | null
  run_time: string
  target_weeks_ahead: number | null
  target_week_start: string | null
}

export interface ScheduleRequest {
  id: string
  employee_id: string
  employee_name: string
  request_type: RequestType
  shift_id: string | null
  shift_starts_at: string | null
  shift_ends_at: string | null
  shift_role?: string | null
  shift_department?: string | null
  target_employee_id: string | null
  target_employee_name?: string | null
  counter_shift_id: string | null
  counterparty_confirmed_at: string | null
  counter_shift_starts_at: string | null
  counter_shift_ends_at: string | null
  counter_shift_role?: string | null
  counter_shift_department?: string | null
  unavailable_start: string | null
  unavailable_end: string | null
  reason: string | null
  status: RequestStatus
  can_withdraw?: boolean
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
  awaiting_counterparty: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
  awaiting_manager: 'text-sky-400 bg-sky-500/10 border-sky-500/20',
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
