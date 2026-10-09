import { Check, Plus, Sparkles } from 'lucide-react'
import type { RosterEmployee, ScheduleReview, Shift } from '../../../types/employeeSchedule'
import { fmtDayLabel, fmtTime } from '../../../types/employeeSchedule'
import { hoursLabel } from './reviewShape'
import type { ShiftMark } from './boardMarks'
import type { PreviewShift } from './reviewVerdict'

/** The week as a manager reads a posted schedule: one row per person, one
 *  column per day, each cell that person's shifts. Open seats ride on top.
 *  A pending Huume proposal is drawn in place — a dashed chip where someone
 *  would be added, a struck chip where someone would come off, an outline on
 *  a shift it retimes or cancels — so the change is visible without opening
 *  the review. The time grid stays one toggle away for drag-and-resize. */
export interface WeekRosterGridProps {
  days: string[]
  shifts: Shift[]
  roster: RosterEmployee[]
  /** The proposal being shown, if any: who it adds to or takes off a shift. */
  review?: ScheduleReview | null
  /** Shifts a proposal would create (a generated week, or a batch's new shifts). */
  previewShifts?: PreviewShift[]
  marks?: ReadonlyMap<string, ShiftMark>
  recentShiftIds?: ReadonlySet<string>
  selectedEmployeeId: string | null
  huumeSelectedShiftIds: ReadonlySet<string>
  onOpenShift(shift: Shift): void
  onToggleHuumeSelection(shift: Shift): void
  onSelectEmployee?(employeeId: string | null): void
  onCreateFor(date: string, employeeId: string): void
}

type Row = { id: string; name: string; title: string | null }

type Cell =
  | { kind: 'shift'; shift: Shift; removed: boolean }
  | { kind: 'proposed'; key: string; startsAt: string; endsAt: string; role: string | null; name: string; shift?: Shift }

const day = (iso: string) => iso.slice(0, 10)
const minutesOf = (startsAt: string, endsAt: string) => Math.max(0, (Date.parse(endsAt) - Date.parse(startsAt)) / 60000)
const span = (startsAt: string, endsAt: string) => `${fmtTime(startsAt)}–${fmtTime(endsAt)}`
const ADD_OPS = new Set(['assign', 'reassign', 'swap', 'create'])

export default function WeekRosterGrid({
  days, shifts, roster, review, previewShifts = [], marks, recentShiftIds, selectedEmployeeId,
  huumeSelectedShiftIds, onOpenShift, onToggleHuumeSelection, onSelectEmployee, onCreateFor,
}: WeekRosterGridProps) {
  const inWeek = new Set(days)
  const weekShifts = shifts.filter((shift) => inWeek.has(day(shift.starts_at)))
  const byId = new Map(weekShifts.map((shift) => [shift.id, shift]))

  // Who a proposal adds to (or takes off) shifts the board already shows.
  const adds = new Map<string, Cell[]>()
  const removes = new Set<string>()
  if (review && review.kind !== 'week_draft') {
    for (const item of review.assignments) {
      if (item.verdict === 'blocked' || !item.employee_id || !item.shift_id) continue
      const existing = byId.get(item.shift_id)
      if (item.op === 'unassign') { removes.add(`${item.shift_id}:${item.employee_id}`); continue }
      if (!ADD_OPS.has(item.op) || !existing) continue
      if (existing.assignments.some((assignment) => assignment.employee_id === item.employee_id)) continue
      const list = adds.get(item.employee_id) ?? []
      list.push({ kind: 'proposed', key: `${item.shift_id}:${item.employee_id}`, startsAt: existing.starts_at, endsAt: existing.ends_at, role: existing.role, name: item.employee_name ?? '', shift: existing })
      adds.set(item.employee_id, list)
    }
  }

  // Rows: the roster, plus anyone on a shift or a proposal who isn't on it.
  const rows: Row[] = roster.map((person) => ({ id: person.id, name: person.name, title: person.job_title }))
  const known = new Set(rows.map((row) => row.id))
  const byName = new Map(rows.map((row) => [row.name.trim().toLowerCase(), row.id]))
  for (const shift of weekShifts) {
    for (const assignment of shift.assignments) {
      if (!known.has(assignment.employee_id)) {
        known.add(assignment.employee_id)
        rows.push({ id: assignment.employee_id, name: assignment.name, title: assignment.job_title })
      }
    }
  }
  const previewFor = new Map<string, Cell[]>()
  const openPreviews: PreviewShift[] = []
  for (const preview of previewShifts) {
    if (preview.open > 0) openPreviews.push(preview)
    for (const name of preview.names) {
      let id = byName.get(name.trim().toLowerCase())
      if (!id) {
        id = `name:${name}`
        if (!known.has(id)) { known.add(id); byName.set(name.trim().toLowerCase(), id); rows.push({ id, name, title: null }) }
      }
      const list = previewFor.get(id) ?? []
      list.push({ kind: 'proposed', key: `${preview.id}:${name}`, startsAt: preview.starts_at, endsAt: preview.ends_at, role: preview.role, name })
      previewFor.set(id, list)
    }
  }

  const cellsFor = (employeeId: string, date: string): Cell[] => {
    const real: Cell[] = weekShifts
      .filter((shift) => day(shift.starts_at) === date && shift.assignments.some((assignment) => assignment.employee_id === employeeId))
      .map((shift) => ({ kind: 'shift', shift, removed: removes.has(`${shift.id}:${employeeId}`) }))
    const proposed = [...(adds.get(employeeId) ?? []), ...(previewFor.get(employeeId) ?? [])]
      .filter((cell) => cell.kind === 'proposed' && day(cell.startsAt) === date)
    return [...real, ...proposed].sort((a, b) => (startOf(a) < startOf(b) ? -1 : startOf(a) > startOf(b) ? 1 : 0))
  }

  const minutesFor = (employeeId: string) => weekShifts
    .filter((shift) => shift.status !== 'cancelled' && shift.assignments.some((assignment) => assignment.employee_id === employeeId))
    .reduce((total, shift) => total + minutesOf(shift.starts_at, shift.ends_at) - (shift.break_minutes || 0), 0)
  const proposedMinutesFor = (employeeId: string) => {
    const added = [...(adds.get(employeeId) ?? []), ...(previewFor.get(employeeId) ?? [])]
      .reduce((total, cell) => total + (cell.kind === 'proposed' ? minutesOf(cell.startsAt, cell.endsAt) : 0), 0)
    const removed = weekShifts
      .filter((shift) => removes.has(`${shift.id}:${employeeId}`))
      .reduce((total, shift) => total + minutesOf(shift.starts_at, shift.ends_at) - (shift.break_minutes || 0), 0)
    return added - removed
  }

  // People working this week first (by their first shift), then everyone else.
  // Plain code-point order on purpose: localeCompare ranks punctuation before
  // digits, which would put the no-shifts sentinel ahead of real ISO times.
  const firstStart = (employeeId: string) => days.flatMap((date) => cellsFor(employeeId, date)).map(startOf).sort()[0] ?? '\uffff'
  const byTime = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0)
  const ordered = [...rows].sort((a, b) => byTime(firstStart(a.id), firstStart(b.id)) || a.name.localeCompare(b.name))

  const openOn = (date: string) => weekShifts.filter((shift) => day(shift.starts_at) === date && shift.status !== 'cancelled'
    && shift.assignments.length < shift.required_staff)
  const columns = { gridTemplateColumns: `minmax(132px, 168px) repeat(${days.length}, minmax(96px, 1fr))` }

  const chipFrame = (shift: Shift | undefined, base: string) => {
    if (!shift) return base
    const mark = marks?.get(shift.id)
    if (mark) return `${base} ring-2 ${mark.warn ? 'ring-amber-400/60' : 'ring-sky-400/60'}`
    if (recentShiftIds?.has(shift.id)) return `${base} ring-2 ring-emerald-400/50`
    if (huumeSelectedShiftIds.has(shift.id)) return `${base} ring-1 ring-emerald-400`
    return base
  }

  const markLine = (shift: Shift) => {
    const mark = marks?.get(shift.id)
    if (!mark || !mark.chips.length) return null
    return (
      <span aria-label="Proposed by Huume" className="mt-0.5 block truncate text-[9px] font-medium text-sky-200" title={mark.chips.map((chip) => chip.title || chip.label).join('\n')}>
        {mark.chips.map((chip) => <span key={chip.label}>{chip.label} </span>)}
      </span>
    )
  }
  const huumeToggle = (shift: Shift) => {
    const selected = huumeSelectedShiftIds.has(shift.id)
    return (
      <button
        type="button"
        onClick={() => onToggleHuumeSelection(shift)}
        aria-pressed={selected}
        aria-label={`${selected ? 'Remove' : 'Select'} ${shift.role || 'shift'} for Huume`}
        title={selected ? 'Remove from Huume context' : 'Select for Huume'}
        className={`absolute right-0.5 top-0.5 rounded p-0.5 ${selected ? 'bg-emerald-400 text-zinc-950' : 'text-zinc-500 opacity-0 hover:text-emerald-300 focus:opacity-100 group-hover:opacity-100'}`}
      >
        {selected ? <Check className="h-3 w-3" /> : <Sparkles className="h-3 w-3" />}
      </button>
    )
  }

  const renderCell = (cell: Cell) => {
    if (cell.kind === 'proposed') {
      return (
        <div
          key={cell.key}
          role="img"
          aria-label={`Proposed ${cell.role || 'shift'} ${span(cell.startsAt, cell.endsAt)}: ${cell.name || 'someone'}`}
          className={chipFrame(cell.shift, 'rounded border border-dashed border-sky-400/70 bg-sky-500/10 px-1.5 py-1 text-sky-100')}
        >
          <span className="block truncate font-mono text-[11px] font-semibold">+ {span(cell.startsAt, cell.endsAt)}</span>
          <span className="block truncate text-[10px] text-sky-200/80">{cell.role || 'Shift'}</span>
        </div>
      )
    }
    const { shift, removed } = cell
    const mark = marks?.get(shift.id)
    const tone = removed
      ? 'border-red-500/40 bg-red-500/10 text-red-200 line-through decoration-red-400/70'
      : shift.status === 'cancelled'
        ? 'border-red-500/30 bg-red-950/50 text-red-300/80 line-through'
        : shift.status === 'draft'
          ? 'border-zinc-600 border-dashed bg-zinc-900 text-zinc-100'
          : 'border-zinc-700 bg-zinc-800/80 text-zinc-100'
    return (
      <div key={shift.id} className={chipFrame(shift, `group relative rounded border px-1.5 py-1 ${tone}`)}>
        <button type="button" onClick={() => onOpenShift(shift)} className="block w-full min-w-0 text-left" title={shift.status === 'draft' ? 'Draft — not published' : undefined}>
          <span className="block truncate font-mono text-[11px] font-semibold">{span(shift.starts_at, shift.ends_at)}</span>
          <span className="block truncate text-[10px] text-zinc-400">{shift.role || 'Shift'}</span>
        </button>
        {!removed && markLine(shift)}
        {recentShiftIds?.has(shift.id) && !mark && <span className="mt-0.5 block text-[9px] font-medium text-emerald-300">Just changed</span>}
        {huumeToggle(shift)}
      </div>
    )
  }

  return (
    <div className="min-h-0 min-w-0 flex-1 overflow-auto bg-zinc-950 p-3 md:p-4" role="table" aria-label="Week schedule by person">
      <div className="min-w-[760px]">
        <div role="row" className="sticky top-0 z-10 grid border-b border-zinc-800 bg-zinc-950" style={columns}>
          <div role="columnheader" className="px-2 pb-2 text-[10px] font-semibold uppercase tracking-wide text-zinc-500">Person</div>
          {days.map((date) => (
            <div role="columnheader" key={date} className="border-l border-zinc-900 px-2 pb-2 text-[11px] font-semibold uppercase tracking-wide text-zinc-400">{fmtDayLabel(date)}</div>
          ))}
        </div>

        {(days.some((date) => openOn(date).length > 0) || openPreviews.length > 0) && (
          <div role="row" className="grid border-b border-zinc-800 bg-amber-500/[0.04]" style={columns}>
            <div role="rowheader" className="px-2 py-2 text-[11px] font-medium text-amber-200">Open seats</div>
            {days.map((date) => (
              <div role="cell" key={date} className="space-y-1 border-l border-zinc-900 p-1">
                {openOn(date).map((shift) => (
                  <div key={shift.id} className={chipFrame(shift, 'group relative rounded border border-amber-400/40 bg-amber-500/10 px-1.5 py-1 text-amber-100')}>
                    <button type="button" onClick={() => onOpenShift(shift)} className="block w-full min-w-0 text-left">
                      <span className="block truncate font-mono text-[11px] font-semibold">{span(shift.starts_at, shift.ends_at)}</span>
                      <span className="block truncate text-[10px] text-amber-200/80">{shift.role || 'Shift'} · {shift.required_staff - shift.assignments.length} open</span>
                    </button>
                    {markLine(shift)}
                    {/* A partly staffed shift is selectable from its people's rows. */}
                    {shift.assignments.length === 0 && huumeToggle(shift)}
                  </div>
                ))}
                {openPreviews.filter((preview) => day(preview.starts_at) === date).map((preview) => (
                  <div key={preview.id} role="img" aria-label={`Proposed open ${preview.role} ${span(preview.starts_at, preview.ends_at)}`} className="rounded border border-dashed border-amber-400/60 bg-amber-500/[0.06] px-1.5 py-1 text-amber-100">
                    <span className="block truncate font-mono text-[11px] font-semibold">{span(preview.starts_at, preview.ends_at)}</span>
                    <span className="block truncate text-[10px] text-amber-200/80">{preview.role} · {preview.open} unfilled</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}

        {ordered.map((row) => {
          const minutes = minutesFor(row.id)
          const delta = proposedMinutesFor(row.id)
          const selected = selectedEmployeeId === row.id
          const dimmed = !!selectedEmployeeId && !selected
          return (
            <div role="row" key={row.id} className={`grid border-b border-zinc-900 ${selected ? 'bg-emerald-500/[0.05]' : ''} ${dimmed ? 'opacity-50' : ''}`} style={columns}>
              <div role="rowheader" className="min-w-0 px-2 py-2">
                <button
                  type="button"
                  onClick={() => onSelectEmployee?.(selected ? null : row.id)}
                  disabled={!onSelectEmployee || row.id.startsWith('name:')}
                  className="block w-full min-w-0 text-left"
                  aria-pressed={selected}
                >
                  <span className="block truncate text-xs font-medium text-zinc-100">{row.name}</span>
                  <span className="block truncate font-mono text-[10px] text-zinc-500">
                    {hoursLabel(minutes)}
                    {delta !== 0 && <span className="text-sky-300"> → {hoursLabel(minutes + delta)}</span>}
                    {row.title ? <span className="font-sans"> · {row.title}</span> : null}
                  </span>
                </button>
              </div>
              {days.map((date) => {
                const cells = cellsFor(row.id, date)
                return (
                  <div role="cell" key={date} className="group/cell relative min-h-[44px] space-y-1 border-l border-zinc-900 p-1">
                    {cells.map(renderCell)}
                    {!cells.length && !row.id.startsWith('name:') && (
                      <button
                        type="button"
                        onClick={() => onCreateFor(date, row.id)}
                        aria-label={`Add a shift for ${row.name} on ${fmtDayLabel(date)}`}
                        className="flex h-full min-h-[36px] w-full items-center justify-center rounded text-zinc-700 opacity-0 hover:bg-white/[0.03] hover:text-zinc-300 focus:opacity-100 group-hover/cell:opacity-100"
                      >
                        <Plus className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                )
              })}
            </div>
          )
        })}
        {!ordered.length && <p className="px-2 py-6 text-xs text-zinc-500">Nobody is assigned to this store yet.</p>}
      </div>
    </div>
  )
}

function startOf(cell: Cell): string {
  return cell.kind === 'shift' ? cell.shift.starts_at : cell.startsAt
}
