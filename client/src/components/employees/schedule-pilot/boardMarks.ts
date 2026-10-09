import type { ScheduleReview, Shift } from '../../../types/employeeSchedule'
import { fmtTime } from '../../../types/employeeSchedule'

/** What a pending proposal does to one shift the board already shows, as
 *  short chips drawn on that shift — so a manager sees the change where it
 *  happens instead of flipping to Review to find it. */
export type ChangeTone = 'add' | 'remove' | 'move' | 'cancel' | 'blocked' | 'open'

export interface ChangeChip {
  tone: ChangeTone
  label: string
  /** The server's reasons, verbatim, for a hover. */
  title?: string
}

export interface ShiftMark {
  chips: ChangeChip[]
  /** Something on this shift carries a warning (policy or statute). */
  warn: boolean
}

function firstName(name: string | null | undefined): string {
  const trimmed = (name ?? '').trim()
  return trimmed ? trimmed.split(/\s+/)[0] : 'someone'
}

function timeRange(startsAt: string | null, endsAt: string | null): string {
  return startsAt && endsAt ? `${fmtTime(startsAt)}–${fmtTime(endsAt)}` : 'new time'
}

function chipFor(op: string, name: string | null, startsAt: string | null, endsAt: string | null): ChangeChip {
  switch (op) {
    case 'unassign': return { tone: 'remove', label: `− ${firstName(name)}` }
    case 'retime': return { tone: 'move', label: `↻ ${timeRange(startsAt, endsAt)}` }
    case 'cancel': return { tone: 'cancel', label: '✕ cancel' }
    case 'swap': return { tone: 'move', label: `⇄ ${firstName(name)}` }
    default: return { tone: 'add', label: `+ ${firstName(name)}` }
  }
}

/** Per board shift id, the chips a proposal puts on it. A generated week is
 *  drawn as preview blocks instead (`proposalPreviewShifts`), so it marks
 *  nothing here; ids the board doesn't show are left to the previews too. */
export function proposalMarks(review: ScheduleReview | null, boardShiftIds: ReadonlySet<string>): Map<string, ShiftMark> {
  const marks = new Map<string, ShiftMark>()
  if (!review || review.kind === 'week_draft') return marks
  const markFor = (id: string | null) => {
    if (!id || !boardShiftIds.has(id)) return null
    let mark = marks.get(id)
    if (!mark) { mark = { chips: [], warn: false }; marks.set(id, mark) }
    return mark
  }
  for (const item of review.assignments) {
    if (item.verdict === 'blocked') continue
    const mark = markFor(item.shift_id)
    if (!mark) continue
    const chip = chipFor(item.op, item.employee_name, item.starts_at, item.ends_at)
    if (item.reasons.length) chip.title = item.reasons.map((reason) => reason.message).join('\n')
    mark.chips.push(chip)
    if (item.verdict === 'warn' || item.reasons.length) mark.warn = true
  }
  for (const item of review.rejected) {
    const mark = markFor(item.shift_id)
    if (!mark) continue
    mark.chips.push({
      tone: 'blocked',
      label: `✕ ${firstName(item.employee_name)} not staged`,
      title: item.reasons.map((reason) => reason.message).join('\n') || undefined,
    })
  }
  for (const item of review.unfilled) {
    const mark = markFor(item.shift_id)
    if (!mark) continue
    mark.chips.push({ tone: 'open', label: 'stays open', title: item.reason })
  }
  return marks
}

/** Everything about a shift a manager would call "changed". */
export function shiftSignature(shift: Shift): string {
  const people = shift.assignments.map((assignment) => assignment.employee_id).sort().join(',')
  return [shift.starts_at, shift.ends_at, shift.status, shift.role ?? '', shift.required_staff, people].join('|')
}

/** Shift ids that are new, or differ from the snapshot taken before an apply —
 *  what the board highlights as "just changed" once Huume's write lands. */
export function changedShiftIds(before: ReadonlyMap<string, string>, after: Shift[]): Set<string> {
  const changed = new Set<string>()
  for (const shift of after) {
    if (before.get(shift.id) !== shiftSignature(shift)) changed.add(shift.id)
  }
  return changed
}
