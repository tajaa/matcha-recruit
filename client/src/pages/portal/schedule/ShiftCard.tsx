import { useState } from 'react'
import { Check, Loader2, LogOut, Repeat } from 'lucide-react'
import { useToast } from '../../../components/ui'
import { createMyRequest } from '../../../api/employees/employeeSchedule'
import type { Shift, ShiftAssignment } from '../../../types/employeeSchedule'
import { errorMessage, fmtTime } from '../../../types/employeeSchedule'
import { formatShift, inputCls } from './shared'

/** One of the employee's own shifts, with the inline swap / pickup offer form. */
export function ShiftCard({
  shift,
  coworkers,
  teamShifts,
  onChanged,
}: {
  shift: Shift
  coworkers: { id: string; name: string }[]
  teamShifts: Shift[]
  onChanged: () => void
}) {
  const { toast } = useToast()
  const [mode, setMode] = useState<'swap' | 'pickup' | null>(null)
  const [targetEmployeeId, setTargetEmployeeId] = useState('')
  const [counterShiftId, setCounterShiftId] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const targetShifts = teamShifts.filter((candidate) => (
    candidate.id !== shift.id
    && candidate.assignments.some((assignment) => assignment.employee_id === targetEmployeeId)
  ))

  async function submit() {
    if (!mode) return
    setBusy(true)
    try {
      if (mode === 'swap' && !targetEmployeeId) {
        toast('Choose a coworker for the swap', 'error')
        return
      }
      if (mode === 'swap' && !counterShiftId) {
        toast('Choose the shift you want to trade for', 'error')
        return
      }
      await createMyRequest({ request_type: mode, shift_id: shift.id, target_employee_id: targetEmployeeId || null, counter_shift_id: counterShiftId || null, reason: reason.trim() || null })
      setMode(null)
      setReason('')
      setTargetEmployeeId('')
      setCounterShiftId('')
      toast(`${mode === 'swap' ? 'Swap' : 'Pickup'} offer sent for confirmation`, 'success')
      onChanged()
    } catch (err) {
      toast(errorMessage(err), 'error')
    } finally { setBusy(false) }
  }

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-zinc-100 flex items-center gap-1.5">
            {fmtTime(shift.starts_at)}–{fmtTime(shift.ends_at)}
            {shift.kind === 'training' && (
              <span className="px-1.5 py-0.5 rounded-full border text-[9px] font-semibold uppercase text-sky-400 bg-sky-500/10 border-sky-500/20">Training</span>
            )}
          </div>
          {(shift.role || shift.department) && <div className="text-[11px] text-zinc-500 truncate">{[shift.role, shift.department].filter(Boolean).join(' · ')}</div>}
          {shift.notes?.trim() && <p className="mt-1 text-[11px] text-zinc-400 whitespace-pre-wrap">Schedule note: {shift.notes.trim()}</p>}
          <AssignmentGuidance assignment={shift.assignments[0]} />
        </div>
        <button onClick={() => { setMode(mode === 'swap' ? null : 'swap'); setCounterShiftId('') }} className="inline-flex items-center gap-1 text-[11px] text-zinc-400 hover:text-zinc-100"><Repeat className="h-3.5 w-3.5" /> Swap</button>
        <button onClick={() => setMode(mode === 'pickup' ? null : 'pickup')} className="inline-flex items-center gap-1 text-[11px] text-zinc-400 hover:text-zinc-100"><LogOut className="h-3.5 w-3.5" /> Offer pickup</button>
      </div>
      {mode && (
        <div className="mt-2 flex items-center gap-2 flex-wrap border-t border-zinc-800 pt-2">
          {mode === 'swap' && <select value={targetEmployeeId} onChange={(e) => { setTargetEmployeeId(e.target.value); setCounterShiftId('') }} className={`${inputCls} max-w-[180px]`}><option value="">Swap with…</option>{coworkers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>}
          {mode === 'swap' && <select value={counterShiftId} disabled={!targetEmployeeId} onChange={(e) => setCounterShiftId(e.target.value)} className={`${inputCls} max-w-[220px] disabled:opacity-40`}><option value="">Trade for their shift…</option>{targetShifts.map((candidate) => <option key={candidate.id} value={candidate.id}>{formatShift(candidate.starts_at, candidate.ends_at, candidate.role, candidate.department)}</option>)}</select>}
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder={`Reason for ${mode} (optional)`} className={inputCls} />
          <button onClick={submit} disabled={busy} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs rounded-lg px-2.5 py-1.5 shrink-0 disabled:opacity-50">{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Send</button>
        </div>
      )}
    </div>
  )
}

export function AssignmentGuidance({ assignment }: { assignment: ShiftAssignment | undefined }) {
  if (!assignment) return null
  const guidance = assignment.compliance_guidance
  const summary = guidance?.summary
  const requirements = guidance?.requirements ?? []
  const active = requirements.filter((requirement) => !requirement.waived)
  const waived = requirements.some((requirement) => requirement.waived && requirement.kind === 'meal')
  // Break times a manager staggered and saved. Schedule times are wall-clock,
  // so the characters are already this location's clock — never convert.
  const planned = assignment.planned_breaks ?? []
  return (
    <div className="mt-1.5 space-y-1 text-[11px]">
      {summary && <p className={guidance?.status === 'unmapped' || guidance?.status === 'error' ? 'text-amber-300' : 'text-sky-300'}>{summary}</p>}
      {!summary && active.length > 0 && <p className="text-sky-300">{active.map((requirement) => `${requirement.duration_minutes}-minute ${requirement.paid ? 'paid' : 'unpaid'} ${requirement.kind} break`).join(' · ')}</p>}
      {waived && <p className="text-emerald-300">Meal-break waiver applies to this shift.</p>}
      {planned.length > 0 && <p className="text-sky-300">Scheduled break{planned.length > 1 ? 's' : ''}: {planned.map((entry) => `${entry.start_local.slice(11, 16)} (${entry.duration_minutes} min ${entry.kind})`).join(' · ')}</p>}
      {assignment.manager_note && <p className="text-zinc-400">Manager note: {assignment.manager_note}</p>}
    </div>
  )
}
