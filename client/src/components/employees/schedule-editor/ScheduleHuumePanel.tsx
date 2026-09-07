import { useEffect, useRef } from 'react'
import { History, Loader2, Mic, Plus, Send, Sparkles, Square, Trash2, X } from 'lucide-react'
import type { ScheduleHuumeThread } from '../../../hooks/employees/useScheduleHuumeThread'
import MessageBubble from '../../../work/components/panels/MessageBubble'
import HuumeActionCard from '../../../work/components/panels/HuumeActionCard'
import HuumeChoiceChips from '../../../work/components/panels/HuumeChoiceChips'
import ActionDocViewer from '../../../work/components/panels/HuumePanel/ActionDocViewer'
import HuumeStepTimeline from '../../../work/components/panels/HuumeStepTimeline'
import type { Shift } from '../../../types/employeeSchedule'

export { SETUP_KICKOFF_PROMPT, relativeChatTime, selectedShiftContext } from '../../../hooks/employees/useScheduleHuumeThread'
import { SETUP_KICKOFF_PROMPT, relativeChatTime } from '../../../hooks/employees/useScheduleHuumeThread'

interface ScheduleHuumePanelProps {
  /** The thread state and actions — `useScheduleHuumeThread`, owned by the page. */
  thread: ScheduleHuumeThread
  firstName: string
  weekStart: string
  locationId: string | null
  locationName?: string
  selectedShifts: Shift[]
  /** False while this location's hours / staffing pattern / leader rule are
   *  unsaved. The week builder refuses in that state, so the empty state
   *  offers the interview instead of a build that cannot succeed. */
  weekRulesEstablished?: boolean
  onClearSelectedShifts(): void
  /** Mounted as a column of the workspace (fills its container) rather than
   *  the old floating dialog. */
  embedded?: boolean
  onClose?(): void
  /** When the staged action has a review the workspace renders it in its own
   *  pane; the card in the thread stays for Confirm/Cancel and a "Review →". */
  onOpenReview?(): void
}

/** Presentational Huume thread for the schedule workspace: messages, the
 *  staged-action card, choice chips, live steps, composer and push-to-talk.
 *  All state lives in `useScheduleHuumeThread`. */
export default function ScheduleHuumePanel({ thread, firstName, weekStart, locationId, locationName, selectedShifts, weekRulesEstablished = true, onClearSelectedShifts, embedded = false, onClose, onOpenReview }: ScheduleHuumePanelProps) {
  const messagesEndRef = useRef<HTMLDivElement | null>(null)
  const { messages, steps, status, action, choice, busy, sessionError, composerDisabled, voice } = thread

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView?.({ block: 'nearest' })
  }, [messages, steps, status])

  const reviewable = !!(action && (action.type === 'schedule_change' || action.type === 'schedule_week_draft') && 'review' in action && action.review && action.status === 'proposed')

  return (
    <section
      role={embedded ? 'region' : 'dialog'}
      aria-modal={embedded ? undefined : 'false'}
      aria-label="Huume schedule assistant"
      className={embedded
        ? 'flex h-full min-h-0 flex-col bg-zinc-950'
        : 'absolute left-1/2 top-2 z-30 flex w-[min(460px,calc(100vw-2rem))] -translate-x-1/2 flex-col overflow-hidden rounded-xl border border-zinc-700 bg-zinc-950/95 shadow-2xl backdrop-blur'}
    >
      <header className="flex shrink-0 items-center gap-2 border-b border-white/[0.08] px-3 py-2">
        <Sparkles className="h-4 w-4 text-emerald-300" />
        <span className="text-xs font-medium text-zinc-200">Huume · Schedule assistant</span>
        <span className="ml-auto truncate text-[10px] text-zinc-600">{locationName || 'Location'} · {weekStart}</span>
        <button
          type="button"
          onClick={() => thread.openChat(null)}
          disabled={busy || !locationId}
          className="rounded p-1 text-zinc-500 hover:text-emerald-300 disabled:opacity-40"
          aria-label="New chat"
          title="New chat"
        ><Plus className="h-4 w-4" /></button>
        <button
          type="button"
          onClick={() => { thread.setHistoryOpen(!thread.historyOpen); if (!thread.historyOpen) thread.refreshSessions() }}
          disabled={!locationId}
          aria-expanded={thread.historyOpen}
          className={'rounded p-1 disabled:opacity-40 ' + (thread.historyOpen ? 'text-emerald-300' : 'text-zinc-500 hover:text-zinc-100')}
          aria-label="Previous chats"
          title="Previous chats"
        ><History className="h-4 w-4" /></button>
        {onClose && <button type="button" onClick={onClose} className="rounded p-1 text-zinc-500 hover:text-zinc-100" aria-label="Close schedule assistant"><X className="h-4 w-4" /></button>}
      </header>
      {thread.historyOpen && (
        <div className="max-h-64 shrink-0 overflow-y-auto border-b border-white/[0.08] bg-white/[0.02]">
          {thread.sessions.length === 0 ? (
            <p className="px-3 py-3 text-[11px] text-zinc-500">No earlier chats for this location and week.</p>
          ) : (
            <ul className="divide-y divide-white/[0.05]">
              {thread.sessions.map((summary) => (
                <li key={summary.session_id} className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => thread.openChat(summary.session_id)}
                    disabled={busy}
                    className={'min-w-0 flex-1 px-3 py-2 text-left disabled:opacity-40 hover:bg-white/[0.04] ' + (summary.session_id === thread.sessionId ? 'bg-emerald-500/[0.08]' : '')}
                  >
                    <span className="block truncate text-[11px] text-zinc-200">{summary.title}</span>
                    <span className="mt-0.5 block text-[10px] text-zinc-500">
                      {relativeChatTime(summary.last_activity_at)} · {summary.message_count} message{summary.message_count === 1 ? '' : 's'}
                      {summary.session_id === thread.sessionId ? ' · open' : ''}
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => { void thread.archiveChat(summary) }}
                    disabled={busy}
                    className="mr-2 shrink-0 rounded p-1 text-zinc-600 hover:text-red-300 disabled:opacity-40"
                    aria-label={`Remove chat: ${summary.title}`}
                    title="Remove from history"
                  ><Trash2 className="h-3.5 w-3.5" /></button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {selectedShifts.length > 0 && (
        <div className="flex shrink-0 items-center gap-2 border-b border-emerald-400/20 bg-emerald-400/[0.06] px-3 py-2 text-[11px] text-emerald-100">
          <Sparkles className="h-3.5 w-3.5 shrink-0 text-emerald-300" />
          <span className="min-w-0 flex-1 truncate">Using {selectedShifts.length} selected shift{selectedShifts.length === 1 ? '' : 's'} as context</span>
          <button type="button" onClick={onClearSelectedShifts} className="shrink-0 text-emerald-300 hover:text-emerald-100">Clear</button>
        </div>
      )}
      <div className={`flex min-h-[220px] flex-col gap-3 overflow-y-auto px-3 py-3 ${embedded ? 'flex-1' : 'max-h-[min(560px,70vh)]'}`} role="log" aria-live="polite">
        {messages.length === 0 && !action && !sessionError && (
          <div className="space-y-3">
            <div className="text-xs text-zinc-400">
              {weekRulesEstablished
                ? `Hi, ${firstName}. I can review this week, fill the open shifts, or build the whole schedule from confirmed availability.`
                : `Hi, ${firstName}. Before I can build a week here I need this location's hours, its usual shift blocks, and whether a lead has to be on.`}
            </div>
            <div className="grid grid-cols-2 gap-2">
              {weekRulesEstablished ? (
                <button
                  type="button"
                  disabled={!thread.threadId || busy}
                  onClick={() => { void thread.send('Build this entire week for me. Check readiness first, preserve existing assignments, and use existing draft shifts as demand; if there are none, use the saved week template when there is only one choice. Show me the proposal for approval.') }}
                  className="rounded-lg border border-emerald-500/30 bg-emerald-500/[0.08] px-3 py-2 text-left text-[11px] text-emerald-200 hover:bg-emerald-500/[0.14] disabled:opacity-40"
                >
                  <span className="block font-medium">Build my week</span>
                  <span className="mt-0.5 block text-emerald-300/60">Generate an editable draft</span>
                </button>
              ) : (
                <button
                  type="button"
                  disabled={!thread.threadId || busy}
                  onClick={() => { void thread.send(SETUP_KICKOFF_PROMPT) }}
                  className="rounded-lg border border-amber-500/30 bg-amber-500/[0.08] px-3 py-2 text-left text-[11px] text-amber-200 hover:bg-amber-500/[0.14] disabled:opacity-40"
                >
                  <span className="block font-medium">Set up this location</span>
                  <span className="mt-0.5 block text-amber-300/60">A few questions, then I can build</span>
                </button>
              )}
              {weekRulesEstablished ? (
                <button
                  type="button"
                  disabled={!thread.threadId || busy}
                  onClick={() => { void thread.send('Fill the open shifts this week.') }}
                  className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-left text-[11px] text-zinc-300 hover:bg-white/[0.06] disabled:opacity-40"
                >
                  <span className="block font-medium">Fill the open shifts</span>
                  <span className="mt-0.5 block text-zinc-500">Server picks people under the rules</span>
                </button>
              ) : (
                <button
                  type="button"
                  disabled={!thread.threadId || busy}
                  onClick={() => { void thread.send('Check whether this week is ready for you to build. Tell me about missing availability, staffing demand, or template choices, but do not generate it yet.') }}
                  className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-left text-[11px] text-zinc-300 hover:bg-white/[0.06] disabled:opacity-40"
                >
                  <span className="block font-medium">Check readiness</span>
                  <span className="mt-0.5 block text-zinc-500">Find missing inputs first</span>
                </button>
              )}
            </div>
          </div>
        )}
        {action?.type === 'schedule_week_draft' && action.auto_generated && action.status === 'proposed' && (
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/[0.08] px-3 py-2 text-xs text-emerald-100">
            Huume prepared this suggestion automatically. Review the staffing below, then approve it or describe the changes you want.
          </div>
        )}
        {messages.map((message) => <MessageBubble key={message.id} message={message} lightMode={false} />)}
        {action && <HuumeActionCard action={action} streaming={busy} onSendChat={(text) => { void thread.send(text) }} />}
        {reviewable && onOpenReview && (
          <button type="button" onClick={onOpenReview} className="self-start rounded-lg border border-emerald-500/30 px-2.5 py-1 text-[11px] text-emerald-200 hover:bg-emerald-500/[0.08]">
            Open the review pane →
          </button>
        )}
        {choice && !busy && <HuumeChoiceChips choice={choice} disabled={composerDisabled} onPick={(text) => { void thread.send(text) }} />}
        {(action?.type === 'schedule_week_draft' || action?.type === 'schedule_location_profile') && (
          <div className="max-h-80 overflow-y-auto rounded-lg border border-white/[0.08] bg-white/[0.02]">
            <ActionDocViewer action={action} lightMode={false} />
          </div>
        )}
        {steps.length > 0 && <div className="mr-4 rounded-lg bg-white/[0.03] px-3 py-2"><HuumeStepTimeline steps={steps} live /></div>}
        {status && <div className="flex items-center gap-2 text-[11px] text-zinc-500"><Loader2 className="h-3.5 w-3.5 animate-spin" />{status}</div>}
        {sessionError && (
          <div role="alert" className="rounded-lg border border-amber-500/30 bg-amber-500/[0.08] p-3 text-xs text-amber-200">
            <p>{sessionError}</p>
            <button type="button" onClick={thread.retry} className="mt-2 rounded border border-amber-400/40 px-2 py-1 text-[11px] hover:bg-amber-400/10">Try again</button>
          </div>
        )}
        {voice.recording && <div className="flex items-center gap-2 text-[11px] text-red-300"><span className="h-2 w-2 animate-pulse rounded-full bg-red-400" />Listening · tap stop when finished</div>}
        {voice.error && <p className="text-[11px] text-amber-400">{voice.error}</p>}
        <div ref={messagesEndRef} />
      </div>
      <form onSubmit={(event) => { event.preventDefault(); void thread.send() }} className="flex shrink-0 items-center gap-2 border-t border-white/[0.08] p-2">
        <label htmlFor="schedule-huume-input" className="sr-only">Ask Huume about this schedule</label>
        <input id="schedule-huume-input" value={thread.input} onChange={(event) => thread.setInput(event.target.value)} disabled={composerDisabled} placeholder="Try: add an opener Monday" className="min-w-0 flex-1 rounded-lg border border-white/[0.08] bg-white/[0.04] px-3 py-2 text-xs text-zinc-100 outline-none placeholder:text-zinc-600" />
        <button type="button" onClick={() => { void (voice.recording ? voice.finish() : voice.begin()) }} disabled={!thread.threadId || busy || voice.starting || voice.transcribing || !!sessionError} className={'rounded-lg border p-2 disabled:opacity-40 ' + (voice.recording ? 'border-red-400/50 bg-red-500/15 text-red-300' : 'border-zinc-700 text-zinc-300 hover:border-emerald-500/50 hover:text-emerald-300')} aria-label={voice.recording ? 'Stop voice recording' : 'Talk to Huume'} title={voice.recording ? 'Stop recording' : 'Talk to Huume'}>
          {voice.starting || voice.transcribing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : voice.recording ? <Square className="h-3.5 w-3.5 fill-current" /> : <Mic className="h-3.5 w-3.5" />}
        </button>
        <button type="submit" disabled={composerDisabled || !thread.input.trim()} className="rounded-lg bg-emerald-500 p-2 text-zinc-950 disabled:opacity-40" aria-label="Send scheduling question"><Send className="h-4 w-4" /></button>
      </form>
      {voice.enabled && <p className="shrink-0 border-t border-white/[0.05] px-3 py-1.5 text-[10px] text-zinc-600">Audio is transcribed for this turn and is not saved.</p>}
    </section>
  )
}
