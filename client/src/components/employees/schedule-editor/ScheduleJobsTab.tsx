import { BriefcaseBusiness, Check, ChevronDown, ChevronUp, Loader2, Plus, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useToast, Card } from '../../ui'
import {
  createJob, deleteJob, fetchJobs, fetchRoster, replaceJobCredentialRequirements, replaceJobEmployees, updateJob,
} from '../../../api/employees/employeeSchedule'
import { fetchCredentialTypes } from '../../../api/employees/credentialTemplates'
import type { CredentialType } from '../../../types/credentialTemplates'
import type { JobCredentialRequirement, RosterEmployee, ScheduleJob } from '../../../types/employeeSchedule'
import { errorMessage } from '../../../types/employeeSchedule'

const inputCls = 'w-full rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-1.5 text-sm text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-zinc-500'

export default function ScheduleJobsTab({ locationId, credentialTemplatesEnabled, onJobsChanged }: { locationId: string; credentialTemplatesEnabled: boolean; onJobsChanged?: () => Promise<void> }) {
  const { toast } = useToast()
  const [jobs, setJobs] = useState<ScheduleJob[]>([])
  const [roster, setRoster] = useState<RosterEmployee[]>([])
  const [credentialTypes, setCredentialTypes] = useState<CredentialType[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const credentialTypesPromise = credentialTemplatesEnabled
        ? fetchCredentialTypes().catch((error) => {
          toast(errorMessage(error), 'error')
          return []
        })
        : Promise.resolve([])
      const [jobResponse, rosterResponse, types] = await Promise.all([fetchJobs(locationId), fetchRoster(locationId), credentialTypesPromise])
      setJobs(jobResponse.jobs)
      setRoster(rosterResponse.employees)
      setCredentialTypes(types)
    } catch (error) {
      toast(errorMessage(error), 'error')
    } finally {
      setLoading(false)
    }
  }, [credentialTemplatesEnabled, locationId, toast])

  useEffect(() => { void load() }, [load])

  if (loading) return <div className="flex h-40 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-zinc-500" /></div>

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-medium text-zinc-200">Jobs and qualifications</h3>
          <p className="mt-1 max-w-2xl text-xs leading-5 text-zinc-500">Define the work areas at this location, then choose who is qualified for each one. Employees who are not qualified can still be overridden when a manager makes that call.</p>
        </div>
        <button onClick={() => setCreating((value) => !value)} className="inline-flex items-center gap-1 rounded-lg border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:text-zinc-100"><Plus className="h-4 w-4" /> New job</button>
      </div>
      {creating && <NewJobForm locationId={locationId} credentialTypes={credentialTypes} credentialTemplatesEnabled={credentialTemplatesEnabled} onDone={() => { setCreating(false); void load(); void onJobsChanged?.() }} onCancel={() => setCreating(false)} />}
      {jobs.length === 0 && !creating ? <p className="rounded-xl border border-dashed border-zinc-800 px-4 py-8 text-center text-sm text-zinc-600">No jobs yet. Start with an area such as Box Office, Concessions, or Ushers.</p> : (
        <div className="space-y-2">
          {jobs.map((job) => <JobCard key={job.id} job={job} roster={roster} credentialTypes={credentialTypes} credentialTemplatesEnabled={credentialTemplatesEnabled} onChanged={async () => { await load(); await onJobsChanged?.() }} />)}
        </div>
      )}
    </div>
  )
}

function NewJobForm({ locationId, credentialTypes, credentialTemplatesEnabled, onDone, onCancel }: { locationId: string; credentialTypes: CredentialType[]; credentialTemplatesEnabled: boolean; onDone(): void; onCancel(): void }) {
  const { toast } = useToast()
  const [name, setName] = useState('')
  const [notes, setNotes] = useState('')
  const [graceDays, setGraceDays] = useState('')
  const [requirementIds, setRequirementIds] = useState<string[]>([])
  const [busy, setBusy] = useState(false)

  async function save() {
    if (!name.trim()) return
    setBusy(true)
    try {
      await createJob({
        name: name.trim(), location_id: locationId, notes: notes.trim() || null, employee_ids: [],
        credential_grace_days: graceDays === '' ? null : Number(graceDays),
        credential_requirements: requirementIds.map((credential_type_id) => ({ credential_type_id, is_required: true, schedule_blocking: true })),
      })
      onDone()
    } catch (error) {
      toast(errorMessage(error), 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="space-y-3 border-zinc-800 bg-zinc-900/50 p-4 shadow-none">
      <div className="grid gap-2 md:grid-cols-2">
        <label className="text-[10px] uppercase tracking-wide text-zinc-500">Job name<input value={name} onChange={(event) => setName(event.target.value)} placeholder="Box Office" className={`${inputCls} mt-1`} /></label>
        <label className="text-[10px] uppercase tracking-wide text-zinc-500">Notes<input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Optional qualification context" className={`${inputCls} mt-1`} /></label>
        {credentialTemplatesEnabled && <label className="text-[10px] uppercase tracking-wide text-zinc-500">Grace days<input value={graceDays} min="0" max="365" type="number" onChange={(event) => setGraceDays(event.target.value)} placeholder="Company default" className={`${inputCls} mt-1`} /></label>}
      </div>
      {credentialTemplatesEnabled && <CredentialRequirementPicker credentialTypes={credentialTypes} selectedIds={requirementIds} onChange={setRequirementIds} />}
      <div className="flex items-center gap-2">
        <button onClick={save} disabled={busy || !name.trim()} className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50">{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Create job</button>
        <button onClick={onCancel} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-100">Cancel</button>
      </div>
    </Card>
  )
}

function JobCard({ job, roster, credentialTypes, credentialTemplatesEnabled, onChanged }: { job: ScheduleJob; roster: RosterEmployee[]; credentialTypes: CredentialType[]; credentialTemplatesEnabled: boolean; onChanged(): Promise<void> }) {
  const { toast } = useToast()
  const [expanded, setExpanded] = useState(false)
  const [selected, setSelected] = useState(() => new Set(job.employee_ids))
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [savingCredentials, setSavingCredentials] = useState(false)
  const [graceDays, setGraceDays] = useState(job.credential_grace_days?.toString() ?? '')
  const [requirementIds, setRequirementIds] = useState<string[]>(() => job.credential_requirements.map((item) => item.credential_type_id))

  useEffect(() => setSelected(new Set(job.employee_ids)), [job.employee_ids])
  useEffect(() => {
    setGraceDays(job.credential_grace_days?.toString() ?? '')
    setRequirementIds(job.credential_requirements.map((item) => item.credential_type_id))
  }, [job.credential_grace_days, job.credential_requirements])

  function toggle(employeeId: string) {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(employeeId)) next.delete(employeeId)
      else next.add(employeeId)
      return next
    })
  }

  async function saveRoster() {
    setSaving(true)
    try {
      await replaceJobEmployees(job.id, [...selected])
      toast(`${job.name} qualifications saved`, 'success')
      await onChanged()
    } catch (error) {
      toast(errorMessage(error), 'error')
    } finally {
      setSaving(false)
    }
  }

  async function remove() {
    if (!window.confirm(`Delete ${job.name}? Existing shifts will become ungated.`)) return
    setDeleting(true)
    try {
      await deleteJob(job.id)
      await onChanged()
    } catch (error) {
      toast(errorMessage(error), 'error')
    } finally {
      setDeleting(false)
    }
  }

  async function saveCredentials() {
    setSavingCredentials(true)
    try {
      const requirements: JobCredentialRequirement[] = requirementIds.map((credential_type_id) => ({ credential_type_id, is_required: true, schedule_blocking: true }))
      await Promise.all([
        updateJob(job.id, { credential_grace_days: graceDays === '' ? null : Number(graceDays) }),
        replaceJobCredentialRequirements(job.id, requirements),
      ])
      toast(`${job.name} credential rules saved`, 'success')
      await onChanged()
    } catch (error) {
      toast(errorMessage(error), 'error')
    } finally {
      setSavingCredentials(false)
    }
  }

  return (
    <Card className="border-transparent bg-zinc-900/40 p-2.5 shadow-none">
      <div className="flex flex-wrap items-center gap-2.5">
        <button onClick={() => setExpanded((value) => !value)} className="p-0.5 text-zinc-600 hover:text-zinc-200" aria-label={`${expanded ? 'Collapse' : 'Expand'} ${job.name}`}>
          {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </button>
        <BriefcaseBusiness className="h-4 w-4 text-emerald-400" />
        <div className="min-w-0 flex-1">
          <div className="text-sm text-zinc-200">{job.name}</div>
          <div className="text-[11px] text-zinc-600">{job.employee_ids.length} qualified employee{job.employee_ids.length === 1 ? '' : 's'}{credentialTemplatesEnabled ? ` · ${job.credential_requirements.length} credential rule${job.credential_requirements.length === 1 ? '' : 's'}` : ''}</div>
        </div>
        <button onClick={remove} disabled={deleting} className="p-1 text-zinc-600 hover:text-red-400" aria-label={`Delete ${job.name}`}><Trash2 className="h-3.5 w-3.5" /></button>
      </div>
      {expanded && <div className="mt-3 border-t border-zinc-800/70 pt-3">
        <p className="mb-2 text-xs text-zinc-500">Select everyone qualified for this job. Unselected employees remain visible in the schedule and can be force-assigned when needed.</p>
        <div className="grid gap-1 sm:grid-cols-2 lg:grid-cols-3">
          {roster.map((employee) => <label key={employee.id} className="flex cursor-pointer items-center gap-2 rounded-lg border border-zinc-800 px-2.5 py-2 text-xs text-zinc-300 hover:border-zinc-700">
            <input type="checkbox" checked={selected.has(employee.id)} onChange={() => toggle(employee.id)} className="accent-emerald-500" />
            <span className="min-w-0 flex-1 truncate">{employee.name}</span>
            <span className="truncate text-[10px] text-zinc-600">{employee.job_title || employee.department || ''}</span>
          </label>)}
        </div>
        <button onClick={saveRoster} disabled={saving} className="mt-3 inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50">{saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Save qualified roster</button>
        {credentialTemplatesEnabled && <div className="mt-4 border-t border-zinc-800/70 pt-3">
          <p className="mb-2 text-xs text-zinc-500">Required credentials block this job after the new-hire grace period. They do not affect unrelated jobs.</p>
          <label className="block max-w-48 text-[10px] uppercase tracking-wide text-zinc-500">Grace days<input value={graceDays} min="0" max="365" type="number" onChange={(event) => setGraceDays(event.target.value)} placeholder="Company default" className={`${inputCls} mt-1`} /></label>
          <CredentialRequirementPicker credentialTypes={credentialTypes} selectedIds={requirementIds} onChange={setRequirementIds} />
          <button onClick={saveCredentials} disabled={savingCredentials} className="mt-3 inline-flex items-center gap-1 rounded-lg border border-emerald-700 px-3 py-1.5 text-xs font-medium text-emerald-300 hover:bg-emerald-950 disabled:opacity-50">{savingCredentials ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Save credential rules</button>
        </div>}
      </div>}
    </Card>
  )
}

function CredentialRequirementPicker({ credentialTypes, selectedIds, onChange }: { credentialTypes: CredentialType[]; selectedIds: string[]; onChange(ids: string[]): void }) {
  const selected = new Set(selectedIds)
  const available = credentialTypes.filter((type) => !selected.has(type.id))
  return <div className="mt-3">
    <select value="" onChange={(event) => { if (event.target.value) onChange([...selectedIds, event.target.value]) }} className={inputCls} aria-label="Add required credential">
      <option value="">Add a required credential…</option>
      {available.map((type) => <option key={type.id} value={type.id}>{type.label}</option>)}
    </select>
    {selectedIds.length > 0 && <div className="mt-2 flex flex-wrap gap-1.5">{selectedIds.map((id) => {
      const type = credentialTypes.find((item) => item.id === id)
      return <button key={id} type="button" onClick={() => onChange(selectedIds.filter((item) => item !== id))} className="rounded-md border border-emerald-800 bg-emerald-950/40 px-2 py-1 text-[11px] text-emerald-200 hover:border-red-700" title="Remove requirement">{type?.label ?? 'Credential'} ×</button>
    })}</div>}
  </div>
}
