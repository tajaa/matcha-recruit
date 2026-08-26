import { ApiError } from '../../../api/client'
import { fmtDayLabel, fmtTime } from '../../../types/employeeSchedule'

export interface ComplianceViolation {
  check: string
  severity: string
  message: string
  statute?: string | null
}

export interface ForceableDetail {
  code?: string
  message?: string
  conflicts?: { starts_at: string; ends_at: string; role: string | null }[]
  violations?: { message: string; [k: string]: unknown }[]
}

function forceableDetail(err: unknown): ForceableDetail | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null
  return (err.body as { detail?: ForceableDetail } | null)?.detail ?? null
}

/** Meal-break advisories need a plan, not the generic force-through prompt.
 * Schedule-editor assignment flows use this to open the affected shift's
 * break control while every other caller keeps the normal 409 behavior. */
export function mealBreakConflictMessage(err: unknown): string | null {
  const detail = forceableDetail(err)
  if (detail?.code !== 'schedule_compliance') return null
  const violations = (detail.violations ?? []) as unknown as ComplianceViolation[]
  const mealBreaks = violations.filter((violation) => violation.check === 'meal_break')
  if (mealBreaks.length === 0) return null
  return mealBreaks
    .map((violation) => `${violation.message}${violation.statute ? ` [${violation.statute}]` : ''}`)
    .join(' ')
}

/** A 409 the admin can override → confirm() text. Anything else → null (it gets
 *  surfaced as an error instead of silently swallowed). */
export function conflictPrompt(err: unknown): string | null {
  const detail = forceableDetail(err)
  if (!detail) return null
  if (detail?.code === 'schedule_conflict') {
    const lines = (detail.conflicts ?? []).map(
      (c) => `• ${fmtDayLabel(c.starts_at)} ${fmtTime(c.starts_at)}–${fmtTime(c.ends_at)}${c.role ? ` (${c.role})` : ''}`,
    )
    return `Already scheduled during this time:\n${lines.join('\n')}\n\nAssign anyway?`
  }
  if (detail?.code === 'shift_full') {
    return `${detail.message ?? 'This shift is already fully staffed.'}\n\nAssign anyway?`
  }
  if (detail?.code === 'schedule_compliance') {
    // Advisory scheduling-law flags (meal break, overtime, min rest, Fair
    // Workweek notice/clopening). A hard minor-hour limit comes back as a 422
    // (schedule_compliance_block) instead and is surfaced as a non-overridable
    // error by errorMessage().
    const violations = (detail.violations ?? []) as unknown as ComplianceViolation[]
    const lines = violations.map((v) => `• ${v.message}${v.statute ? ` [${v.statute}]` : ''}`)
    const allFairWorkweek = violations.length > 0 && violations.every((v) => v.check?.startsWith('fair_workweek_'))
    const hasMealBreakViolation = violations.some((v) => v.check === 'meal_break')
    const lead = hasMealBreakViolation
      ? 'This shift needs a compliant break plan:'
      : allFairWorkweek
        ? 'This change may trigger Fair Workweek obligations:'
        : 'This shift may not comply with scheduling law:'
    return `${lead}\n${lines.join('\n')}\n\nSchedule anyway?`
  }
  if (detail?.code === 'outside_availability') {
    const lines = (detail.violations ?? []).map((v) => `• ${v.message}`)
    return `Outside this employee's logged availability:\n${lines.join('\n')}\n\nSchedule anyway?`
  }
  if (detail?.code === 'not_qualified_for_job') {
    return `${detail.message ?? 'This employee is not qualified for the selected job.'}\n\nAssign anyway?`
  }
  return null
}
