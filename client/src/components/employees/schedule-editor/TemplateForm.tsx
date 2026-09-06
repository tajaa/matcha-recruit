/** The week-template block editor, shared by the Templates tab on the schedule
 *  page and the Week Start pane in the editor.
 *
 *  Both surfaces edit the same rows, so a second copy would drift the way the
 *  role picker did before `roleSelection.ts` existed. The one behavioural
 *  difference is the `jobs` prop: when a caller passes the location's jobs the
 *  block picks a real job (and mirrors its name into `role`); without it the
 *  block keeps the free-text role field the schedule page has always shown. */
import { useState } from 'react'
import { Check, Loader2, Plus } from 'lucide-react'
import { useToast, Select } from '../../ui'
import { createWeekTemplate, replaceWeekTemplate } from '../../../api/employees/employeeSchedule'
import type { ScheduleJob, WeekTemplate } from '../../../types/employeeSchedule'
import { WEEKDAY_LABELS, errorMessage } from '../../../types/employeeSchedule'
import { isJobMissingFromList, roleLabelForJob } from './roleSelection'

const inputCls = 'bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 w-full'

type TemplateBlockDraft = {
  id: number | string
  name: string
  role: string
  jobId: string
  start: string
  end: string
  breakMinutes: string
  required: string
  days: number[]
}

export const MAX_TEMPLATE_BLOCKS = 40

function newTemplateBlock(id: number): TemplateBlockDraft {
  return {
    id,
    name: '',
    role: '',
    jobId: '',
    start: '09:00',
    end: '17:00',
    breakMinutes: '0',
    required: '1',
    days: [1, 2, 3, 4, 5],
  }
}

interface TemplateFormProps {
  locationId: string
  template?: WeekTemplate
  /** When supplied, each block picks one of these instead of typing a role. */
  jobs?: ScheduleJob[]
  submitLabel?: string
  /** Receives the saved template so a caller that just created one can store its id. */
  onDone: (template: WeekTemplate) => void
  /** Omit to hide the Cancel button (an always-open editor has nothing to cancel to). */
  onCancel?: () => void
}

export function TemplateForm({ locationId, template, jobs, submitLabel, onDone, onCancel }: TemplateFormProps) {
  const { toast } = useToast()
  const [name, setName] = useState(() => template?.name ?? '')
  const [blocks, setBlocks] = useState<TemplateBlockDraft[]>(() => template
    ? template.blocks.map((block) => ({
      id: block.id,
      name: block.name,
      role: block.role ?? '',
      jobId: block.job_id ?? '',
      start: block.start_time.slice(0, 5),
      end: block.end_time.slice(0, 5),
      breakMinutes: String(block.break_minutes),
      required: String(block.required_staff),
      days: block.days_of_week,
    }))
    : [newTemplateBlock(1)])
  const [busy, setBusy] = useState(false)
  const blocksValid = blocks.every((block) => block.days.length > 0)

  function updateBlock(id: number | string, patch: Partial<TemplateBlockDraft>) {
    setBlocks((current) => current.map((block) => block.id === id ? { ...block, ...patch } : block))
  }

  function toggleDay(id: number | string, day: number) {
    const block = blocks.find((item) => item.id === id)
    if (!block) return
    updateBlock(id, {
      days: block.days.includes(day)
        ? block.days.filter((item) => item !== day)
        : [...block.days, day].sort((a, b) => a - b),
    })
  }

  function addBlock() {
    setBlocks((current) => {
      if (current.length >= MAX_TEMPLATE_BLOCKS) return current
      const nextId = Math.max(0, ...current.map((block) => typeof block.id === 'number' ? block.id : 0)) + 1
      return [...current, newTemplateBlock(nextId)]
    })
  }

  async function save() {
    if (!name.trim() || blocks.length === 0 || !blocksValid) return
    setBusy(true)
    try {
      const blockPayload = (block: TemplateBlockDraft, index: number) => ({
        id: typeof block.id === 'string' ? block.id : undefined,
        name: block.name.trim() || block.role.trim() || `Shift ${index + 1}`,
        role: block.role.trim() || null,
        start_time: `${block.start}:00`, end_time: `${block.end}:00`,
        break_minutes: Math.max(0, Math.round(Number(block.breakMinutes) || 0)),
        required_staff: Math.max(1, Math.round(Number(block.required) || 1)),
        days_of_week: block.days,
        // Carried on every save, including from the surface that never shows a
        // job picker — otherwise editing a name here silently unlinks the job.
        job_id: block.jobId || null,
      })
      let saved: WeekTemplate
      if (!template) {
        saved = await createWeekTemplate({
          name: name.trim(), location_id: locationId,
          blocks: blocks.map((block, index) => {
            const { id: _id, ...payload } = blockPayload(block, index)
            return payload
          }),
        })
      } else {
        saved = await replaceWeekTemplate(template.id, { name: name.trim(), blocks: blocks.map(blockPayload) })
      }
      onDone(saved)
    } catch (error) {
      toast(errorMessage(error), 'error')
    } finally { setBusy(false) }
  }

  function jobOptions(block: TemplateBlockDraft) {
    const options = (jobs ?? []).map((job) => ({ value: job.id, label: job.name }))
    // A job scoped to another location, or since deleted, still shows so an
    // unrelated edit to this block cannot quietly drop it.
    if (isJobMissingFromList(block.jobId, jobs ?? [])) {
      options.unshift({ value: block.jobId, label: block.role || 'Current job (unavailable)' })
    }
    return options
  }

  return (
    <div className="space-y-4">
      <label className="block max-w-md"><span className="text-[10px] text-zinc-500 uppercase">Template name</span><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Standard operating week" className={`${inputCls} mt-1`} /></label>
      <div className="space-y-3">
        {blocks.map((block, index) => (
          <div key={block.id} className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-3 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-zinc-300">Shift {index + 1}</span>
              {blocks.length > 1 && <button type="button" onClick={() => setBlocks((current) => current.filter((item) => item.id !== block.id))} className="text-xs text-zinc-500 hover:text-red-400">Remove shift</button>}
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {jobs ? (
                <>
                  <label className="block"><span className="text-[10px] text-zinc-500 uppercase">Shift name</span><input value={block.name} onChange={(e) => updateBlock(block.id, { name: e.target.value })} placeholder="Opening crew" className={`${inputCls} mt-1`} /></label>
                  <Select
                    label="Job"
                    options={jobOptions(block)}
                    placeholder={jobs.length ? 'No job' : 'No jobs at this location yet'}
                    value={block.jobId}
                    onChange={(event) => updateBlock(block.id, {
                      jobId: event.target.value,
                      role: roleLabelForJob(event.target.value, jobs) ?? '',
                    })}
                  />
                </>
              ) : (
                <label className="block"><span className="text-[10px] text-zinc-500 uppercase">Role</span><input value={block.role} onChange={(e) => updateBlock(block.id, { role: e.target.value })} className={`${inputCls} mt-1`} /></label>
              )}
              <label className="block"><span className="text-[10px] text-zinc-500 uppercase">Start</span><input type="time" value={block.start} onChange={(e) => updateBlock(block.id, { start: e.target.value })} className={`${inputCls} mt-1`} /></label>
              <label className="block"><span className="text-[10px] text-zinc-500 uppercase">End</span><input type="time" value={block.end} onChange={(e) => updateBlock(block.id, { end: e.target.value })} className={`${inputCls} mt-1`} /></label>
              <label className="block"><span className="text-[10px] text-zinc-500 uppercase">Staff needed</span><input value={block.required} onChange={(e) => updateBlock(block.id, { required: e.target.value })} className={`${inputCls} mt-1`} /></label>
            </div>
            <div className="grid max-w-sm grid-cols-2 gap-2">
              <label className="block"><span className="text-[10px] text-zinc-500 uppercase">Planned break (minutes)</span><input type="number" min="0" step="5" value={block.breakMinutes} onChange={(e) => updateBlock(block.id, { breakMinutes: e.target.value })} className={`${inputCls} mt-1`} /></label>
            </div>
            <div>
              <span className="text-[10px] text-zinc-500 uppercase">Repeat on</span>
              <div className="flex gap-1 mt-1">
                {WEEKDAY_LABELS.map((lbl, day) => (
                  <button type="button" key={day} aria-label={`${lbl} for shift ${index + 1}`} aria-pressed={block.days.includes(day)} onClick={() => toggleDay(block.id, day)} className={`w-9 py-1 rounded-md text-xs border ${block.days.includes(day) ? 'bg-emerald-600 border-emerald-500 text-white' : 'border-zinc-700 text-zinc-400 hover:text-zinc-100'}`}>{lbl[0]}</button>
                ))}
              </div>
              {block.days.length === 0 && <div className="mt-1 text-xs text-red-400">Select at least one day for this shift.</div>}
            </div>
          </div>
        ))}
        <button type="button" onClick={addBlock} disabled={blocks.length >= MAX_TEMPLATE_BLOCKS} className="inline-flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 disabled:cursor-not-allowed disabled:text-zinc-600"><Plus className="h-3.5 w-3.5" /> Add shift</button>
        {blocks.length >= MAX_TEMPLATE_BLOCKS && <div className="text-xs text-zinc-500">Maximum 40 shifts per template.</div>}
      </div>
      <div className="flex items-center gap-2">
        <button onClick={save} disabled={busy || !name.trim() || blocks.length === 0 || !blocksValid} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg px-3 py-1.5 disabled:opacity-50">{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} {submitLabel ?? (template ? 'Save changes' : 'Save template')}</button>
        {onCancel && <button onClick={onCancel} className="text-xs text-zinc-400 hover:text-zinc-100 px-3 py-1.5 rounded-lg border border-zinc-700">Cancel</button>}
      </div>
    </div>
  )
}

export default TemplateForm
