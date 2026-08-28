import { useCallback, useEffect, useState } from 'react'
import { Button, Input, Select, useToast } from '../ui'
import {
  fetchEmployeeAvailability, fetchEmployeeJobs, fetchEmployeeScheduleProfile,
  fetchJobs, updateEmployeeSchedulingDetails, type AvailabilityWindow,
} from '../../api/employees/employeeSchedule'
import type {
  AvailabilityState, EmployeeJobAssignmentPayload, EmployeeScheduleProfile,
  QualificationStatus, ScheduleJob,
} from '../../types/employeeSchedule'

const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const STATE_OPTIONS = [
  { value: 'always_available', label: 'Available any time' },
  { value: 'windows', label: 'Specific windows' },
]
const STATUS_OPTIONS = [
  { value: 'active', label: 'Active' },
  { value: 'training', label: 'In training' },
  { value: 'suspended', label: 'Suspended' },
]

function minutesToHours(value: number | null) {
  return value == null ? '' : String(value / 60)
}

function hoursToMinutes(value: string) {
  return value.trim() === '' ? null : Math.round(Number(value) * 60)
}

export function EmployeeSchedulingPanel({
  employeeId, workLocationId,
}: { employeeId: string; workLocationId: string | null }) {
  const { toast } = useToast()
  const [jobs, setJobs] = useState<ScheduleJob[]>([])
  const [assignments, setAssignments] = useState<EmployeeJobAssignmentPayload[]>([])
  const [jobsDirty, setJobsDirty] = useState(false)
  const [profile, setProfile] = useState<EmployeeScheduleProfile | null>(null)
  const [availabilityState, setAvailabilityState] = useState<Exclude<AvailabilityState, 'unconfirmed'>>('always_available')
  const [windows, setWindows] = useState<AvailabilityWindow[]>([])
  const [hours, setHours] = useState({ min: '', target: '', max: '' })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const assignedJobIds = new Set(assignments.map((assignment) => assignment.job_id))
  const staleJobIds = new Set(jobs
    .filter((job) => assignedJobIds.has(job.id) && job.location_id != null && job.location_id !== workLocationId)
    .map((job) => job.id))
  const hasStaleAssignments = staleJobIds.size > 0

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [jobResult, assignmentResult, nextProfile, availability] = await Promise.all([
        fetchJobs(workLocationId ?? undefined), fetchEmployeeJobs(employeeId),
        fetchEmployeeScheduleProfile(employeeId), fetchEmployeeAvailability(employeeId),
      ])
      const availableJobs = jobResult.jobs.filter((job) => job.location_id == null || job.location_id === workLocationId)
      const visibleJobIds = new Set(availableJobs.map((job) => job.id))
      // Keep a stale/moved-location assignment visible. Saving unrelated hour
      // preferences must never silently delete a qualification the filtered
      // job catalog did not return.
      const assignedJobs = assignmentResult.assignments
        .filter((assignment) => !visibleJobIds.has(assignment.job_id))
        .map((assignment): ScheduleJob => ({
          id: assignment.job_id, name: assignment.job_name,
          location_id: assignment.location_id, color: null, notes: null,
          credential_grace_days: null, employee_ids: [employeeId],
          credential_requirements: assignment.credential_requirements,
        }))
      setJobs([...availableJobs, ...assignedJobs])
      setAssignments(assignmentResult.assignments.map(({ job_id, is_primary, qualification_status, qualified_from, qualified_until, notes }) => ({
        job_id, is_primary, qualification_status, qualified_from, qualified_until, notes,
      })))
      setJobsDirty(false)
      setProfile(nextProfile)
      setAvailabilityState(availability.availability_state === 'unconfirmed'
        ? (availability.windows.length > 0 ? 'windows' : 'always_available')
        : availability.availability_state)
      setWindows(availability.windows)
      setHours({
        min: minutesToHours(nextProfile.min_weekly_minutes),
        target: minutesToHours(nextProfile.target_weekly_minutes),
        max: minutesToHours(nextProfile.max_weekly_minutes),
      })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load scheduling details')
    } finally {
      setLoading(false)
    }
  }, [employeeId, workLocationId])

  useEffect(() => { void load() }, [load])

  function toggleJob(jobId: string, checked: boolean) {
    setJobsDirty(true)
    setAssignments((current) => checked
      ? [...current, { job_id: jobId, is_primary: false, qualification_status: 'active', qualified_from: null, qualified_until: null, notes: null }]
      : current.filter((assignment) => assignment.job_id !== jobId))
  }

  function updateAssignment(jobId: string, patch: Partial<EmployeeJobAssignmentPayload>) {
    setJobsDirty(true)
    setAssignments((current) => current.map((assignment) => assignment.job_id === jobId
      ? { ...assignment, ...patch } : assignment))
  }

  function setPrimary(jobId: string) {
    setJobsDirty(true)
    setAssignments((current) => current.map((assignment) => ({
      ...assignment,
      is_primary: assignment.job_id === jobId,
      qualification_status: assignment.job_id === jobId ? 'active' : assignment.qualification_status,
    })))
  }

  function addWindow() {
    setWindows((current) => [...current, { weekday: 1, start_time: '09:00', end_time: '17:00' }])
  }

  function removeWindow(index: number) {
    setWindows((current) => {
      const next = current.filter((_, currentIndex) => currentIndex !== index)
      if (next.length === 0) setAvailabilityState('always_available')
      return next
    })
  }

  function updateWindow(index: number, patch: Partial<AvailabilityWindow>) {
    setWindows((current) => current.map((window, currentIndex) => currentIndex === index
      ? { ...window, ...patch } : window))
  }

  async function save() {
    if (!profile) return
    if (jobsDirty && hasStaleAssignments) {
      setError('Remove all previous-location jobs before changing job assignments.')
      return
    }
    const min = hoursToMinutes(hours.min)
    const target = hoursToMinutes(hours.target)
    const max = hoursToMinutes(hours.max)
    if ([min, target, max].some((value) => value != null && (!Number.isFinite(value) || value < 0))) {
      setError('Weekly hours must be positive numbers.')
      return
    }
    setSaving(true)
    setError('')
    try {
      const result = await updateEmployeeSchedulingDetails(employeeId, {
        jobs: jobsDirty ? { assignments } : undefined,
        availability: {
          availability_state: availabilityState,
          windows: availabilityState === 'windows' ? windows : [],
        },
        profile: {
          min_weekly_minutes: min,
          target_weekly_minutes: target,
          max_weekly_minutes: max,
          max_consecutive_days: profile.max_consecutive_days,
          allow_overtime: profile.allow_overtime,
          prefer_extra_hours: profile.prefer_extra_hours,
        },
      })
      setProfile(result.profile)
      toast('Scheduling details saved', 'success')
      await load()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save scheduling details')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <p className="text-sm text-zinc-500">Loading scheduling details...</p>
  if (!profile) return <p className="text-sm text-red-400">{error || 'Scheduling details are unavailable.'}</p>

  return (
    <div className="space-y-6">
      <section>
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-medium text-zinc-200">Qualified jobs</h3>
          {assignments.some((assignment) => assignment.is_primary) && (
            <Button variant="ghost" size="sm" disabled={hasStaleAssignments} onClick={() => {
              setJobsDirty(true)
              setAssignments((current) => current.map((assignment) => ({ ...assignment, is_primary: false })))
            }}>
              Clear primary
            </Button>
          )}
        </div>
        <p className="mt-1 text-xs text-zinc-500">Job credentials become required as soon as the assignment is saved.</p>
        {hasStaleAssignments && (
          <p className="mt-2 text-xs text-amber-300">
            Remove every previous-location job to unlock job edits. Hours, preferences, and availability can still be saved without changing jobs.
          </p>
        )}
        <div className="mt-3 space-y-3">
          {jobs.map((job) => {
            const assignment = assignments.find((item) => item.job_id === job.id)
            const staleLocationJob = job.location_id != null && job.location_id !== workLocationId
            const staleAssignment = Boolean(assignment && staleLocationJob)
            const jobToggleDisabled = (hasStaleAssignments && !staleAssignment) || (staleLocationJob && !assignment)
            return (
              <div key={job.id} className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
                <label className="flex items-center gap-2 text-sm text-zinc-200">
                  <input type="checkbox" checked={Boolean(assignment)} disabled={jobToggleDisabled} onChange={(event) => toggleJob(job.id, event.target.checked)} />
                  {job.name}
                </label>
                {assignment && (
                  <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-5">
                    <Select label="Status" options={STATUS_OPTIONS} value={assignment.qualification_status}
                      disabled={hasStaleAssignments}
                      onChange={(event) => updateAssignment(job.id, { qualification_status: event.target.value as QualificationStatus, is_primary: event.target.value === 'active' ? assignment.is_primary : false })} />
                    <Input label="Qualified from" type="date" value={assignment.qualified_from ?? ''}
                      disabled={hasStaleAssignments}
                      onChange={(event) => updateAssignment(job.id, { qualified_from: event.target.value || null })} />
                    <Input label="Qualified until" type="date" value={assignment.qualified_until ?? ''}
                      disabled={hasStaleAssignments}
                      onChange={(event) => updateAssignment(job.id, { qualified_until: event.target.value || null })} />
                    <label className="flex items-end gap-2 pb-2 text-xs text-zinc-300">
                      <input type="radio" name="primary-job" checked={assignment.is_primary} disabled={hasStaleAssignments} onChange={() => setPrimary(job.id)} /> Primary job
                    </label>
                    <Input label="Notes" value={assignment.notes ?? ''}
                      disabled={hasStaleAssignments}
                      onChange={(event) => updateAssignment(job.id, { notes: event.target.value || null })} />
                  </div>
                )}
                {assignment && job.credential_requirements.length > 0 && (
                  <p className="mt-2 text-xs text-amber-300">Credentials: {job.credential_requirements.map((item) => item.credential_type_label).join(', ')}</p>
                )}
                {staleAssignment && (
                  <p className="mt-2 text-xs text-amber-300">Assigned at a previous work location. Remove this job before changing any job assignments.</p>
                )}
              </div>
            )
          })}
          {jobs.length === 0 && <p className="text-sm text-zinc-500">No jobs are configured for this location.</p>}
        </div>
      </section>

      <section className="border-t border-zinc-800 pt-5">
        <h3 className="text-sm font-medium text-zinc-200">Recurring availability</h3>
        <div className="mt-3 max-w-sm">
          <Select label="Availability" options={STATE_OPTIONS} value={availabilityState}
            onChange={(event) => {
              const next = event.target.value as Exclude<AvailabilityState, 'unconfirmed'>
              setAvailabilityState(next)
              if (next === 'windows' && windows.length === 0) addWindow()
            }} />
        </div>
        {profile.availability_state === 'unconfirmed' && <p className="mt-2 text-xs text-amber-300">Not confirmed. Auto-assignment will not use this employee until these details are saved.</p>}
        {availabilityState === 'windows' && (
          <div className="mt-3 space-y-2">
            {windows.map((window, index) => (
              <div key={`${index}-${window.weekday}`} className="grid grid-cols-[1fr_1fr_1fr_auto] items-end gap-2">
                <Select label={index === 0 ? 'Day' : ''} options={DAYS.map((label, value) => ({ label, value: String(value) }))}
                  value={String(window.weekday)} onChange={(event) => updateWindow(index, { weekday: Number(event.target.value) })} />
                <Input label={index === 0 ? 'Start' : ''} type="time" value={window.start_time}
                  onChange={(event) => updateWindow(index, { start_time: event.target.value })} />
                <Input label={index === 0 ? 'End' : ''} type="time" value={window.end_time}
                  onChange={(event) => updateWindow(index, { end_time: event.target.value })} />
                <Button variant="ghost" size="sm" onClick={() => removeWindow(index)}>Remove</Button>
              </div>
            ))}
            <Button variant="ghost" size="sm" onClick={addWindow}>Add window</Button>
          </div>
        )}
      </section>

      <section className="border-t border-zinc-800 pt-5">
        <h3 className="text-sm font-medium text-zinc-200">Hours and assignment preferences</h3>
        <div className="mt-3 grid grid-cols-3 gap-3">
          <Input label="Minimum hours / week" type="number" min="0" step="0.5" value={hours.min} onChange={(event) => setHours((current) => ({ ...current, min: event.target.value }))} />
          <Input label="Target hours / week" type="number" min="0" step="0.5" value={hours.target} onChange={(event) => setHours((current) => ({ ...current, target: event.target.value }))} />
          <Input label="Maximum hours / week" type="number" min="0" step="0.5" value={hours.max} onChange={(event) => setHours((current) => ({ ...current, max: event.target.value }))} />
        </div>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Select label="Maximum consecutive days" value={profile.max_consecutive_days == null ? '' : String(profile.max_consecutive_days)}
            placeholder="No preference" options={[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14].map((value) => ({ value: String(value), label: String(value) }))}
            onChange={(event) => setProfile({ ...profile, max_consecutive_days: event.target.value ? Number(event.target.value) : null })} />
          <label className="flex items-end gap-2 pb-2 text-sm text-zinc-300"><input type="checkbox" checked={profile.allow_overtime} onChange={(event) => setProfile({ ...profile, allow_overtime: event.target.checked })} /> Allow overtime</label>
          <label className="flex items-end gap-2 pb-2 text-sm text-zinc-300"><input type="checkbox" checked={profile.prefer_extra_hours} onChange={(event) => setProfile({ ...profile, prefer_extra_hours: event.target.checked })} /> Prefers extra hours</label>
        </div>
      </section>

      {error && <p className="text-sm text-red-400">{error}</p>}
      <div className="flex justify-end border-t border-zinc-800 pt-4">
        <Button onClick={save} disabled={saving}>{saving ? 'Saving...' : 'Save scheduling details'}</Button>
      </div>
    </div>
  )
}
