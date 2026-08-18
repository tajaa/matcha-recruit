import { useState } from 'react'
import { Bot, Loader2, Send, Sparkles, X } from 'lucide-react'
import { useToast } from '../../ui'
import { applyScheduleChat, discardScheduleChat, sendScheduleChatMessage } from '../../../api/employees/scheduleChat'
import type { ScheduleChatApplyResponse, ScheduleChatProposal, ScheduleChatTurnResponse } from '../../../types/scheduleChat'
import { fmtTime } from '../../../types/employeeSchedule'

interface ScheduleChatPanelProps {
  weekStart: string
  locationId: string | null
  editPublished: boolean
  onApplied(): void
  onClose(): void
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text?: string
  turn?: ScheduleChatTurnResponse
  result?: ScheduleChatApplyResponse
}

function proposalSummary(proposal: ScheduleChatProposal): string {
  if (proposal.kind === 'template' && proposal.week_template) {
    return `Week template: ${proposal.week_template.name} (${proposal.week_template.blocks.length} block${proposal.week_template.blocks.length === 1 ? '' : 's'})`
  }
  if (proposal.kind === 'apply_template') {
    return `Apply ${proposal.week_template_name}: ${proposal.total_shifts} shift${proposal.total_shifts === 1 ? '' : 's'}, ${proposal.start_date}–${proposal.end_date}`
  }
  if (proposal.ops?.length) return `${proposal.ops.length} schedule change${proposal.ops.length === 1 ? '' : 's'}`
  return `${proposal.shifts?.length ?? 0} shift${proposal.shifts?.length === 1 ? '' : 's'}`
}

export default function ScheduleChatPanel({ weekStart, locationId, editPublished, onApplied, onClose }: ScheduleChatPanelProps) {
  const { toast } = useToast()
  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: 'welcome', role: 'assistant', text: 'Ask about coverage, test a schedule idea, edit a draft, save a reusable week, or apply one you already saved.' },
  ])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [pendingClarifyId, setPendingClarifyId] = useState<string | null>(null)

  async function send(message: string, existingProposalId?: string) {
    const value = message.trim()
    if (!value || busy) return
    const proposalId = existingProposalId ?? pendingClarifyId ?? undefined
    setInput('')
    setPendingClarifyId(null)
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'user', text: value }])
    setBusy(true)
    try {
      const turn = await sendScheduleChatMessage({
        message: value, week_start: weekStart, location_id: locationId,
        edit_published: editPublished, existing_proposal_id: proposalId,
      })
      setPendingClarifyId(turn.kind === 'clarify' && !(turn.proposal?.clarify_options?.length) ? turn.proposal_id : null)
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'assistant', turn }])
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Could not ask the scheduling assistant', 'error')
    } finally {
      setBusy(false)
    }
  }

  async function apply(turn: ScheduleChatTurnResponse) {
    if (!turn.proposal_id) return
    setBusy(true)
    try {
      const result = await applyScheduleChat(turn.proposal_id, { as_draft: true, edit_published: editPublished })
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'assistant', result }])
      if (result.shift_ids.length) onApplied()
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Could not apply the schedule proposal', 'error')
    } finally {
      setBusy(false)
    }
  }

  async function discard(turn: ScheduleChatTurnResponse) {
    if (!turn.proposal_id) return
    try {
      await discardScheduleChat(turn.proposal_id)
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'assistant', text: 'Discarded.' }])
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Could not discard the proposal', 'error')
    }
  }

  return (
    <section className="absolute left-1/2 top-2 z-30 flex w-[min(440px,calc(100vw-2rem))] -translate-x-1/2 flex-col overflow-hidden rounded-xl border border-zinc-700 bg-zinc-950/95 shadow-2xl backdrop-blur">
      <header className="flex items-center gap-2 border-b border-white/[0.08] px-3 py-2">
        <Sparkles className="h-4 w-4 text-emerald-300" />
        <span className="text-xs font-medium text-zinc-200">Schedule assistant</span>
        <span className="ml-auto text-[10px] text-zinc-600">Week of {weekStart}</span>
        <button onClick={onClose} className="rounded p-1 text-zinc-500 hover:text-zinc-100" aria-label="Close schedule assistant"><X className="h-4 w-4" /></button>
      </header>
      <div className="max-h-[min(440px,55vh)] space-y-2 overflow-y-auto p-3">
        {messages.map((message) => (
          <div key={message.id} className={message.role === 'user' ? 'ml-8 rounded-lg bg-zinc-800 px-3 py-2 text-xs text-zinc-200' : 'mr-3'}>
            {message.role === 'assistant' && <Bot className="mb-1 h-3.5 w-3.5 text-emerald-300" />}
            {message.text && <p className="text-xs leading-5 text-zinc-300">{message.text}</p>}
            {message.result && <p className="text-xs leading-5 text-emerald-300">{message.result.text}</p>}
            {message.turn && <TurnCard turn={message.turn} onApply={() => void apply(message.turn!)} onDiscard={() => void discard(message.turn!)} onClarify={(answer) => void send(answer, message.turn!.proposal_id ?? undefined)} />}
          </div>
        ))}
        {busy && <div className="flex items-center gap-2 text-[11px] text-zinc-500"><Loader2 className="h-3 w-3 animate-spin" /> Checking the schedule...</div>}
      </div>
      <form onSubmit={(event) => { event.preventDefault(); void send(input) }} className="flex items-center gap-2 border-t border-white/[0.08] p-2">
        <input value={input} onChange={(event) => setInput(event.target.value)} disabled={busy} placeholder={pendingClarifyId ? 'Reply to the question above…' : 'Try: add an opener Monday'} className="min-w-0 flex-1 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-xs text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-emerald-500/50" />
        <button disabled={busy || !input.trim()} className="rounded-lg bg-emerald-400 p-2 text-zinc-950 disabled:opacity-40" aria-label="Send scheduling question"><Send className="h-3.5 w-3.5" /></button>
      </form>
    </section>
  )
}

function TurnCard({ turn, onApply, onDiscard, onClarify }: { turn: ScheduleChatTurnResponse; onApply(): void; onDiscard(): void; onClarify(answer: string): void }) {
  const proposal = turn.proposal
  if (turn.kind === 'unactionable' || !proposal) return <p className="text-xs leading-5 text-zinc-300">{turn.message}</p>
  if (turn.kind === 'clarify') return (
    <div className="rounded-lg border border-amber-500/20 bg-amber-500/[0.06] p-2 text-xs text-zinc-300">
      <p>{proposal.clarify_question || turn.message}</p>
      {(proposal.clarify_options || []).length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1.5">{(proposal.clarify_options || []).map((option) => <button key={option} onClick={() => onClarify(option)} className="rounded border border-zinc-700 px-2 py-1 text-[11px] text-zinc-300 hover:border-emerald-500/50">{option}</button>)}</div>
      ) : (
        <p className="mt-2 text-[11px] text-zinc-500">Type your answer below.</p>
      )}
    </div>
  )
  return (
    <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/[0.04] p-2 text-xs text-zinc-300">
      <p className="font-medium text-zinc-200">{turn.message || proposalSummary(proposal)}</p>
      {proposal.shifts?.map((shift) => <div key={`${shift.starts_at}-${shift.label}`} className="mt-2 border-t border-white/[0.06] pt-2"><div className="flex justify-between"><span>{shift.label}</span><span>{fmtTime(shift.starts_at)}-{fmtTime(shift.ends_at)}</span></div><div className="text-[11px] text-zinc-500">{shift.assignees.map((a) => a.name).join(', ') || `${shift.open_slots} open`}</div></div>)}
      {proposal.ops?.map((op, index) => <div key={`${op.kind}-${index}`} className="mt-2 text-[11px] text-zinc-400">{op.kind}: {op.from_employee_name || ''}{op.to_employee_name ? ` -> ${op.to_employee_name}` : ''}</div>)}
      {proposal.week_template?.blocks.map((block) => <div key={block.name} className="mt-2 border-t border-white/[0.06] pt-2 text-[11px] text-zinc-400">{block.name}: {block.start_time}-{block.end_time}, {block.required_staff} staff, {block.days_of_week.length} days</div>)}
      {proposal.blocks_preview?.map((block) => <div key={block.name} className="mt-2 border-t border-white/[0.06] pt-2 text-[11px] text-zinc-400">{block.name}: {block.start_time}-{block.end_time}, {block.shifts} shifts</div>)}
      <div className="mt-3 flex gap-2"><button onClick={onApply} className="rounded bg-emerald-400 px-2.5 py-1 text-[11px] font-medium text-zinc-950">Add as draft</button><button onClick={onDiscard} className="rounded border border-zinc-700 px-2.5 py-1 text-[11px] text-zinc-400">Discard</button></div>
    </div>
  )
}
