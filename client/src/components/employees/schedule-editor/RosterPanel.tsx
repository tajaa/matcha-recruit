import { Search, UserRound, Users, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useDraggable, useDroppable } from '@dnd-kit/core'
import type { RosterEmployee, RosterFlags } from '../../../types/employeeSchedule'

interface RosterPanelProps {
  roster: RosterEmployee[]
  rosterFlags: RosterFlags | null
  selectedEmployeeId: string | null
  onSelectEmployee(employeeId: string | null): void
  requiredJobId?: string | null
  requiredJobDate?: string | null
}

function EmployeeRow({ employee, flags, selected, requiredJobId, requiredJobDate, onSelect }: {
  employee: RosterEmployee
  flags?: { overdue_training: number; lapsed_credentials: number; warnings?: string[]; blocking_credentials?: string[] }
  selected: boolean
  requiredJobId?: string | null
  requiredJobDate?: string | null
  onSelect(): void
}) {
  const blockedReasons = flags?.blocking_credentials ?? []
  const blocked = blockedReasons.length > 0
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `roster-${employee.id}`,
    data: { kind: 'roster-employee', employeeId: employee.id },
    disabled: blocked,
  })
  const warnings = (flags?.overdue_training ?? 0) + (flags?.lapsed_credentials ?? 0)
  const effectiveQualifications = employee.job_qualifications
  const unqualified = !!requiredJobId && (effectiveQualifications
    ? !effectiveQualifications.some((qualification) => (
      qualification.job_id === requiredJobId
      && (!requiredJobDate || qualification.qualified_from == null || qualification.qualified_from <= requiredJobDate)
      && (!requiredJobDate || qualification.qualified_until == null || qualification.qualified_until >= requiredJobDate)
    ))
    : !employee.job_ids.includes(requiredJobId))
  return (
    <button
      ref={setNodeRef}
      type="button"
      {...listeners}
      {...attributes}
      onClick={onSelect}
      disabled={blocked}
      title={blocked ? blockedReasons.join('; ') : undefined}
      className={`flex w-full items-center gap-2 rounded-lg border px-2.5 py-2 text-left transition-colors ${blocked ? 'cursor-not-allowed border-red-500/30 bg-red-500/5 opacity-70' : selected ? 'border-emerald-500/50 bg-emerald-500/10' : 'border-transparent bg-zinc-900/60 hover:border-zinc-700 hover:bg-zinc-900'} ${isDragging ? 'opacity-40' : ''}`}
      aria-label={blocked ? `${employee.name} cannot be scheduled: ${blockedReasons.join('; ')}` : `Drag ${employee.name} to a shift`}
    >
      <UserRound className="h-4 w-4 shrink-0 text-zinc-500" />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-xs text-zinc-200">{employee.name}</span>
        <span className="block truncate text-[10px] text-zinc-600">{employee.job_title || employee.department || 'Employee'}</span>
      </span>
      {blocked && <span className="text-[10px] text-red-400" title={blockedReasons.join('; ')}>Blocked</span>}
      {!blocked && warnings > 0 && <span className="text-[10px] text-amber-400" title={flags?.warnings?.join('; ') || 'Training or credential lapse'}>{warnings}</span>}
      {unqualified && <span className="text-[10px] text-amber-400" title="Not qualified for this job">Not qualified</span>}
    </button>
  )
}

export default function RosterPanel({ roster, rosterFlags, selectedEmployeeId, onSelectEmployee, requiredJobId, requiredJobDate }: RosterPanelProps) {
  const [query, setQuery] = useState('')
  const { setNodeRef, isOver } = useDroppable({ id: 'schedule-unassign', data: { kind: 'unassign' } })
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return roster
    return roster.filter((employee) => [employee.name, employee.job_title, employee.department].filter(Boolean).join(' ').toLowerCase().includes(needle))
  }, [query, roster])

  return (
    <aside className="flex min-h-0 w-full shrink-0 flex-col border-b border-zinc-900 bg-zinc-950 p-3 lg:h-full lg:w-64 lg:border-b-0 lg:border-r lg:p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs font-medium text-zinc-300"><Users className="h-4 w-4 text-zinc-500" /> Roster</div>
        {selectedEmployeeId && <button onClick={() => onSelectEmployee(null)} className="text-zinc-600 hover:text-zinc-200" aria-label="Clear selected employee"><X className="h-3.5 w-3.5" /></button>}
      </div>
      <label className="relative mb-3 block">
        <Search className="pointer-events-none absolute left-2 top-2 h-3.5 w-3.5 text-zinc-600" />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find an employee" className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-7 py-1.5 text-xs text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-zinc-600" />
      </label>
      <div className="min-h-0 max-h-64 space-y-1 overflow-y-auto pr-1 lg:max-h-none lg:flex-1">
        {filtered.map((employee) => <EmployeeRow key={employee.id} employee={employee} flags={rosterFlags?.[employee.id]} requiredJobId={requiredJobId} requiredJobDate={requiredJobDate} selected={employee.id === selectedEmployeeId} onSelect={() => onSelectEmployee(employee.id === selectedEmployeeId ? null : employee.id)} />)}
        {filtered.length === 0 && <p className="px-2 py-3 text-xs text-zinc-600">No employees match.</p>}
      </div>
      <div ref={setNodeRef} className={`mt-3 rounded-lg border border-dashed px-2.5 py-2 text-center text-[10px] text-zinc-600 ${isOver ? 'border-red-400/70 bg-red-500/10 text-red-300' : 'border-zinc-800'}`}>
        Drop here to unassign
      </div>
      <p className="mt-2 hidden text-[10px] leading-relaxed text-zinc-700 lg:block">Drag a person onto a shift. Click a person, then click a shift for keyboard-friendly assignment.</p>
    </aside>
  )
}
