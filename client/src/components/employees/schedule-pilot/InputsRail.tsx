import { memo, useMemo, useState } from 'react'
import { useDraggable, useDroppable } from '@dnd-kit/core'
import { AlertTriangle, BriefcaseBusiness, CalendarCog, Search, Sparkles, UserRound, X } from 'lucide-react'
import { LABEL } from '../../ui'
import type { LocationScheduleProfile, PlanningInputs, PlanningRosterPerson, RosterEmployee, RosterFlags } from '../../../types/employeeSchedule'
import { WEEK_RULE_LABELS, fmtDayLabel, fmtTime } from '../../../types/employeeSchedule'
import { SETUP_KICKOFF_PROMPT } from '../../../hooks/employees/useScheduleHuumeThread'
import { LoadBar, POLICY_WEEKLY_MINUTES } from './LoadLedger'
import { hoursLabel } from './reviewShape'

export interface InputsRailProps {
  inputs: PlanningInputs | null
  loading: boolean
  roster: RosterEmployee[]
  rosterFlags: RosterFlags | null
  selectedEmployeeId: string | null
  onSelectEmployee(employeeId: string | null): void
  requiredJobId?: string | null
  requiredJobDate?: string | null
  weekRules: LocationScheduleProfile['week_rules'] | null
  locationName: string
  credentialsEnabled: boolean
  onOpenWeekSetup(): void
  onOpenJobs(): void
  onAskHuume(text: string): void
  onShowShift(shiftId: string): void
}

type Person = {
  employee: RosterEmployee
  planning: PlanningRosterPerson | null
  flags?: RosterFlags[string]
}

function isUnqualified(employee: RosterEmployee, requiredJobId?: string | null, requiredJobDate?: string | null): boolean {
  if (!requiredJobId) return false
  const qualifications = employee.job_qualifications
  if (!qualifications) return !employee.job_ids.includes(requiredJobId)
  return !qualifications.some((qualification) => (
    qualification.job_id === requiredJobId
    && (!requiredJobDate || qualification.qualified_from == null || qualification.qualified_from <= requiredJobDate)
    && (!requiredJobDate || qualification.qualified_until == null || qualification.qualified_until >= requiredJobDate)
  ))
}

function shortRange(start: string, end: string): string {
  const s = fmtDayLabel(start).split(' ')[1]
  const e = fmtDayLabel(end).split(' ')[1]
  return s === e ? s : `${s}–${e}`
}

const AVAILABILITY_DOT: Record<string, { className: string; title: string }> = {
  windows: { className: 'bg-emerald-400', title: 'Availability confirmed (windows)' },
  always_available: { className: 'bg-sky-400', title: 'Always available' },
  unconfirmed: { className: 'bg-amber-400', title: 'Availability unconfirmed — the planner will not place them' },
}

function PersonRow({ person, selected, requiredJobId, requiredJobDate, policyMinutes, onSelect }: {
  person: Person
  selected: boolean
  requiredJobId?: string | null
  requiredJobDate?: string | null
  policyMinutes: number
  onSelect(): void
}) {
  const { employee, planning, flags } = person
  const blockedReasons = flags?.blocking_credentials ?? []
  const blocked = blockedReasons.length > 0
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `roster-${employee.id}`,
    data: { kind: 'roster-employee', employeeId: employee.id },
    disabled: blocked,
  })
  const warnings = (flags?.overdue_training ?? 0) + (flags?.lapsed_credentials ?? 0)
  const unqualified = isUnqualified(employee, requiredJobId, requiredJobDate)
  const dot = AVAILABILITY_DOT[planning?.availability_state ?? ''] ?? { className: 'bg-zinc-600', title: 'Availability unknown' }
  const load = planning?.load
  return (
    <button
      ref={setNodeRef}
      type="button"
      {...listeners}
      {...attributes}
      onClick={onSelect}
      disabled={blocked}
      title={blocked ? blockedReasons.join('; ') : undefined}
      aria-pressed={selected}
      className={`w-full rounded-lg border px-2.5 py-2 text-left transition-colors ${blocked ? 'cursor-not-allowed border-red-500/30 bg-red-500/5 opacity-70' : selected ? 'border-emerald-500/50 bg-emerald-500/10' : 'border-transparent bg-zinc-900/60 hover:border-zinc-700 hover:bg-zinc-900'} ${isDragging ? 'opacity-40' : ''}`}
      aria-label={blocked ? `${employee.name} cannot be scheduled: ${blockedReasons.join('; ')}` : `Drag ${employee.name} to a shift`}
    >
      <span className="flex items-center gap-2">
        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot.className}`} title={dot.title} />
        <span className="min-w-0 flex-1 truncate text-xs text-zinc-200">{employee.name}</span>
        {blocked && <span className="text-[10px] text-red-400">Blocked</span>}
        {!blocked && warnings > 0 && <span className="text-[10px] text-amber-400" title={flags?.warnings?.join('; ') || 'Training or credential lapse'}>{warnings}</span>}
        {unqualified && <span className="text-[10px] text-amber-400" title="Not qualified for this job">Not qualified</span>}
      </span>
      <span className="mt-1.5 block">
        <LoadBar
          compact
          name={employee.name}
          minutes={load?.minutes ?? 0}
          capMinutes={planning?.caps.max_weekly_minutes ?? null}
          allowOvertime={planning?.caps.allow_overtime ?? false}
          policyMinutes={policyMinutes}
        />
      </span>
      <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-zinc-500">
        <span className="font-mono tabular-nums">{load ? `${load.shifts} shift${load.shifts === 1 ? '' : 's'} · ${load.days.length} day${load.days.length === 1 ? '' : 's'}` : '—'}</span>
        <span className="truncate">{planning?.jobs.length ? planning.jobs.join(', ') : (employee.job_title || employee.department || 'No job on file')}</span>
        {planning?.time_away.map((away) => (
          <span key={away.start} className="rounded bg-amber-500/10 px-1 text-amber-300">away {shortRange(away.start, away.end)}</span>
        ))}
      </span>
    </button>
  )
}

function Section({ label, count, children, action }: { label: string; count?: number | string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="border-b border-white/[0.06] px-3 py-3">
      <div className="mb-2 flex items-center gap-2">
        <span className={LABEL}>{label}</span>
        {count !== undefined && <span className="font-mono text-[10px] tabular-nums text-zinc-400">{count}</span>}
        <span className="ml-auto">{action}</span>
      </div>
      {children}
    </section>
  )
}

/** The left column of the Schedule Pilot: what a scheduler should see before
 *  deciding who works. One people list (draggable — this replaces the old
 *  roster panel) carrying each person's load against the policy tick, the
 *  open seats, the house policy next to whether the state's law is on file,
 *  and the week-setup status. Everything a good scheduler has in their head;
 *  now also what Huume reads (`get_schedule_overview.roster_load`). */
function InputsRail({
  inputs, loading, roster, rosterFlags, selectedEmployeeId, onSelectEmployee, requiredJobId, requiredJobDate,
  weekRules, locationName, credentialsEnabled, onOpenWeekSetup, onOpenJobs, onAskHuume, onShowShift,
}: InputsRailProps) {
  const [query, setQuery] = useState('')
  const { setNodeRef, isOver } = useDroppable({ id: 'schedule-unassign', data: { kind: 'unassign' } })
  const policyMinutes = inputs?.policy.default_weekly_cap_minutes ?? POLICY_WEEKLY_MINUTES

  const people = useMemo<Person[]>(() => {
    const planningById = new Map((inputs?.roster ?? []).map((person) => [person.employee_id, person]))
    const merged = roster.map((employee) => ({ employee, planning: planningById.get(employee.id) ?? null, flags: rosterFlags?.[employee.id] }))
    merged.sort((a, b) => (b.planning?.load.minutes ?? 0) - (a.planning?.load.minutes ?? 0) || a.employee.name.localeCompare(b.employee.name))
    const needle = query.trim().toLowerCase()
    if (!needle) return merged
    return merged.filter(({ employee, planning }) => [employee.name, employee.job_title, employee.department, ...(planning?.jobs ?? [])]
      .filter(Boolean).join(' ').toLowerCase().includes(needle))
  }, [inputs, roster, rosterFlags, query])

  const openByDay = useMemo(() => {
    const groups = new Map<string, PlanningInputs['open_slots']>()
    for (const slot of inputs?.open_slots ?? []) {
      const day = slot.starts_at.slice(0, 10)
      groups.set(day, [...(groups.get(day) ?? []), slot])
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [inputs])
  const openSeats = (inputs?.open_slots ?? []).reduce((total, slot) => total + slot.open, 0)
  const jurisdiction = inputs?.jurisdiction
  const jurisdictionTone = !jurisdiction ? 'border-white/[0.08] text-zinc-400'
    : jurisdiction.status === 'curated' || jurisdiction.status === 'catalog' ? 'border-emerald-500/30 bg-emerald-500/[0.06] text-emerald-200'
    : jurisdiction.status === 'unavailable' ? 'border-red-500/30 bg-red-500/[0.06] text-red-200'
    : 'border-amber-500/30 bg-amber-500/[0.06] text-amber-200'

  return (
    <aside className="flex h-full min-h-0 flex-col overflow-y-auto bg-zinc-950" aria-label="Planning inputs">
      <Section
        label="People"
        count={people.length}
        action={selectedEmployeeId
          ? <button onClick={() => onSelectEmployee(null)} className="text-zinc-600 hover:text-zinc-200" aria-label="Clear selected employee"><X className="h-3.5 w-3.5" /></button>
          : null}
      >
        <label className="relative mb-2 block">
          <Search className="pointer-events-none absolute left-2 top-2 h-3.5 w-3.5 text-zinc-600" />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find a person" className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-7 py-1.5 text-xs text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-zinc-600" />
        </label>
        <div className="space-y-1">
          {people.map((person) => (
            <PersonRow
              key={person.employee.id}
              person={person}
              selected={person.employee.id === selectedEmployeeId}
              requiredJobId={requiredJobId}
              requiredJobDate={requiredJobDate}
              policyMinutes={policyMinutes}
              onSelect={() => onSelectEmployee(person.employee.id === selectedEmployeeId ? null : person.employee.id)}
            />
          ))}
          {people.length === 0 && <p className="px-2 py-3 text-xs text-zinc-600">{loading ? 'Loading people…' : 'No one matches.'}</p>}
        </div>
        {inputs?.roster_truncated && <p className="mt-2 text-[10px] text-amber-400">Showing the first {inputs.roster.length} people by load.</p>}
        <div ref={setNodeRef} className={`mt-3 rounded-lg border border-dashed px-2.5 py-2 text-center text-[10px] text-zinc-600 ${isOver ? 'border-red-400/70 bg-red-500/10 text-red-300' : 'border-zinc-800'}`}>
          Drop here to unassign
        </div>
        <p className="mt-2 text-[10px] leading-relaxed text-zinc-700">Drag a person onto a shift, or click a person then a shift. The bar is their hours this week against the {hoursLabel(policyMinutes)} policy tick.</p>
      </Section>

      <Section
        label="Open seats"
        count={openSeats}
        action={openSeats > 0
          ? <button type="button" onClick={() => onAskHuume('Fill the open shifts this week.')} className="inline-flex items-center gap-1 text-[10px] text-emerald-300 hover:text-emerald-100"><Sparkles className="h-3 w-3" /> Fill with Huume</button>
          : null}
      >
        {openByDay.length === 0 ? (
          <p className="text-xs text-zinc-600">{loading ? 'Checking…' : 'Every seat this week is filled.'}</p>
        ) : (
          <ul className="space-y-1.5">
            {openByDay.map(([day, slots]) => (
              <li key={day}>
                <div className="mb-0.5 text-[10px] font-medium uppercase tracking-wide text-zinc-500">{fmtDayLabel(day)}</div>
                <ul className="space-y-0.5">
                  {slots.map((slot) => (
                    <li key={slot.shift_id}>
                      <button type="button" onClick={() => onShowShift(slot.shift_id)} className="flex w-full items-center gap-2 rounded px-1.5 py-1 text-left text-[11px] text-zinc-300 hover:bg-white/[0.04]">
                        <span className="font-mono tabular-nums text-zinc-500">{fmtTime(slot.starts_at)}–{fmtTime(slot.ends_at)}</span>
                        <span className="min-w-0 flex-1 truncate">{slot.role || 'Shift'}</span>
                        <span className="font-mono text-[10px] tabular-nums text-amber-300">{slot.open} open</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section label="Policy & law">
        <div className={`rounded-lg border px-2.5 py-2 text-[11px] leading-snug ${jurisdictionTone}`}>
          {jurisdiction ? jurisdiction.message : loading ? 'Checking which state law is on file…' : 'Law status unknown.'}
        </div>
        <ul className="mt-2 space-y-0.5 text-[11px] text-zinc-400">
          {inputs ? (
            <>
              <li>At least {inputs.policy.min_rest_hours}h rest between shifts</li>
              <li>{inputs.policy.max_shifts_per_day} shift a day unless a split is asked for</li>
              <li>At most {inputs.policy.max_consecutive_days} days in a row</li>
              <li>{hoursLabel(inputs.policy.default_weekly_cap_minutes)} a week unless overtime is allowed</li>
            </>
          ) : <li className="text-zinc-600">—</li>}
        </ul>
        <p className="mt-1.5 text-[10px] text-zinc-600">House policy — what the planner and Huume refuse to break. Not the law: the law is the line above.</p>
      </Section>

      <Section label="Setup">
        {weekRules && !weekRules.established ? (
          <div className="rounded-lg border border-amber-500/25 bg-amber-500/[0.08] px-2.5 py-2 text-[11px] text-amber-100">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-300" />
              <span>{locationName || 'This location'} is still missing {weekRules.missing.map((field) => WEEK_RULE_LABELS[field]).join(', ')}. Huume can’t build a week until these are saved.</span>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <button type="button" onClick={() => onAskHuume(SETUP_KICKOFF_PROMPT)} className="rounded-md border border-amber-400/40 px-2 py-1 text-[10px] font-medium hover:bg-amber-400/10">Set up with Huume</button>
              <button type="button" onClick={onOpenWeekSetup} className="rounded-md border border-amber-400/40 px-2 py-1 text-[10px] font-medium hover:bg-amber-400/10">Fill it in myself</button>
            </div>
          </div>
        ) : (
          <p className="text-[11px] text-zinc-500">{weekRules ? 'Hours, staffing pattern and leader rule are saved.' : 'Checking week setup…'}</p>
        )}
        <div className="mt-2 flex flex-wrap gap-1.5">
          <button type="button" onClick={onOpenWeekSetup} className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-800 px-2.5 py-1.5 text-xs text-zinc-400 hover:text-zinc-100" title="Operating hours, week start, and this location's staffing pattern"><CalendarCog className="h-3.5 w-3.5" /> Week setup</button>
          <button type="button" onClick={onOpenJobs} className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-800 px-2.5 py-1.5 text-xs text-zinc-400 hover:text-zinc-100" title={credentialsEnabled ? 'Configure location jobs and their required credentials' : 'Configure location jobs'}><BriefcaseBusiness className="h-3.5 w-3.5" /> {credentialsEnabled ? 'Jobs & credentials' : 'Jobs'}</button>
        </div>
      </Section>
      <div className="px-3 py-3 text-[10px] text-zinc-700"><UserRound className="mr-1 inline h-3 w-3" />Huume reads this same list before it names anyone.</div>
    </aside>
  )
}

// Memoized for the same reason as BoardPane: one draggable per person.
export default memo(InputsRail)
