import { Check, Loader2, Trash2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { trainingApi, type TrainingRequirement } from '../../../api/training/training'
import { Card } from '../../ui'
import type { RosterEmployee, ScheduleJob, Shift, ShiftPayload } from '../../../types/employeeSchedule'
import { addDays, fmtTime } from '../../../types/employeeSchedule'

export type NewShiftDefaults = {
  date: string
  minute: number
  employeeIds?: string[]
}

interface ShiftInspectorProps {
  shift: Shift | null
  defaults: NewShiftDefaults | null
  /** The location the editor is scoped to — every shift here belongs to it.
   *  No location picker: scope is mandatory and set once, above, not
   *  per-shift (a shift can no longer be moved out of the scoped view). */
  locationId: string
  locationName: string
  roster: RosterEmployee[]
  jobs: ScheduleJob[]
  trainingEnabled: boolean
  readOnly: boolean
  saving: boolean
  onCreate(payload: ShiftPayload): Promise<void>
  onUpdate(payload: Partial<ShiftPayload>): Promise<void>
  onDelete(): Promise<void>
  onClose(): void
}

const input = 'mt-1 w-full rounded-lg border border-zinc-800 bg-zinc-950 px-2.5 py-2 text-xs text-zinc-200 outline-none focus:border-zinc-600 disabled:opacity-50'

function twoDigits(value: number) {
  return String(value).padStart(2, '0')
}

function minuteToTime(minute: number) {
  return `${twoDigits(Math.floor(minute / 60) % 24)}:${twoDigits(minute % 60)}`
}

export default function ShiftInspector({ shift, defaults, locationId, locationName, roster, jobs, trainingEnabled, readOnly, saving, onCreate, onUpdate, onDelete, onClose }: ShiftInspectorProps) {
  const editing = !!shift
  const defaultDate = defaults?.date ?? shift?.starts_at.slice(0, 10) ?? ''
  const [date, setDate] = useState(defaultDate)
  const [start, setStart] = useState(shift ? shift.starts_at.slice(11, 16) : minuteToTime(defaults?.minute ?? 540))
  const [end, setEnd] = useState(shift ? shift.ends_at.slice(11, 16) : minuteToTime((defaults?.minute ?? 540) + 480))
  const [role, setRole] = useState(shift?.role ?? '')
  const [jobId, setJobId] = useState(shift?.job_id ?? '')
  const [department, setDepartment] = useState(shift?.department ?? '')
  const [breakMinutes, setBreakMinutes] = useState(String(shift?.break_minutes ?? 0))
  const [requiredStaff, setRequiredStaff] = useState(String(shift?.required_staff ?? 1))
  const [notes, setNotes] = useState(shift?.notes ?? '')
  const [kind, setKind] = useState<'work' | 'training'>(shift?.kind ?? 'work')
  const [requirementId, setRequirementId] = useState(shift?.training_requirement_id ?? '')
  const [requirements, setRequirements] = useState<TrainingRequirement[]>([])

  useEffect(() => {
    if (!trainingEnabled || editing) return
    trainingApi.listRequirements().then(setRequirements).catch(() => setRequirements([]))
  }, [editing, trainingEnabled])

  if (!shift && !defaults) return null

  const overnight = end <= start
  const assignments = shift?.assignments ?? []

  function payload(): ShiftPayload {
    const endDate = overnight ? addDays(date, 1) : date
    return {
      starts_at: `${date}T${start}:00Z`,
      ends_at: `${endDate}T${end}:00Z`,
      role: role.trim() || null,
      job_id: jobId || null,
      department: department.trim() || null,
      location_id: locationId || null,
      break_minutes: Math.max(0, Math.round(Number(breakMinutes) || 0)),
      required_staff: Math.max(1, Math.round(Number(requiredStaff) || 1)),
      notes: notes.trim() || null,
      ...(editing ? {} : {
        kind,
        ...(kind === 'training' && requirementId ? { training_requirement_id: requirementId } : {}),
        ...(defaults?.employeeIds?.length ? { employee_ids: defaults.employeeIds } : {}),
      }),
    }
  }

  async function save() {
    if (!date || !start || !end) return
    if (!editing && kind === 'training' && !requirementId) return
    if (editing) await onUpdate(payload())
    else await onCreate(payload())
  }

  return (
    <Card className="w-full shrink-0 rounded-none border-x-0 border-b-0 p-4 lg:w-80 lg:rounded-xl lg:border">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-medium text-zinc-100">{editing ? 'Edit shift' : 'New draft shift'}</h2>
          <p className="mt-0.5 text-[10px] text-zinc-600">{editing ? `${fmtTime(shift!.starts_at)}-${fmtTime(shift!.ends_at)}` : 'Changes autosave'}</p>
        </div>
        <button onClick={onClose} className="text-zinc-600 hover:text-zinc-200" aria-label="Close shift inspector"><X className="h-4 w-4" /></button>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <label className="text-[10px] uppercase tracking-wide text-zinc-600">Date<input type="date" value={date} onChange={(event) => setDate(event.target.value)} disabled={readOnly} className={input} /></label>
        <label className="text-[10px] uppercase tracking-wide text-zinc-600">Role<input value={role} onChange={(event) => setRole(event.target.value)} disabled={readOnly} className={input} placeholder="Opener" /></label>
        <label className="text-[10px] uppercase tracking-wide text-zinc-600">Start<input type="time" value={start} onChange={(event) => setStart(event.target.value)} disabled={readOnly} className={input} /></label>
        <label className="text-[10px] uppercase tracking-wide text-zinc-600">End<input type="time" value={end} onChange={(event) => setEnd(event.target.value)} disabled={readOnly} className={input} /></label>
      </div>
      <div className="mt-3 space-y-2">
        <label className="block text-[10px] uppercase tracking-wide text-zinc-600">Department<input value={department} onChange={(event) => setDepartment(event.target.value)} disabled={readOnly} className={input} /></label>
        <label className="block text-[10px] uppercase tracking-wide text-zinc-600">Job<select value={jobId} onChange={(event) => setJobId(event.target.value)} disabled={readOnly} className={input}><option value="">No job — anyone can be assigned</option>{jobs.map((job) => <option key={job.id} value={job.id}>{job.name}</option>)}</select></label>
        <label className="block text-[10px] uppercase tracking-wide text-zinc-600">Location<div className={`${input} text-zinc-400`}>{locationName}</div></label>
        <div className="grid grid-cols-2 gap-2">
          <label className="text-[10px] uppercase tracking-wide text-zinc-600">Break minutes<input type="number" min="0" value={breakMinutes} onChange={(event) => setBreakMinutes(event.target.value)} disabled={readOnly} className={input} /></label>
          <label className="text-[10px] uppercase tracking-wide text-zinc-600">Staff needed<input type="number" min="1" value={requiredStaff} onChange={(event) => setRequiredStaff(event.target.value)} disabled={readOnly} className={input} /></label>
        </div>
        <label className="block text-[10px] uppercase tracking-wide text-zinc-600">Notes<textarea rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} disabled={readOnly} className={input} /></label>
        {!editing && trainingEnabled && <label className="block text-[10px] uppercase tracking-wide text-zinc-600">Kind<select value={kind} onChange={(event) => setKind(event.target.value as 'work' | 'training')} disabled={readOnly} className={input}><option value="work">Work</option><option value="training">Training</option></select></label>}
        {!editing && trainingEnabled && kind === 'training' && <label className="block text-[10px] uppercase tracking-wide text-zinc-600">Training requirement<select value={requirementId} onChange={(event) => setRequirementId(event.target.value)} disabled={readOnly} className={input}><option value="">Select requirement...</option>{requirements.map((requirement) => <option key={requirement.id} value={requirement.id}>{requirement.title}</option>)}</select></label>}
      </div>
      {editing && <div className="mt-3 rounded-lg bg-zinc-950 px-2.5 py-2 text-[11px] text-zinc-500">Assigned: {assignments.length === 0 ? <span className="text-zinc-300">Nobody yet</span> : <span className="block space-y-1 text-zinc-300">{assignments.map((assignment) => <span key={assignment.employee_id} className="flex items-center gap-1"><span>{assignment.name}</span>{assignment.availability_overridden && <span className="text-orange-400" title="Availability override">Availability override</span>}</span>)}</span>}</div>}
      <div className="mt-4 flex items-center gap-2">
        {!readOnly && <button onClick={save} disabled={saving} className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50">{saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}{editing ? 'Save changes' : 'Create draft'}</button>}
        {editing && !readOnly && <button onClick={onDelete} disabled={saving} className="ml-auto rounded-lg p-2 text-zinc-600 hover:bg-red-500/10 hover:text-red-400" aria-label="Delete shift"><Trash2 className="h-4 w-4" /></button>}
      </div>
      {readOnly && <p className="mt-3 text-[10px] text-amber-500">Published shifts are locked. Enable Edit published to change this shift.</p>}
      {defaults?.employeeIds?.length ? <p className="mt-3 text-[10px] text-emerald-400">{roster.filter((employee) => defaults.employeeIds?.includes(employee.id)).map((employee) => employee.name).join(', ')} will be assigned.</p> : null}
    </Card>
  )
}
