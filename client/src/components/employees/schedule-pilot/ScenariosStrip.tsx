import { useState } from 'react'
import { Check, FlaskConical, Loader2, Play, Plus, Sparkles, Trash2, X } from 'lucide-react'
import { LABEL } from '../../ui'
import type { Scenario, ScenarioNotice, ScenarioRequest } from '../../../hooks/employees/useScheduleScenarios'
import type { ScheduleComplianceStatus } from '../../../types/employeeSchedule'

export interface StagedChip {
  label: string
  staged: number
  unfilled: number
  rejected: number
  compliance: ScheduleComplianceStatus
}

export interface ScenariosStripProps {
  scenarios: Scenario[]
  selectedIds: string[]
  onSelect(proposalId: string, options?: { compare?: boolean }): void
  /** The thread's staged action, when it carries a review. */
  staged: StagedChip | null
  stagedSelected: boolean
  onSelectStaged(): void
  previewing: boolean
  notice: ScenarioNotice | null
  onDismissNotice(): void
  onPreview(request: ScenarioRequest): void
  jobs: Array<{ id: string; name: string }>
  people: Array<{ id: string; name: string }>
  selectedShiftIds: string[]
  onApply(proposalId: string): void
  onStage(proposalId: string): void
  onDiscard(proposalId: string): void
  /** False until the thread is open — staging writes into it. */
  canStage: boolean
  disabled?: boolean
}

const DOT: Record<ScheduleComplianceStatus, string> = {
  verified: 'bg-emerald-400', advisory: 'bg-amber-400', unmapped: 'bg-amber-500', unavailable: 'bg-red-400',
}

function Chip({ active, onClick, onCompareClick, children, tone = 'default' }: {
  active: boolean
  onClick(): void
  onCompareClick?(): void
  children: React.ReactNode
  tone?: 'default' | 'huume'
}) {
  return (
    <button
      type="button"
      onClick={(event) => { if (event.shiftKey && onCompareClick) onCompareClick(); else onClick() }}
      aria-pressed={active}
      className={`flex shrink-0 items-center gap-2 rounded-lg border px-2.5 py-1.5 text-left text-[11px] transition-colors ${active ? 'border-emerald-500/50 bg-emerald-500/[0.08] text-zinc-100' : tone === 'huume' ? 'border-emerald-500/20 text-emerald-200/90 hover:bg-emerald-500/[0.06]' : 'border-white/[0.08] text-zinc-300 hover:bg-white/[0.04]'}`}
    >
      {children}
    </button>
  )
}

type Scope = 'all' | 'job' | 'selected'

function NewScenarioForm({ jobs, people, selectedShiftIds, previewing, onPreview, onClose }: {
  jobs: ScenariosStripProps['jobs']
  people: ScenariosStripProps['people']
  selectedShiftIds: string[]
  previewing: boolean
  onPreview(request: ScenarioRequest): void
  onClose(): void
}) {
  const [label, setLabel] = useState('')
  const [scope, setScope] = useState<Scope>('all')
  const [jobId, setJobId] = useState('')
  const [onlyId, setOnlyId] = useState('')
  const [excludeIds, setExcludeIds] = useState<string[]>([])
  const [allowSplit, setAllowSplit] = useState(false)
  const excluded = people.filter((person) => excludeIds.includes(person.id))

  function submit(event: React.FormEvent) {
    event.preventDefault()
    onPreview({
      label: label.trim() || null,
      job_id: scope === 'job' && jobId ? jobId : null,
      shift_ids: scope === 'selected' ? selectedShiftIds : null,
      employee_id: onlyId || null,
      exclude_employee_ids: excludeIds.length ? excludeIds : null,
      allow_split_shift: allowSplit,
    })
  }

  const inputClass = 'rounded-md border border-white/[0.08] bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-emerald-500/50'
  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-3 border-t border-white/[0.06] bg-white/[0.015] px-4 py-3" aria-label="New scenario">
      <label className="flex flex-col gap-1">
        <span className={LABEL}>Name</span>
        <input value={label} onChange={(event) => setLabel(event.target.value)} placeholder="e.g. Spread the leads" className={`${inputClass} w-44`} />
      </label>
      <fieldset className="flex flex-col gap-1">
        <legend className={LABEL}>Fill which</legend>
        <div className="flex items-center gap-1">
          {([
            ['all', 'All open'],
            ['job', 'One job'],
            ['selected', `Selected (${selectedShiftIds.length})`],
          ] as Array<[Scope, string]>).map(([value, text]) => (
            <button
              key={value}
              type="button"
              onClick={() => setScope(value)}
              disabled={value === 'selected' && selectedShiftIds.length === 0}
              aria-pressed={scope === value}
              className={`rounded-md border px-2 py-1 text-[11px] disabled:opacity-40 ${scope === value ? 'border-emerald-500/50 bg-emerald-500/[0.08] text-zinc-100' : 'border-white/[0.08] text-zinc-400 hover:text-zinc-100'}`}
            >{text}</button>
          ))}
          {scope === 'job' && (
            <select value={jobId} onChange={(event) => setJobId(event.target.value)} aria-label="Job" className={inputClass}>
              <option value="">Pick a job</option>
              {jobs.map((job) => <option key={job.id} value={job.id}>{job.name}</option>)}
            </select>
          )}
        </div>
      </fieldset>
      <label className="flex flex-col gap-1">
        <span className={LABEL}>Only this person</span>
        <select value={onlyId} onChange={(event) => setOnlyId(event.target.value)} className={`${inputClass} w-40`}>
          <option value="">Anyone qualified</option>
          {people.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}
        </select>
      </label>
      <div className="flex flex-col gap-1">
        <span className={LABEL}>Leave out</span>
        <div className="flex flex-wrap items-center gap-1">
          {excluded.map((person) => (
            <span key={person.id} className="inline-flex items-center gap-1 rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[11px] text-zinc-200">
              {person.name}
              <button type="button" onClick={() => setExcludeIds((current) => current.filter((id) => id !== person.id))} aria-label={`Include ${person.name} again`} className="text-zinc-500 hover:text-zinc-100"><X className="h-3 w-3" /></button>
            </span>
          ))}
          <select
            value=""
            onChange={(event) => { if (event.target.value) setExcludeIds((current) => [...current, event.target.value]) }}
            aria-label="Leave someone out"
            className={`${inputClass} w-36`}
          >
            <option value="">Add a person…</option>
            {people.filter((person) => !excludeIds.includes(person.id) && person.id !== onlyId).map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}
          </select>
        </div>
      </div>
      <label className="flex items-center gap-1.5 pb-1 text-[11px] text-zinc-400">
        <input type="checkbox" checked={allowSplit} onChange={(event) => setAllowSplit(event.target.checked)} /> Allow split shifts
      </label>
      <div className="ml-auto flex items-center gap-2 pb-0.5">
        <button type="button" onClick={onClose} className="rounded-md px-2 py-1.5 text-[11px] text-zinc-500 hover:text-zinc-200">Cancel</button>
        <button type="submit" disabled={previewing || (scope === 'job' && !jobId)} className="inline-flex items-center gap-1.5 rounded-md bg-emerald-500 px-3 py-1.5 text-[11px] font-medium text-zinc-950 disabled:opacity-40">
          {previewing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FlaskConical className="h-3.5 w-3.5" />} Preview
        </button>
      </div>
    </form>
  )
}

/** The strip across the top of the workspace: every fill scenario the
 *  manager ran (each a free server-side simulation), plus the thread's staged
 *  action when it has a review. Click a chip to review it; shift-click a
 *  second to compare; the selected scenario's Stage / Apply / Discard live on
 *  the chip. Nothing here writes a shift by itself. */
export default function ScenariosStrip({
  scenarios, selectedIds, onSelect, staged, stagedSelected, onSelectStaged, previewing, notice, onDismissNotice,
  onPreview, jobs, people, selectedShiftIds, onApply, onStage, onDiscard, canStage, disabled = false,
}: ScenariosStripProps) {
  const [formOpen, setFormOpen] = useState(false)
  const primary = selectedIds.length === 1 ? scenarios.find((item) => item.proposal_id === selectedIds[0]) ?? null : null

  return (
    <div className="shrink-0 border-b border-white/[0.06] bg-zinc-950/90">
      <div className="flex items-center gap-2 overflow-x-auto px-4 py-2">
        <span className={`${LABEL} shrink-0`}>Scenarios</span>
        {staged && (
          <Chip active={stagedSelected} onClick={onSelectStaged} tone="huume">
            <Sparkles className="h-3 w-3 text-emerald-300" />
            <span className="max-w-[16rem] truncate">{staged.label}</span>
            <span className="font-mono text-[10px] tabular-nums text-zinc-400">{staged.staged} staged{staged.rejected ? ` · ${staged.rejected} refused` : ''}{staged.unfilled ? ` · ${staged.unfilled} open` : ''}</span>
            <span className={`h-1.5 w-1.5 rounded-full ${DOT[staged.compliance]}`} title={`Compliance: ${staged.compliance}`} />
          </Chip>
        )}
        {scenarios.map((scenario) => {
          const active = selectedIds.includes(scenario.proposal_id)
          const stagedCount = scenario.review.assignments.length
          return (
            <Chip
              key={scenario.proposal_id}
              active={active}
              onClick={() => onSelect(scenario.proposal_id)}
              onCompareClick={() => onSelect(scenario.proposal_id, { compare: true })}
            >
              <FlaskConical className="h-3 w-3 text-zinc-500" />
              <span className="max-w-[14rem] truncate">{scenario.label}</span>
              <span className="font-mono text-[10px] tabular-nums text-zinc-400">{stagedCount} staged{scenario.review.unfilled.length ? ` · ${scenario.review.unfilled.length} open` : ''}</span>
              <span className={`h-1.5 w-1.5 rounded-full ${DOT[scenario.review.compliance_status]}`} title={`Compliance: ${scenario.review.compliance_status}`} />
              {scenario.status === 'applied' && <span className="rounded bg-emerald-500/15 px-1 font-mono text-[9px] uppercase text-emerald-300">applied</span>}
              {scenario.status === 'staged' && <span className="rounded bg-emerald-500/15 px-1 font-mono text-[9px] uppercase text-emerald-300">staged</span>}
              {scenario.status === 'applying' && <Loader2 className="h-3 w-3 animate-spin text-zinc-400" />}
            </Chip>
          )
        })}
        <button
          type="button"
          onClick={() => setFormOpen((open) => !open)}
          disabled={disabled}
          aria-expanded={formOpen}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-dashed border-white/[0.12] px-2.5 py-1.5 text-[11px] text-zinc-400 hover:border-emerald-500/40 hover:text-emerald-200 disabled:opacity-40"
        >
          <Plus className="h-3 w-3" /> New scenario
        </button>
        {primary && primary.status !== 'applied' && (
          <div className="ml-auto flex shrink-0 items-center gap-1.5">
            <button
              type="button"
              onClick={() => onStage(primary.proposal_id)}
              disabled={!canStage || primary.status !== 'ready'}
              title={canStage ? 'Make this the staged change in the Huume thread — confirm it there' : 'Open the Huume thread to stage'}
              className="inline-flex items-center gap-1.5 rounded-md border border-emerald-500/40 px-2.5 py-1.5 text-[11px] text-emerald-200 hover:bg-emerald-500/[0.08] disabled:opacity-40"
            ><Sparkles className="h-3 w-3" /> Stage in thread</button>
            <button
              type="button"
              onClick={() => onApply(primary.proposal_id)}
              disabled={primary.status !== 'ready'}
              className="inline-flex items-center gap-1.5 rounded-md bg-zinc-100 px-2.5 py-1.5 text-[11px] font-medium text-zinc-900 hover:bg-white disabled:opacity-40"
            ><Play className="h-3 w-3" /> Apply now</button>
            <button
              type="button"
              onClick={() => onDiscard(primary.proposal_id)}
              disabled={primary.status === 'applying'}
              aria-label={`Discard ${primary.label}`}
              className="rounded-md border border-white/[0.08] p-1.5 text-zinc-500 hover:text-red-300 disabled:opacity-40"
            ><Trash2 className="h-3.5 w-3.5" /></button>
          </div>
        )}
        {primary?.status === 'applied' && (
          <span className="ml-auto inline-flex shrink-0 items-center gap-1 text-[11px] text-emerald-300"><Check className="h-3 w-3" /> Applied</span>
        )}
      </div>
      {notice && (
        <div role="status" className="flex items-start gap-2 border-t border-amber-500/20 bg-amber-500/[0.06] px-4 py-2 text-[11px] text-amber-100">
          <span className="min-w-0 flex-1">
            {notice.message}
            {notice.unfilled.length > 0 && (
              <span className="text-amber-200/70"> · {notice.unfilled.slice(0, 3).map((item) => `${item.role || 'shift'}: ${item.reason}`).join('; ')}{notice.unfilled.length > 3 ? ` · +${notice.unfilled.length - 3} more` : ''}</span>
            )}
          </span>
          <button type="button" onClick={onDismissNotice} aria-label="Dismiss" className="shrink-0 text-amber-300 hover:text-amber-100"><X className="h-3.5 w-3.5" /></button>
        </div>
      )}
      {formOpen && (
        <NewScenarioForm
          jobs={jobs}
          people={people}
          selectedShiftIds={selectedShiftIds}
          previewing={previewing}
          onPreview={(request) => { onPreview(request); setFormOpen(false) }}
          onClose={() => setFormOpen(false)}
        />
      )}
    </div>
  )
}
