import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2, Circle, Lock, Loader2, XCircle, PlayCircle, Send, FileSignature, Scale, BookOpen } from 'lucide-react'
import type { HuumePlan, HuumePlanStep, HuumeOffer } from '../../types'
import { approveHuumePlan, executeHuumePlan } from '../../api/matchaWork/huume'
import { getHuumeState, hasHuumeContent } from '../../utils/huumeState'
import HuumeActionCard from './HuumeActionCard'
import { useToast } from '../../../components/ui'

interface HuumePlanCardProps {
  state: Record<string, unknown>
  threadId: string
  lightMode?: boolean
  onStateUpdate: (offerId: string, plan: HuumePlan) => void
  /** Disables Approve/Execute mid-turn — the model can mutate this plan via
   * its own execute_approved_steps tool while streaming; the advisory lock
   * makes a race safe server-side, but the UI shouldn't invite one, and it
   * guarantees onExecuted's full message refetch can't clobber an in-flight
   * optimistic message. */
  streaming?: boolean
  /** Powers the staged-action Confirm/Cancel card — sends the literal chat
   * text through the thread's normal send path. */
  onSendChat?: (text: string) => void
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

function OfferChip({ offer, lightMode }: { offer: HuumeOffer; lightMode?: boolean }) {
  const label = offer.status === 'accepted' ? 'Accepted' : offer.status === 'rejected' ? 'Declined' : offer.status === 'sent' ? 'Sent — awaiting response' : 'Draft'
  const color = offer.status === 'accepted'
    ? (lightMode ? 'bg-emerald-50 text-emerald-700 border-emerald-300' : 'bg-emerald-950/40 text-emerald-300 border-emerald-800')
    : offer.status === 'rejected'
      ? (lightMode ? 'bg-red-50 text-red-700 border-red-300' : 'bg-red-950/40 text-red-300 border-red-800')
      : offer.status === 'sent'
        ? (lightMode ? 'bg-amber-50 text-amber-700 border-amber-300' : 'bg-amber-950/40 text-amber-300 border-amber-800')
        : (lightMode ? 'bg-zinc-50 text-zinc-600 border-zinc-300' : 'bg-zinc-800/40 text-zinc-400 border-zinc-700')
  return (
    <div className={`flex items-center gap-1.5 text-[11px] px-2 py-1 rounded border w-fit ${color}`}>
      {offer.status === 'accepted' ? <FileSignature size={12} /> : <Send size={12} />}
      Offer: {label}
      {offer.status === 'accepted' && offer.signed_name && <span>· signed by {offer.signed_name}</span>}
    </div>
  )
}

/** One candidate's plan section — its own selection/busy/error state so
 * approving/executing one candidate never disturbs another's UI. */
function PlanSection({
  offerId, plan, threadId, lightMode, onStateUpdate, streaming, onExecuted,
}: {
  offerId: string; plan: HuumePlan; threadId: string; lightMode?: boolean
  onStateUpdate: (offerId: string, plan: HuumePlan) => void
  streaming?: boolean; onExecuted?: () => void
}) {
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
    <div className={`border-b ${border}`}>
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

      <div className={`px-3 py-2.5 flex flex-col gap-1.5`}>
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

/** Right-panel card for a Huume thread — offer status chip, staged-action
 * confirm card, Legal/Handbook Pilot chips, and one plan section per active
 * candidate (plans are keyed by offer_id, since a thread can be onboarding
 * several candidates at once). Mirrors InventoryPanel/ProjectPanel's shape:
 * reads straight off `thread.current_state`, calls back into the thread's
 * own state setter on a successful write. */
export default function HuumePlanCard({ state, threadId, lightMode, onStateUpdate, streaming, onSendChat, onExecuted }: HuumePlanCardProps) {
  const huume = getHuumeState(state)
  const { plans, offer, action, legal, handbook } = huume
  const planEntries = Object.entries(plans)

  const th = { bg: lightMode ? 'bg-white' : 'bg-zinc-900', border: lightMode ? 'border-zinc-200' : 'border-zinc-800' }
  const chipBase = 'flex items-center gap-1.5 text-[11px] px-2 py-1 rounded border w-fit'
  const legalChip = lightMode ? 'bg-amber-50 text-amber-700 border-amber-300 hover:bg-amber-100' : 'bg-amber-950/40 text-amber-300 border-amber-800 hover:bg-amber-950/60'
  const handbookChip = lightMode ? 'bg-zinc-50 text-zinc-600 border-zinc-300 hover:bg-zinc-100' : 'bg-zinc-800/40 text-zinc-400 border-zinc-700 hover:bg-zinc-800/70'

  if (!hasHuumeContent(huume)) {
    return (
      <div className={`flex w-full flex-1 min-w-0 items-center justify-center ${th.bg}`}>
        <p className={`text-sm px-4 text-center ${lightMode ? 'text-zinc-500' : 'text-zinc-500'}`}>
          Ask Huume to draft an offer or build an onboarding plan to see it here.
        </p>
      </div>
    )
  }

  return (
    <div className={`flex w-full flex-1 min-w-0 flex-col ${th.bg} overflow-y-auto`}>
      <div className={`px-3 py-2.5 border-b ${th.border} flex flex-col gap-1.5`}>
        <div className={`text-xs font-medium uppercase tracking-wide ${lightMode ? 'text-zinc-500' : 'text-zinc-500'}`}>Huume</div>
        {offer && <OfferChip offer={offer} lightMode={lightMode} />}
        {action && (
          <HuumeActionCard action={action} variant="panel" lightMode={lightMode} streaming={streaming} onSendChat={onSendChat} />
        )}
        {legal && (
          // Deep link into the pilot page — FeatureGate there handles a
          // company that lost the legal_defense flag after this was written.
          <Link to="/app/legal-pilot" className={`${chipBase} ${legalChip}`}>
            <Scale size={12} /> Legal matter: {legal.title ?? legal.matter_id}
          </Link>
        )}
        {handbook && handbook.pending_drafts?.length > 0 && (
          <Link to="/app/handbook-pilot" className={`${chipBase} ${handbookChip}`}>
            <BookOpen size={12} /> Handbook: {handbook.pending_drafts.length} pending draft{handbook.pending_drafts.length !== 1 ? 's' : ''}
          </Link>
        )}
      </div>

      {planEntries.map(([offerId, plan]) => (
        <PlanSection
          key={offerId} offerId={offerId} plan={plan} threadId={threadId} lightMode={lightMode}
          onStateUpdate={onStateUpdate} streaming={streaming} onExecuted={onExecuted}
        />
      ))}
    </div>
  )
}
