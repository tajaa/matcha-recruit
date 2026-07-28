import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2, Circle, Lock, Loader2, XCircle, PlayCircle } from 'lucide-react'
import type { HuumePlan, HuumePlanStep } from '../../../types'
import { approveHuumePlan, executeHuumePlan } from '../../../api/matchaWork/huume'
import { useToast } from '../../../../components/ui'

interface PlanViewerProps {
  offerId: string
  plan: HuumePlan
  threadId: string
  lightMode?: boolean
  onStateUpdate: (offerId: string, plan: HuumePlan) => void
  /** Disables Approve/Execute mid-turn — the model can mutate this plan via
   * its own execute_approved_steps tool while streaming; the advisory lock
   * makes a race safe server-side, but the UI shouldn't invite one, and it
   * guarantees onExecuted's full message refetch can't clobber an in-flight
   * optimistic message. */
  streaming?: boolean
  /** REST plan-execute posts an assistant summary message
   * (metadata.huume_event: "plan_executed") but does not broadcast it — this
   * is how it appears without a reload. */
  onExecuted?: () => void
}

function StepRow({
  step, selected, onToggle, lightMode,
}: { step: HuumePlanStep; selected: boolean; onToggle: () => void; lightMode?: boolean }) {
  const border = lightMode ? 'border-zinc-200' : 'border-zinc-800'
  const muted = lightMode ? 'text-zinc-500' : 'text-zinc-500'

  let icon = <Circle size={14} className={lightMode ? 'text-zinc-400' : 'text-zinc-600'} />
  const interactive = step.status === 'proposed'
  if (step.status === 'approved') icon = <CheckCircle2 size={14} className="text-emerald-500" />
  else if (step.status === 'executing') icon = <Loader2 size={14} className="animate-spin text-amber-500" />
  else if (step.status === 'done') icon = <CheckCircle2 size={14} className="text-emerald-500" />
  else if (step.status === 'skipped') icon = <Lock size={14} className={muted} />
  else if (step.status === 'failed') icon = <XCircle size={14} className="text-red-500" />

  return (
    <div className={`flex items-start gap-2 px-2 py-1.5 border-b last:border-b-0 ${border}`}>
      <button
        type="button"
        disabled={!interactive}
        onClick={onToggle}
        className={`mt-0.5 shrink-0 ${interactive ? 'cursor-pointer' : 'cursor-default'}`}
        title={interactive ? 'Select for approval' : step.status}
      >
        {interactive ? (
          selected
            ? <CheckCircle2 size={14} className="text-emerald-500" />
            : <Circle size={14} className={lightMode ? 'text-zinc-400' : 'text-zinc-600'} />
        ) : icon}
      </button>
      <div className="flex-1 min-w-0">
        <div className={`text-xs ${lightMode ? 'text-zinc-800' : 'text-zinc-200'} ${step.status === 'skipped' ? 'opacity-60' : ''}`}>
          {step.label}
        </div>
        {step.status === 'skipped' && step.reason && (
          <div className={`text-[10px] ${muted}`}>Skipped — {step.reason}</div>
        )}
        {step.status === 'failed' && step.error && (
          <div className="text-[10px] text-red-500">{step.error}</div>
        )}
        {step.status === 'done' && step.record_id && (
          // Only create_employee has a canonical detail page today — other
          // record_ids (portal invite, training records, …) have nowhere to
          // deep-link to yet, so they keep the bare "Done" caption.
          step.key === 'create_employee' ? (
            <Link to={`/app/employees/${step.record_id}`} className="text-[10px] text-emerald-500 hover:text-emerald-400">
              View employee record →
            </Link>
          ) : (
            <div className={`text-[10px] ${muted}`}>Done</div>
          )
        )}
      </div>
    </div>
  )
}

/** One candidate's onboarding plan — its own selection/busy/error state so
 * approving/executing one candidate never disturbs another's UI when a
 * thread has several plan artifacts. */
export default function PlanViewer({
  offerId, plan, threadId, lightMode, onStateUpdate, streaming, onExecuted,
}: PlanViewerProps) {
  const { toast } = useToast()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState<'approve' | 'execute' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [lastSummary, setLastSummary] = useState<string | null>(null)

  const border = lightMode ? 'border-zinc-200' : 'border-zinc-800'
  const proposedSteps = plan.steps.filter((s) => s.status === 'proposed')
  const hasApproved = plan.steps.some((s) => s.status === 'approved')
  const doneCount = plan.steps.filter((s) => s.status === 'done').length
  const progressPct = plan.steps.length > 0 ? (doneCount / plan.steps.length) * 100 : 0

  function toggle(key: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  async function handleApprove(all: boolean) {
    setBusy('approve'); setError(null)
    const count = all ? proposedSteps.length : selected.size
    try {
      const keys = all ? undefined : Array.from(selected)
      const { plan: updated } = await approveHuumePlan(threadId, offerId, keys)
      onStateUpdate(offerId, updated)
      setSelected(new Set())
      toast(`${count} step${count !== 1 ? 's' : ''} approved`, 'success')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to approve steps')
    } finally {
      setBusy(null)
    }
  }

  async function handleExecute() {
    setBusy('execute'); setError(null)
    try {
      const { plan: updated, summary } = await executeHuumePlan(threadId, offerId)
      onStateUpdate(offerId, updated)
      setLastSummary(summary)
      toast('Onboarding steps executed', 'success')
      onExecuted?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to execute plan')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="flex w-full flex-1 flex-col overflow-y-auto">
      <div className={`px-3 py-2 border-b ${border}`}>
        <div className={`text-xs font-medium ${lightMode ? 'text-zinc-800' : 'text-zinc-200'}`}>
          Onboarding plan {plan.employee.first_name ? `— ${plan.employee.first_name}${plan.employee.last_name ? ' ' + plan.employee.last_name : ''}` : ''}
        </div>
        {plan.employee.position_title && (
          <div className={`text-[10px] ${lightMode ? 'text-zinc-500' : 'text-zinc-500'}`}>{plan.employee.position_title}</div>
        )}
        <div className={`text-[10px] ${lightMode ? 'text-zinc-500' : 'text-zinc-500'}`}>
          Status: {plan.status} · {doneCount}/{plan.steps.length} done
        </div>
        <div className={`mt-1 h-px w-full ${lightMode ? 'bg-zinc-200' : 'bg-zinc-700/50'}`}>
          <div className="h-px bg-emerald-500" style={{ width: `${progressPct}%` }} />
        </div>
      </div>

      <div>
        {plan.steps.map((s) => (
          <StepRow key={s.key} step={s} selected={selected.has(s.key)} onToggle={() => toggle(s.key)} lightMode={lightMode} />
        ))}
      </div>

      <div className="px-3 py-2.5 flex flex-col gap-1.5">
        {error && <p className="text-[11px] text-red-500">{error}</p>}
        {lastSummary && !error && <p className={`text-[11px] ${lightMode ? 'text-zinc-500' : 'text-zinc-500'}`}>{lastSummary}</p>}
        <div className="flex gap-1.5">
          <button
            type="button"
            disabled={busy !== null || streaming || proposedSteps.length === 0}
            onClick={() => handleApprove(true)}
            className="flex-1 flex items-center justify-center gap-1 text-xs font-medium px-2 py-1.5 rounded bg-orange-600 hover:bg-orange-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white"
          >
            {busy === 'approve' ? <Loader2 size={12} className="animate-spin" /> : 'Approve all'}
          </button>
          <button
            type="button"
            disabled={busy !== null || streaming || selected.size === 0}
            onClick={() => handleApprove(false)}
            className="flex-1 text-xs font-medium px-2 py-1.5 rounded border border-orange-700 text-orange-400 hover:bg-orange-950/40 disabled:opacity-40"
          >
            Approve selected
          </button>
        </div>
        <button
          type="button"
          disabled={busy !== null || streaming || !hasApproved}
          onClick={handleExecute}
          className="flex items-center justify-center gap-1.5 text-xs font-medium px-2 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white"
        >
          {busy === 'execute' ? <Loader2 size={12} className="animate-spin" /> : <><PlayCircle size={13} /> Execute approved steps</>}
        </button>
      </div>
    </div>
  )
}
