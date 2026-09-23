import type { ScheduleReview } from '../../../types/employeeSchedule'
import { costLabel, hoursLabel } from './reviewShape'

/** "Can I approve this?" — answered before the evidence, not after it.
 *
 *  Pure over a `ScheduleReview`, so a Huume-staged change, a fill scenario and
 *  a generated week all get the same verdict. Every sentence about the law is
 *  the server's (`jurisdiction.message`); this module only counts and groups.
 */

export type VerdictTone = 'ok' | 'warn' | 'bad'

export type VerdictFix =
  | { kind: 'board'; shiftId: string }
  | { kind: 'person'; employeeId: string }
  | { kind: 'ask'; text: string }

export interface VerdictIssue {
  key: string
  tone: VerdictTone
  label: string
  detail?: string
  fix?: VerdictFix
}

export interface ApprovalVerdict {
  tone: VerdictTone
  headline: string
  /** What the approve button says. With open seats it names them, so the
   *  manager confirms with the gap in view — never a bare "Approve". */
  approveLabel: string
  /** Neutral facts shown under the headline: filled x/y, cost, labor %. */
  facts: string[]
  issues: VerdictIssue[]
}

/** A finding kind as a manager would say it. Unknown kinds fall back to the
 *  kind itself, de-snaked — the finding's own `detail` carries the specifics. */
const FINDING_LABEL: Record<string, string> = {
  break_relief_uncovered: 'nobody can relieve a break',
  break_relief_impossible: 'a required break cannot be scheduled',
  coverage_gap: 'hours with nobody on',
  open_buffer_uncovered: 'nobody on for the open',
  close_buffer_uncovered: 'nobody on for the close',
  leader_absent_at_open: 'no lead at the open',
  leader_absent_at_close: 'no lead at the close',
  leader_absent: 'no lead on shift',
  existing_double_booking: 'someone already double-booked',
  staffing_concentration: 'one person carries the week',
}

export function findingLabel(kind: string): string {
  return FINDING_LABEL[kind] ?? kind.replaceAll('_', ' ')
}

function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`
}

export interface FindingGroup {
  kind: string
  severity: string
  count: number
  label: string
  details: string[]
}

/** Findings grouped by kind, gaps first then by count — 28 identical lines
 *  are one fact with a count, not 28 facts. */
export function groupFindings(findings: ScheduleReview['findings']): FindingGroup[] {
  const groups = new Map<string, FindingGroup>()
  for (const finding of findings) {
    const kind = String(finding.kind ?? 'finding')
    const severity = String(finding.severity ?? 'advisory')
    const key = `${severity}:${kind}`
    const group = groups.get(key) ?? { kind, severity, count: 0, label: findingLabel(kind), details: [] }
    group.count += 1
    const detail = finding.detail == null ? '' : String(finding.detail)
    if (detail && !group.details.includes(detail)) group.details.push(detail)
    groups.set(key, group)
  }
  return [...groups.values()].sort((a, b) =>
    Number(b.severity === 'gap') - Number(a.severity === 'gap') || b.count - a.count || a.kind.localeCompare(b.kind))
}

type Caps = Record<string, { max_weekly_minutes: number | null; allow_overtime: boolean }>

export function approvalVerdict(review: ScheduleReview, caps: Caps = {}, policyMinutes = 2400): ApprovalVerdict {
  const staged = review.assignments.filter((item) => item.verdict !== 'blocked')
  const open = review.unfilled.length
  const issues: VerdictIssue[] = []

  // 1. Open seats, grouped by WHY — "28 open · Food Handler Card …" is one
  //    thing to fix, not 28 rows to read.
  const openGroups = new Map<string, { count: number; reason: string; firstShift: string }>()
  for (const item of review.unfilled) {
    const key = item.reason_code || item.reason
    const group = openGroups.get(key) ?? { count: 0, reason: item.reason, firstShift: item.shift_id }
    group.count += 1
    openGroups.set(key, group)
  }
  for (const [key, group] of [...openGroups.entries()].sort((a, b) => b[1].count - a[1].count)) {
    issues.push({
      key: `open:${key}`, tone: 'bad',
      label: `${plural(group.count, 'shift')} left open`,
      detail: group.reason,
      fix: { kind: 'ask', text: `${plural(group.count, 'shift')} would stay open (${group.reason}). What would it take to fill them?` },
    })
  }

  // 2. State rules could not be read — the one thing worse than "unverified".
  if (review.compliance_status === 'unavailable') {
    issues.push({ key: 'law:unavailable', tone: 'bad', label: 'State rules could not be loaded', detail: review.jurisdiction.message })
  } else if (review.compliance_status === 'unmapped') {
    issues.push({ key: 'law:unmapped', tone: 'warn', label: 'Legality not verified for this state', detail: review.jurisdiction.message })
  }

  // 3. People pushed past their own cap or the house policy.
  for (const person of review.employees) {
    const after = person.after.minutes ?? 0
    const before = person.before.minutes ?? 0
    if (after <= before) continue
    const cap = caps[person.employee_id]?.max_weekly_minutes ?? null
    const overtimeOk = caps[person.employee_id]?.allow_overtime ?? false
    if (cap != null && after > cap) {
      issues.push({
        key: `hours:${person.employee_id}`, tone: 'warn',
        label: `${person.name} goes to ${hoursLabel(after)}`, detail: `over their ${hoursLabel(cap)} cap`,
        fix: { kind: 'person', employeeId: person.employee_id },
      })
    } else if (after > policyMinutes && !overtimeOk) {
      issues.push({
        key: `hours:${person.employee_id}`, tone: 'warn',
        label: `${person.name} goes to ${hoursLabel(after)}`, detail: `over the ${hoursLabel(policyMinutes)} house policy`,
        fix: { kind: 'person', employeeId: person.employee_id },
      })
    }
  }

  // 4. Assignments the guard refused, and statutory advisories to acknowledge.
  if (review.rejected.length) {
    issues.push({
      key: 'rejected', tone: 'warn', label: `${plural(review.rejected.length, 'assignment')} not staged`,
      detail: review.rejected[0]?.reasons[0]?.message,
    })
  }
  if (review.advisories.length) {
    issues.push({
      key: 'advisories', tone: 'warn', label: `${plural(review.advisories.length, 'statutory advisory', 'statutory advisories')} to acknowledge`,
      detail: review.advisories[0]?.message,
    })
  }

  // 5. Real gaps only; advisories stay in the evidence.
  for (const group of groupFindings(review.findings)) {
    if (group.severity !== 'gap') continue
    issues.push({
      key: `finding:${group.kind}`, tone: 'warn',
      label: `${group.count} × ${group.label}`, detail: group.details[0],
    })
  }

  const facts: string[] = []
  const total = staged.length + open
  if (total) facts.push(`${staged.length}/${total} filled`)
  if (review.cost) facts.push(`${costLabel(review.cost.after)} scheduled`)
  const labor = review.demand_model?.labor
  if (labor?.labor_pct != null) facts.push(`${labor.labor_pct}% of forecast sales`)
  else if (labor?.note) facts.push(labor.note)

  const bad = issues.filter((issue) => issue.tone === 'bad')
  const tone: VerdictTone = bad.length ? 'bad' : issues.length ? 'warn' : 'ok'
  const headline = open && !staged.length
    ? `Nothing could be staffed — all ${plural(open, 'shift')} would stay open`
    : open
      ? `${open} of ${plural(total, 'shift')} would stay open`
      : bad.length
        ? bad[0].label
        : issues.length
          ? `Ready to approve · ${plural(issues.length, 'thing')} to know`
          : 'Ready to approve'
  return {
    tone, headline, facts, issues,
    approveLabel: open ? `Approve with ${plural(open, 'shift')} open` : 'Approve',
  }
}

export interface PreviewShift {
  id: string
  starts_at: string
  ends_at: string
  role: string
  names: string[]
  open: number
  warn: boolean
  reasons: string[]
}

/** The proposed week as blocks the board can draw before anything is written.
 *
 *  Only a generated week: its `shift_id`s are demand keys with no row on the
 *  board yet. An edit or fill scenario names shifts the board already shows,
 *  so overlaying them would draw every shift twice. */
export function proposalPreviewShifts(review: ScheduleReview | null): PreviewShift[] {
  if (!review || review.kind !== 'week_draft') return []
  const byId = new Map<string, PreviewShift>()
  const entry = (id: string, role: string | null, startsAt: string | null, endsAt: string | null) => {
    if (!startsAt || !endsAt) return null
    const existing = byId.get(id)
    if (existing) return existing
    const created: PreviewShift = { id, starts_at: startsAt, ends_at: endsAt, role: role || 'Shift', names: [], open: 0, warn: false, reasons: [] }
    byId.set(id, created)
    return created
  }
  for (const item of review.assignments) {
    if (item.verdict === 'blocked' || !item.shift_id) continue
    const shift = entry(item.shift_id, item.role, item.starts_at, item.ends_at)
    if (!shift) continue
    if (item.employee_name) shift.names.push(item.employee_name)
    if (item.verdict === 'warn' || item.reasons.length) {
      shift.warn = true
      for (const reason of item.reasons) if (!shift.reasons.includes(reason.message)) shift.reasons.push(reason.message)
    }
  }
  for (const item of review.unfilled) {
    const shift = entry(item.shift_id, item.role, item.starts_at, item.ends_at)
    if (!shift) continue
    shift.open += 1
    if (!shift.reasons.includes(item.reason)) shift.reasons.push(item.reason)
  }
  return [...byId.values()].sort((a, b) => a.starts_at.localeCompare(b.starts_at) || a.id.localeCompare(b.id))
}

export interface DemandSegment {
  /** Minutes from local midnight — wall clock, like every schedule time. */
  start: number
  end: number
  demand: number
  covered: number
}

const SLOT = 30

function minuteOf(clock: string): number {
  const [hours, minutes] = clock.split(':').map(Number)
  return (hours || 0) * 60 + (minutes || 0)
}

/** Per day, Autopilot's demanded headcount against what the proposal staffs,
 *  in 30-minute slots merged into runs. Timestamps are UTC-tagged wall clock
 *  (as `shiftPosition` reads them), so the UTC fields ARE the store's clock. */
export function demandCoverage(review: ScheduleReview | null): Record<string, DemandSegment[]> {
  const model = review?.demand_model
  if (!review || !model) return {}
  const staffed = review.assignments.filter((item) => item.verdict !== 'blocked' && item.employee_id && item.starts_at && item.ends_at)
  const out: Record<string, DemandSegment[]> = {}
  for (const day of model.days) {
    if (day.closed || !day.staffing_curve.length) continue
    const slots: DemandSegment[] = []
    for (const run of day.staffing_curve) {
      for (let minute = minuteOf(run.start); minute < minuteOf(run.end); minute += SLOT) {
        const slotStart = Date.parse(`${day.date}T00:00:00Z`) + minute * 60000
        const slotEnd = slotStart + SLOT * 60000
        const covered = staffed.filter((item) =>
          Date.parse(item.starts_at as string) <= slotStart && Date.parse(item.ends_at as string) >= slotEnd).length
        const previous = slots[slots.length - 1]
        if (previous && previous.end === minute && previous.demand === run.headcount && previous.covered === covered) {
          previous.end = minute + SLOT
        } else {
          slots.push({ start: minute, end: minute + SLOT, demand: run.headcount, covered })
        }
      }
    }
    out[day.date] = slots
  }
  return out
}
