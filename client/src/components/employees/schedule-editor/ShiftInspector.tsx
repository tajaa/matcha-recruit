import { Check, Loader2, Trash2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { fetchShiftBreakStagger, updateAssignmentBreakPlan, updateAssignmentNote } from '../../../api/employees/employeeSchedule'
import { trainingApi, type TrainingRequirement } from '../../../api/training/training'
import { Card } from '../../ui'
import type { AssignmentNotePayload, BreakStaggerResult, PlannedBreak, ShiftAssignment, RosterEmployee, ScheduleJob, Shift, ShiftPayload } from '../../../types/employeeSchedule'
import { addDays, fmtTime } from '../../../types/employeeSchedule'
import { MAX_BREAK_MINUTES, MAX_REQUIRED_STAFF, validateShiftFields } from './shiftValidation'
import {
  NO_ROLES_MESSAGE, NO_ROLE_OPTION, ROLE_PLACEHOLDER, ROLE_REQUIRED_MESSAGE,
  isJobMissingFromList, roleLabelForJob,
} from './roleSelection'

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
  onAssignmentUpdated(): Promise<void>
  onClose(): void
}

const input = 'mt-1 w-full rounded-lg border border-zinc-800 bg-zinc-950 px-2.5 py-2 text-xs text-zinc-200 outline-none focus:border-zinc-600 disabled:opacity-50'

function twoDigits(value: number) {
  return String(value).padStart(2, '0')
}

function minuteToTime(minute: number) {
  return `${twoDigits(Math.floor(minute / 60) % 24)}:${twoDigits(minute % 60)}`
}

export default function ShiftInspector({ shift, defaults, locationId, locationName, roster, jobs, trainingEnabled, readOnly, saving, onCreate, onUpdate, onDelete, onAssignmentUpdated, onClose }: ShiftInspectorProps) {
  const editing = !!shift
  const defaultDate = defaults?.date ?? shift?.starts_at.slice(0, 10) ?? ''
  const [date, setDate] = useState(defaultDate)
  const [start, setStart] = useState(shift ? shift.starts_at.slice(11, 16) : minuteToTime(defaults?.minute ?? 540))
  const [end, setEnd] = useState(shift ? shift.ends_at.slice(11, 16) : minuteToTime((defaults?.minute ?? 540) + 480))
  const [jobId, setJobId] = useState(shift?.job_id ?? '')
  const [department, setDepartment] = useState(shift?.department ?? '')
  const [breakMinutes, setBreakMinutes] = useState(shift ? String(shift.break_minutes) : '')
  const [breakDirty, setBreakDirty] = useState(false)
  const [requiredStaff, setRequiredStaff] = useState(String(shift?.required_staff ?? 1))
  const [notes, setNotes] = useState(shift?.notes ?? '')
  const [kind, setKind] = useState<'work' | 'training'>(shift?.kind ?? 'work')
  const [requirementId, setRequirementId] = useState(shift?.training_requirement_id ?? '')
  const [requirements, setRequirements] = useState<TrainingRequirement[]>([])
  const [validationError, setValidationError] = useState<string | null>(null)
  const [roleMissing, setRoleMissing] = useState(false)
  const [stagger, setStagger] = useState<BreakStaggerResult[]>([])
  const [staggerAdvisories, setStaggerAdvisories] = useState<string[]>([])
  const [breakRevision, setBreakRevision] = useState(0)
  const persistedBreakMinutes = shift?.break_minutes
  const shiftId = shift?.id ?? ''
  const assignmentCount = shift?.assignments?.length ?? 0
  const selectedJobMissing = isJobMissingFromList(jobId, jobs)
  const noRolesAvailable = !editing && jobs.length === 0

  useEffect(() => {
    if (!breakDirty && persistedBreakMinutes !== undefined) {
      setBreakMinutes(String(persistedBreakMinutes))
    }
  }, [breakDirty, persistedBreakMinutes])

  useEffect(() => {
    if (!trainingEnabled || editing) return
    trainingApi.listRequirements().then(setRequirements).catch(() => setRequirements([]))
  }, [editing, trainingEnabled])

  // Suggestions are derived at read time, so they are fetched per opened shift
  // rather than read off the shift payload. A failure leaves the legally
  // required guidance below untouched — it never blocks editing the shift.
  useEffect(() => {
    if (!shiftId || assignmentCount === 0) {
      setStagger([])
      setStaggerAdvisories([])
      return
    }
    let cancelled = false
    fetchShiftBreakStagger(shiftId)
      .then((plan) => {
        if (cancelled) return
        setStagger(plan.results)
        setStaggerAdvisories(plan.advisories.map((advisory) => advisory.message))
      })
      .catch(() => {
        if (cancelled) return
        setStagger([])
        setStaggerAdvisories([])
      })
    return () => { cancelled = true }
  }, [shiftId, assignmentCount, breakRevision])

  if (!shift && !defaults) return null

  const overnight = end <= start
  const assignments = shift?.assignments ?? []

  function payload(requiredStaffValue: number, breakMinutesValue: number | undefined): ShiftPayload {
    const endDate = overnight ? addDays(date, 1) : date
    return {
      starts_at: `${date}T${start}:00Z`,
      ends_at: `${endDate}T${end}:00Z`,
      role: roleLabelForJob(jobId, jobs, shift),
      job_id: jobId || null,
      department: department.trim() || null,
      location_id: locationId || null,
      break_mode: breakMinutesValue === undefined ? 'auto' : 'manual',
      ...(breakMinutesValue === undefined ? {} : { break_minutes: breakMinutesValue }),
      required_staff: requiredStaffValue,
      notes: notes.trim() || null,
      ...(editing ? {} : {
        kind,
        ...(kind === 'training' && requirementId ? { training_requirement_id: requirementId } : {}),
        ...(defaults?.employeeIds?.length ? { employee_ids: defaults.employeeIds } : {}),
      }),
    }
  }

  async function save() {
    const validation = validateShiftFields({ date, start, end, requiredStaff, breakMinutes })
    if (!validation.valid) {
      setValidationError(validation.error)
      return
    }
    if (!editing && !jobId) {
      setRoleMissing(true)
      setValidationError(ROLE_REQUIRED_MESSAGE)
      return
    }
    if (!editing && kind === 'training' && !requirementId) {
      setValidationError('Select a training requirement for this session')
      return
    }
    setValidationError(null)
    setRoleMissing(false)
    const plannedBreak = editing && !breakDirty ? undefined : validation.breakMinutes
    const nextPayload = payload(validation.requiredStaff, plannedBreak)
    if (editing) await onUpdate(nextPayload)
    else await onCreate(nextPayload)
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
        <label className="text-[10px] uppercase tracking-wide text-zinc-600">Date<input type="date" required value={date} onChange={(event) => setDate(event.target.value)} disabled={readOnly} className={input} /></label>
        <label className="text-[10px] uppercase tracking-wide text-zinc-600">Role <span aria-hidden="true" className="text-red-400">*</span><select required aria-invalid={roleMissing} aria-describedby={roleMissing ? 'shift-role-error' : undefined} value={jobId} onChange={(event) => { setJobId(event.target.value); setRoleMissing(false); setValidationError(null) }} disabled={readOnly} className={input}><option value="">{editing ? NO_ROLE_OPTION : ROLE_PLACEHOLDER}</option>{editing && selectedJobMissing && <option value={jobId}>{shift?.role ?? 'Previously assigned role'}</option>}{jobs.map((job) => <option key={job.id} value={job.id}>{job.name}</option>)}</select>{noRolesAvailable && <span className="mt-1 block normal-case tracking-normal text-[10px] text-amber-500">{NO_ROLES_MESSAGE}</span>}</label>
        <label className="text-[10px] uppercase tracking-wide text-zinc-600">Start<input type="time" required value={start} onChange={(event) => setStart(event.target.value)} disabled={readOnly} className={input} /></label>
        <label className="text-[10px] uppercase tracking-wide text-zinc-600">End<input type="time" required value={end} onChange={(event) => setEnd(event.target.value)} disabled={readOnly} className={input} /></label>
      </div>
      <div className="mt-3 space-y-2">
        <label className="block text-[10px] uppercase tracking-wide text-zinc-600">Department<input value={department} onChange={(event) => setDepartment(event.target.value)} disabled={readOnly} className={input} /></label>
        <label className="block text-[10px] uppercase tracking-wide text-zinc-600">Location<div className={`${input} text-zinc-400`}>{locationName}</div></label>
        <div className="grid grid-cols-2 gap-2">
          <div className="text-[10px] uppercase tracking-wide text-zinc-600"><label htmlFor="shift-break-minutes">Planned break (minutes)</label><input id="shift-break-minutes" aria-describedby="shift-break-help" type="number" min="0" max={MAX_BREAK_MINUTES} step="5" value={breakMinutes} onChange={(event) => { setBreakMinutes(event.target.value); setBreakDirty(true) }} disabled={readOnly} placeholder="Auto" className={input} /><span id="shift-break-help" className="mt-1 block text-[9px] normal-case tracking-normal text-zinc-600">Leave blank for Auto. Untouched breaks are raised when approved rules require it.</span></div>
          <label className="text-[10px] uppercase tracking-wide text-zinc-600">Staff needed<input type="number" min="1" max={MAX_REQUIRED_STAFF} step="1" required value={requiredStaff} onChange={(event) => setRequiredStaff(event.target.value)} disabled={readOnly} className={input} /></label>
        </div>
        <label className="block text-[10px] uppercase tracking-wide text-zinc-600">Notes<textarea rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} disabled={readOnly} className={input} /></label>
        {!editing && trainingEnabled && <label className="block text-[10px] uppercase tracking-wide text-zinc-600">Kind<select value={kind} onChange={(event) => setKind(event.target.value as 'work' | 'training')} disabled={readOnly} className={input}><option value="work">Work</option><option value="training">Training</option></select></label>}
        {!editing && trainingEnabled && kind === 'training' && <label className="block text-[10px] uppercase tracking-wide text-zinc-600">Training requirement<select value={requirementId} onChange={(event) => setRequirementId(event.target.value)} disabled={readOnly} className={input}><option value="">Select requirement...</option>{requirements.map((requirement) => <option key={requirement.id} value={requirement.id}>{requirement.title}</option>)}</select></label>}
      </div>
      {validationError && <p id={roleMissing ? 'shift-role-error' : undefined} role="alert" className="mt-3 text-xs text-red-400">{validationError}</p>}
      {editing && <div className="mt-3 rounded-lg bg-zinc-950 px-2.5 py-2 text-[11px] text-zinc-500">Assigned: {assignments.length === 0 ? <span className="text-zinc-300">Nobody yet</span> : <span className="block space-y-2 text-zinc-300">{assignments.map((assignment) => <AssignmentSummary key={assignment.employee_id} shiftId={shift!.id} assignment={assignment} shiftStartsAt={shift!.starts_at} stagger={stagger.filter((result) => result.employee_id === assignment.employee_id)} readOnly={readOnly} onSaved={async () => { setBreakRevision((value) => value + 1); await onAssignmentUpdated() }} />)}</span>}{staggerAdvisories.map((message) => <span key={message} className="mt-2 block text-amber-300">{message}</span>)}</div>}
      <div className="mt-4 flex items-center gap-2">
        {!readOnly && <button onClick={save} disabled={saving || noRolesAvailable} title={noRolesAvailable ? NO_ROLES_MESSAGE : undefined} className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50">{saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}{editing ? 'Save changes' : 'Create draft'}</button>}
        {editing && !readOnly && <button onClick={onDelete} disabled={saving} className="ml-auto rounded-lg p-2 text-zinc-600 hover:bg-red-500/10 hover:text-red-400" aria-label="Delete shift"><Trash2 className="h-4 w-4" /></button>}
      </div>
      {readOnly && <p className="mt-3 text-[10px] text-amber-500">Published shifts are locked. Enable Edit published to change this shift.</p>}
      {defaults?.employeeIds?.length ? <p className="mt-3 text-[10px] text-emerald-400">{roster.filter((employee) => defaults.employeeIds?.includes(employee.id)).map((employee) => employee.name).join(', ')} will be assigned.</p> : null}
    </Card>
  )
}

/** The clock face of a schedule timestamp. Schedule times are UTC-tagged
 *  wall-clock values, so the characters ARE the local time — never convert. */
function clockOf(iso: string) {
  return iso.slice(11, 16)
}

/** Put `clock` back into `template`'s time slot, keeping its date and offset. */
function withClock(template: string, clock: string) {
  return `${template.slice(0, 11)}${clock}${template.slice(16)}`
}

function breakLabel(result: BreakStaggerResult) {
  const kind = result.kind === 'meal' ? 'meal' : 'rest'
  return `${result.duration_minutes}-min ${kind}`
}

function AssignmentSummary({ shiftId, assignment, shiftStartsAt, stagger, readOnly, onSaved }: { shiftId: string; assignment: ShiftAssignment; shiftStartsAt: string; stagger: BreakStaggerResult[]; readOnly: boolean; onSaved: () => Promise<void> }) {
  const [note, setNote] = useState(assignment.manager_note ?? '')
  const [visible, setVisible] = useState(assignment.manager_note_visible_to_employee ?? true)
  const [includeDigest, setIncludeDigest] = useState(assignment.manager_note_include_in_location_digest ?? true)
  const [sendNotice, setSendNotice] = useState(assignment.manager_note_send_employee_notice ?? true)
  const [saving, setSaving] = useState(false)
  const [savingBreaks, setSavingBreaks] = useState(false)
  const [breakEdits, setBreakEdits] = useState<Record<string, string>>({})
  const guidance = assignment.compliance_guidance
  const savedBreaks = assignment.planned_breaks ?? []
  const breakKey = (kind: string, ordinal: number) => `${kind}:${ordinal}`
  const savedFor = (kind: string, ordinal: number) =>
    savedBreaks.find((planned) => planned.kind === kind && planned.ordinal === ordinal)
  // A saved time wins over a fresh suggestion: the manager already reviewed it.
  const clockFor = (result: BreakStaggerResult) => {
    const edited = breakEdits[breakKey(result.kind, result.ordinal)]
    if (edited !== undefined) return edited
    const saved = savedFor(result.kind, result.ordinal)
    if (saved) return clockOf(saved.start_local)
    return result.suggested_start ? clockOf(result.suggested_start) : ''
  }

  async function saveBreaks() {
    setSavingBreaks(true)
    try {
      const planned: PlannedBreak[] = []
      for (const result of stagger) {
        const clock = clockFor(result)
        if (!clock) continue
        const saved = savedFor(result.kind, result.ordinal)
        const template = saved?.start_local ?? result.suggested_start ?? shiftStartsAt
        const edited = breakEdits[breakKey(result.kind, result.ordinal)] !== undefined
        planned.push({
          kind: result.kind,
          ordinal: result.ordinal,
          start_local: withClock(template, clock),
          duration_minutes: result.duration_minutes,
          source: edited || saved ? 'manager' : 'suggested',
        })
      }
      await updateAssignmentBreakPlan(shiftId, assignment.employee_id, planned.length ? planned : null)
      setBreakEdits({})
      await onSaved()
    } finally {
      setSavingBreaks(false)
    }
  }

  async function saveNote() {
    setSaving(true)
    try {
      const payload: AssignmentNotePayload = {
        note: note.trim() || null,
        visible_to_employee: visible,
        include_in_location_digest: includeDigest,
        send_employee_notice: sendNotice,
      }
      await updateAssignmentNote(shiftId, assignment.employee_id, payload)
      await onSaved()
    } finally {
      setSaving(false)
    }
  }

  return <div className="rounded border border-zinc-800 p-2">
    <div className="flex items-center gap-1 text-zinc-200"><span>{assignment.name}</span>{assignment.availability_overridden && <span className="text-orange-400" title="Availability override">Availability override</span>}</div>
    {guidance?.summary && <p className={guidance.status === 'unmapped' || guidance.status === 'error' ? 'mt-1 text-amber-300' : 'mt-1 text-sky-300'}>{guidance.summary}</p>}
    {stagger.length > 0 && <div className="mt-2 space-y-1.5 border-t border-zinc-800 pt-2">
      <p className="text-[10px] uppercase tracking-wide text-zinc-600">Suggested break times</p>
      {stagger.map((result) => <div key={breakKey(result.kind, result.ordinal)} className="space-y-1">
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-zinc-400">{breakLabel(result)}</span>
          <input
            type="time"
            aria-label={`${breakLabel(result)} break start for ${assignment.name}`}
            value={clockFor(result)}
            disabled={readOnly}
            onChange={(event) => setBreakEdits((edits) => ({ ...edits, [breakKey(result.kind, result.ordinal)]: event.target.value }))}
            className="rounded border border-zinc-800 bg-zinc-950 px-1.5 py-1 text-[11px] text-zinc-200 outline-none focus:border-zinc-600 disabled:opacity-50"
          />
          {savedFor(result.kind, result.ordinal) && <span className="text-[9px] text-emerald-400">Saved</span>}
        </div>
        {result.status !== 'suggested' && result.reason && <p className="text-[10px] text-amber-300">{result.reason}</p>}
      </div>)}
      {!readOnly && <button onClick={() => void saveBreaks()} disabled={savingBreaks} className="text-[10px] text-emerald-300 hover:text-emerald-200 disabled:opacity-50">{savingBreaks ? 'Saving…' : 'Save break times'}</button>}
    </div>}
    <textarea rows={2} value={note} onChange={(event) => setNote(event.target.value)} placeholder="Shift note for this employee" className={`${input} mt-2`} />
    <div className="mt-1.5 grid gap-1 text-[10px] text-zinc-400">
      <label><input type="checkbox" checked={visible} onChange={(event) => setVisible(event.target.checked)} /> Visible to employee</label>
      <label><input type="checkbox" checked={includeDigest} onChange={(event) => setIncludeDigest(event.target.checked)} /> Include in manager digest</label>
      <label><input type="checkbox" checked={sendNotice} onChange={(event) => setSendNotice(event.target.checked)} /> Send in employee digest</label>
    </div>
    <button onClick={() => void saveNote()} disabled={saving} className="mt-2 text-[10px] text-emerald-300 hover:text-emerald-200 disabled:opacity-50">{saving ? 'Saving…' : 'Save assignment note'}</button>
  </div>
}
