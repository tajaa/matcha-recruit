import { useState } from 'react'
import { Check, Plus, Sparkles } from 'lucide-react'
import type { ScheduleReview, Shift } from '../../../types/employeeSchedule'
import { fmtTime } from '../../../types/employeeSchedule'
import type { ShiftMark } from './boardMarks'
import type { PreviewShift } from './reviewVerdict'

/** The Week view on a phone: pick a day, read its shifts as cards. A seven-
 *  column grid needs ~760px; at phone width it is a sideways scroll through
 *  cells too narrow to tap, so the same facts are laid out one day at a time.
 *  Nothing here depends on hover — every control is always visible. */
export interface DayAgendaProps {
  days: string[]
  shifts: Shift[]
  review?: ScheduleReview | null
  previewShifts?: PreviewShift[]
  marks?: ReadonlyMap<string, ShiftMark>
  recentShiftIds?: ReadonlySet<string>
  huumeSelectedShiftIds: ReadonlySet<string>
  onOpenShift(shift: Shift): void
  onToggleHuumeSelection(shift: Shift): void
  onCreateOn?(date: string): void
}

const dayOf = (iso: string) => iso.slice(0, 10)
const span = (startsAt: string, endsAt: string) => `${fmtTime(startsAt)}–${fmtTime(endsAt)}`
const ADD_OPS = new Set(['assign', 'reassign', 'swap', 'create'])

function dayParts(date: string) {
  const value = new Date(`${date}T00:00:00Z`)
  return {
    weekday: value.toLocaleDateString('en-US', { weekday: 'short', timeZone: 'UTC' }),
    long: value.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric', timeZone: 'UTC' }),
    date: `${value.getUTCMonth() + 1}/${value.getUTCDate()}`,
  }
}

function initialDay(days: string[], shifts: Shift[], proposedDays: ReadonlySet<string>): string {
  // A pending proposal is what the manager came to look at: open on its first day.
  const proposed = days.find((date) => proposedDays.has(date))
  if (proposed) return proposed
  const today = new Date()
  const local = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
  if (days.includes(local)) return local
  return days.find((date) => shifts.some((shift) => dayOf(shift.starts_at) === date)) ?? days[0]
}

export default function DayAgenda({
  days, shifts, review, previewShifts = [], marks, recentShiftIds, huumeSelectedShiftIds,
  onOpenShift, onToggleHuumeSelection, onCreateOn,
}: DayAgendaProps) {
  const [picked, setPicked] = useState<{ week: string; date: string } | null>(null)
  // Days a pending proposal touches: an outlined shift, or a new one it would create.
  const proposedDays = new Set<string>([
    ...shifts.filter((shift) => marks?.has(shift.id)).map((shift) => dayOf(shift.starts_at)),
    ...previewShifts.map((preview) => dayOf(preview.starts_at)),
  ])
  // A new week resets the pick; until then the week opens on the proposal's
  // first day, else today, else its first busy day.
  const selected = picked && picked.week === days[0] && days.includes(picked.date) ? picked.date : initialDay(days, shifts, proposedDays)

  // Who a proposal adds to / takes off each existing shift.
  const added = new Map<string, string[]>()
  const removed = new Set<string>()
  if (review && review.kind !== 'week_draft') {
    for (const item of review.assignments) {
      if (item.verdict === 'blocked' || !item.shift_id || !item.employee_id) continue
      if (item.op === 'unassign') { removed.add(`${item.shift_id}:${item.employee_id}`); continue }
      if (!ADD_OPS.has(item.op)) continue
      const list = added.get(item.shift_id) ?? []
      list.push(item.employee_name || 'someone')
      added.set(item.shift_id, list)
    }
  }

  const live = (date: string) => shifts.filter((shift) => dayOf(shift.starts_at) === date)
  const openCount = (date: string) => live(date).filter((shift) => shift.status !== 'cancelled' && shift.assignments.length < shift.required_staff).length
  const dayShifts = live(selected)
  const dayPreviews = previewShifts.filter((preview) => dayOf(preview.starts_at) === selected)
  const items: Array<{ start: string; shift?: Shift; preview?: PreviewShift }> = [
    ...dayShifts.map((shift) => ({ start: shift.starts_at, shift })),
    ...dayPreviews.map((preview) => ({ start: preview.starts_at, preview })),
  ].sort((a, b) => (a.start < b.start ? -1 : a.start > b.start ? 1 : 0))
  const parts = dayParts(selected)
  const unfilled = openCount(selected)

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col bg-zinc-950" aria-label="Day schedule">
      <div role="tablist" aria-label="Day" className="flex shrink-0 gap-1.5 overflow-x-auto border-b border-white/[0.06] px-3 py-2">
        {days.map((date) => {
          const { weekday, date: short } = dayParts(date)
          const active = date === selected
          const count = live(date).length + previewShifts.filter((preview) => dayOf(preview.starts_at) === date).length
          return (
            <button
              key={date}
              type="button"
              role="tab"
              aria-selected={active}
              aria-label={`${dayParts(date).long}, ${count} ${count === 1 ? 'shift' : 'shifts'}${proposedDays.has(date) ? ', has proposed changes' : ''}`}
              onClick={() => setPicked({ week: days[0], date })}
              className={`relative flex min-w-[3.25rem] shrink-0 flex-col items-center rounded-lg border px-2 py-1.5 ${active ? 'border-emerald-500/60 bg-emerald-500/10 text-emerald-100' : proposedDays.has(date) ? 'border-sky-400/60 text-sky-100' : 'border-white/[0.08] text-zinc-300'}`}
            >
              <span className="text-[11px] font-medium">{weekday}</span>
              <span className="font-mono text-[10px] text-zinc-500">{short}</span>
              {openCount(date) > 0 && <span className="absolute right-1 top-1 h-1.5 w-1.5 rounded-full bg-amber-400" aria-hidden />}
              {proposedDays.has(date) && <span className="absolute left-1 top-1 h-1.5 w-1.5 rounded-full bg-sky-400" aria-hidden />}
            </button>
          )
        })}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-6 pt-3">
        <div className="mb-3 flex items-center gap-2">
          <div className="min-w-0 flex-1">
            <h3 className="truncate text-sm font-semibold text-zinc-100">{parts.long}</h3>
            <p className="text-[11px] text-zinc-500">
              {dayShifts.length} {dayShifts.length === 1 ? 'shift' : 'shifts'}
              {unfilled > 0 && <span className="text-amber-300"> · {unfilled} unfilled</span>}
            </p>
          </div>
          {onCreateOn && (
            <button type="button" onClick={() => onCreateOn(selected)} className="inline-flex items-center gap-1 rounded-lg border border-white/[0.1] px-3 py-2 text-xs text-zinc-200 active:bg-white/[0.06]">
              <Plus className="h-4 w-4" /> Add shift
            </button>
          )}
        </div>

        <ul className="space-y-2">
          {items.map((item) => item.preview
            ? <PreviewCard key={`p-${item.preview.id}`} preview={item.preview} />
            : <ShiftCard
                key={item.shift!.id}
                shift={item.shift!}
                mark={marks?.get(item.shift!.id)}
                adds={added.get(item.shift!.id) ?? []}
                removed={removed}
                recent={recentShiftIds?.has(item.shift!.id) ?? false}
                selectedForHuume={huumeSelectedShiftIds.has(item.shift!.id)}
                onOpen={() => onOpenShift(item.shift!)}
                onToggleHuume={() => onToggleHuumeSelection(item.shift!)}
              />)}
        </ul>
        {!items.length && <p className="rounded-lg border border-dashed border-white/[0.08] px-3 py-6 text-center text-xs text-zinc-500">Nothing scheduled this day.</p>}
      </div>
    </div>
  )
}

function ShiftCard({ shift, mark, adds, removed, recent, selectedForHuume, onOpen, onToggleHuume }: {
  shift: Shift
  mark?: ShiftMark
  adds: string[]
  removed: ReadonlySet<string>
  recent: boolean
  selectedForHuume: boolean
  onOpen(): void
  onToggleHuume(): void
}) {
  const open = Math.max(shift.required_staff - shift.assignments.length, 0)
  const frame = mark
    ? mark.warn ? 'border-amber-400/70 ring-1 ring-amber-400/40' : 'border-sky-400/70 ring-1 ring-sky-400/40'
    : recent ? 'border-emerald-400/60 ring-1 ring-emerald-400/30'
      : selectedForHuume ? 'border-emerald-400' : 'border-white/[0.08]'
  return (
    <li className={`relative rounded-xl border bg-zinc-900/80 ${frame} ${shift.status === 'cancelled' ? 'opacity-60' : ''}`}>
      <button type="button" onClick={onOpen} className="block w-full px-3 py-2.5 pr-12 text-left active:bg-white/[0.03]">
        <span className="flex items-baseline gap-2">
          <span className={`font-mono text-sm font-semibold text-zinc-100 ${shift.status === 'cancelled' ? 'line-through' : ''}`}>{span(shift.starts_at, shift.ends_at)}</span>
          <span className="truncate text-xs text-zinc-400">{shift.role || 'Shift'}</span>
        </span>
        <span className="mt-1 flex flex-wrap items-center gap-1">
          {shift.assignments.map((assignment) => {
            const leaving = removed.has(`${shift.id}:${assignment.employee_id}`)
            return (
              <span key={assignment.employee_id} className={`rounded-md px-1.5 py-0.5 text-[11px] ${leaving ? 'bg-red-500/10 text-red-200 line-through' : 'bg-zinc-800 text-zinc-200'}`}>{assignment.name}</span>
            )
          })}
          {adds.map((name, index) => (
            <span key={`${name}-${index}`} className="rounded-md border border-dashed border-sky-400/70 px-1.5 py-0.5 text-[11px] text-sky-100">+ {name}</span>
          ))}
          {open > 0 && <span className="rounded-md bg-amber-500/10 px-1.5 py-0.5 text-[11px] text-amber-200">{open} open</span>}
          {shift.status === 'draft' && <span className="text-[10px] uppercase tracking-wide text-zinc-500">draft</span>}
        </span>
        {/* Adds and removals are already drawn on the names above; this line
            carries the rest (retime, cancel, refused, stays open). */}
        {mark && mark.chips.some((chip) => chip.tone !== 'add' && chip.tone !== 'remove') && (
          <span aria-label="Proposed by Huume" className="mt-1 block text-[11px] text-sky-200" title={mark.chips.map((chip) => chip.title || chip.label).join('\n')}>
            {mark.chips.filter((chip) => chip.tone !== 'add' && chip.tone !== 'remove').map((chip) => chip.label).join(' · ')}
          </span>
        )}
        {recent && !mark && <span className="mt-1 block text-[11px] text-emerald-300">Just changed</span>}
      </button>
      <button
        type="button"
        onClick={onToggleHuume}
        aria-pressed={selectedForHuume}
        aria-label={`${selectedForHuume ? 'Remove' : 'Select'} ${shift.role || 'shift'} for Huume`}
        className={`absolute right-1.5 top-1.5 rounded-lg p-2 ${selectedForHuume ? 'bg-emerald-400 text-zinc-950' : 'text-zinc-500 active:bg-emerald-500/15'}`}
      >
        {selectedForHuume ? <Check className="h-4 w-4" /> : <Sparkles className="h-4 w-4" />}
      </button>
    </li>
  )
}

function PreviewCard({ preview }: { preview: PreviewShift }) {
  const label = `Proposed ${preview.role} ${span(preview.starts_at, preview.ends_at)}: ${preview.names.length ? preview.names.join(', ') : 'nobody'}${preview.open ? `, ${preview.open} open` : ''}`
  return (
    <li role="img" aria-label={label} title={preview.reasons.join('\n') || undefined} className={`rounded-xl border border-dashed px-3 py-2.5 ${preview.open ? 'border-amber-400/60 bg-amber-500/[0.05]' : 'border-sky-400/60 bg-sky-500/[0.06]'}`}>
      <span className="flex items-baseline gap-2">
        <span className="font-mono text-sm font-semibold text-sky-100">+ {span(preview.starts_at, preview.ends_at)}</span>
        <span className="truncate text-xs text-zinc-400">{preview.role}</span>
      </span>
      <span className="mt-1 flex flex-wrap gap-1">
        {preview.names.map((name) => <span key={name} className="rounded-md border border-dashed border-sky-400/60 px-1.5 py-0.5 text-[11px] text-sky-100">{name}</span>)}
        {preview.open > 0 && <span className="rounded-md bg-amber-500/10 px-1.5 py-0.5 text-[11px] text-amber-200">{preview.open} unfilled</span>}
      </span>
    </li>
  )
}
