import { useEffect, useRef, useState } from 'react'
import { Loader2, Mic, Send, Sparkles, Square, X } from 'lucide-react'
import { useToast } from '../../ui'
import { ApiError } from '../../../api/client'
import { getScheduleHuumeSession, transcribeScheduleVoice } from '../../../api/employees/scheduleAssistant'
import { sendMessageStream } from '../../../work/api/matchaWork/messaging'
import type { HuumeStep, MWMessage, MWSendResponse, MWStreamEvent } from '../../../work/types'
import { getHuumeState } from '../../../work/utils/huumeState'
import MessageBubble from '../../../work/components/panels/MessageBubble'
import HuumeActionCard from '../../../work/components/panels/HuumeActionCard'
import ActionDocViewer from '../../../work/components/panels/HuumePanel/ActionDocViewer'
import HuumeStepTimeline from '../../../work/components/panels/HuumeStepTimeline'
import { useVoiceDictation } from '../../../hooks/useVoiceDictation'
import type { Shift } from '../../../types/employeeSchedule'
import { fmtDayLabel, fmtTime } from '../../../types/employeeSchedule'

interface ScheduleHuumePanelProps {
  firstName: string
  weekStart: string
  locationId: string | null
  locationName?: string
  selectedShifts: Shift[]
  onClearSelectedShifts(): void
  onApplied(): void
  onAutomaticActionSettled(): void
  onClose(): void
}

export function selectedShiftContext(shifts: Shift[]): string {
  if (!shifts.length) return ''
  const blocks = shifts.map((shift, index) => {
    const assignees = shift.assignments.map((assignment) => assignment.name).filter(Boolean)
    return `${index + 1}. ${fmtDayLabel(shift.starts_at)} · ${fmtTime(shift.starts_at)}–${fmtTime(shift.ends_at)} · ${shift.role || 'Untitled shift'} · ${assignees.length ? `assigned: ${assignees.join(', ')}` : 'open'} · staffing: ${assignees.length}/${shift.required_staff}`
  })
  return `\n\nSelected schedule blocks — authoritative context for this request:\n${blocks.join('\n')}\nUse these exact blocks as the shift references. Keep any assignee not named in my request on their current shift.`
}

function optimisticUserMessage(threadId: string, content: string): MWMessage {
  return {
    id: 'temp-' + Date.now(),
    thread_id: threadId,
    role: 'user',
    content,
    version_created: null,
    metadata: null,
    created_at: new Date().toISOString(),
  }
}

function appliedActionKey(response: MWSendResponse): string | null {
  const action = response.current_state?.huume_action
  if (!action || typeof action !== 'object') return null
  const record = action as Record<string, unknown>
  if (!['applied', 'created', 'updated'].includes(String(record.status))) return null
  const confirmId = record.confirm_id
  if (typeof confirmId === 'string' && confirmId) return 'confirm:' + confirmId
  const runId = response.assistant_message.metadata?.huume_run_id
  return runId ? 'run:' + runId : null
}

function settledAutomaticActionKey(state: Record<string, unknown>): string | null {
  const action = getHuumeState(state).action
  if (action?.type !== 'schedule_week_draft' || !action.auto_generated || action.status === 'proposed') return null
  return `${action.confirm_id}:${action.status}`
}

export default function ScheduleHuumePanel({ firstName, weekStart, locationId, locationName, selectedShifts, onClearSelectedShifts, onApplied, onAutomaticActionSettled, onClose }: ScheduleHuumePanelProps) {
  const { toast } = useToast()
  const [threadId, setThreadId] = useState<string | null>(null)
  const [messages, setMessages] = useState<MWMessage[]>([])
  const [currentState, setCurrentState] = useState<Record<string, unknown>>({})
  const [input, setInput] = useState('')
  const [status, setStatus] = useState('')
  const [sessionError, setSessionError] = useState<string | null>(null)
  const [sessionAttempt, setSessionAttempt] = useState(0)
  const [steps, setSteps] = useState<HuumeStep[]>([])
  const [busy, setBusy] = useState(false)
  const [voiceEnabled, setVoiceEnabled] = useState(false)
  const [startingVoice, setStartingVoice] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [voiceError, setVoiceError] = useState<string | null>(null)
  const mountedRef = useRef(true)
  const stepsRef = useRef<HuumeStep[]>([])
  const appliedKeysRef = useRef(new Set<string>())
  const settledAutomaticKeysRef = useRef(new Set<string>())
  const abortRef = useRef<AbortController | null>(null)
  const voiceTurnRef = useRef(0)
  const messagesEndRef = useRef<HTMLDivElement | null>(null)
  const dictation = useVoiceDictation({
    maxDurationSeconds: 45,
    onMaxDuration: () => { void finishVoiceTurn() },
  })

  useEffect(() => () => {
    mountedRef.current = false
    voiceTurnRef.current += 1
    abortRef.current?.abort()
  }, [])

  useEffect(() => {
    let cancelled = false
    // React StrictMode re-runs effects after their simulated cleanup. The
    // cleanup below marks the component unmounted, so restore the live state
    // before accepting this scope's session response.
    mountedRef.current = true
    abortRef.current?.abort()
    setThreadId(null)
    setMessages([])
    setCurrentState({})
    setSessionError(null)
    setStatus(locationId ? 'Opening the schedule workspace…' : '')
    if (!locationId) {
      setStatus('Choose a location to start the schedule assistant.')
      return () => { cancelled = true }
    }

    void getScheduleHuumeSession(locationId, weekStart)
      .then((session) => {
        if (cancelled || !mountedRef.current) return
        setThreadId(session.thread_id)
        setMessages(session.messages)
        setCurrentState(session.current_state || {})
        setStatus('')
      })
      .catch((error: unknown) => {
        if (cancelled || !mountedRef.current) return
        setStatus('')
        setSessionError(error instanceof Error ? error.message : 'Could not open the schedule assistant.')
      })
    return () => { cancelled = true }
  }, [locationId, weekStart, sessionAttempt])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView?.({ block: 'nearest' })
  }, [messages, steps, status])

  const settledAutomaticKey = settledAutomaticActionKey(currentState)
  useEffect(() => {
    if (!settledAutomaticKey || settledAutomaticKeysRef.current.has(settledAutomaticKey)) return
    settledAutomaticKeysRef.current.add(settledAutomaticKey)
    onAutomaticActionSettled()
  }, [onAutomaticActionSettled, settledAutomaticKey])

  async function send(contentOverride?: string) {
    const displayContent = (contentOverride ?? input).trim()
    if (!displayContent || !threadId || busy || sessionError) return
    const content = displayContent + selectedShiftContext(selectedShifts)
    setInput('')
    setBusy(true)
    setStatus('Huume is working…')
    stepsRef.current = []
    setSteps([])
    const optimistic = optimisticUserMessage(threadId, displayContent)
    setMessages((current) => [...current, optimistic])
    abortRef.current = sendMessageStream(threadId, content, {
      onEvent: (event: MWStreamEvent) => {
        if (!mountedRef.current) return
        if (event.type === 'status') setStatus(event.message)
        if (event.type === 'step') {
          stepsRef.current = [...stepsRef.current, event.data]
          setSteps(stepsRef.current)
        }
      },
      onComplete: (response: MWSendResponse) => {
        if (!mountedRef.current) return
        const persistedSteps = response.assistant_message.metadata?.huume_steps
        const completedSteps = persistedSteps || stepsRef.current
        const assistantMessage = persistedSteps
          ? response.assistant_message
          : {
              ...response.assistant_message,
              metadata: completedSteps.length
                ? { ...(response.assistant_message.metadata || {}), huume_steps: completedSteps }
                : response.assistant_message.metadata,
            }
        setMessages((current) => [
          ...current.filter((message) => message.id !== optimistic.id),
          { ...response.user_message, content: displayContent },
          assistantMessage,
        ])
        setCurrentState(response.current_state || {})
        stepsRef.current = []
        setSteps([])
        setStatus('')
        setBusy(false)
        const key = appliedActionKey(response)
        if (key && !appliedKeysRef.current.has(key)) {
          appliedKeysRef.current.add(key)
          onApplied()
        }
      },
      onError: (message: string) => {
        if (!mountedRef.current) return
        setMessages((current) => current.filter((item) => item.id !== optimistic.id))
        stepsRef.current = []
        setSteps([])
        setStatus('')
        setBusy(false)
        toast(message, 'error')
      },
    })
  }

  async function beginVoiceTurn() {
    if (busy || transcribing || startingVoice) return
    setVoiceEnabled(true)
    setStartingVoice(true)
    setVoiceError(null)
    try {
      await dictation.start()
    } catch {
      setVoiceError('Microphone access failed. Please type your request instead.')
    } finally {
      if (mountedRef.current) setStartingVoice(false)
    }
  }

  async function finishVoiceTurn() {
    if (transcribing) return
    const voiceTurn = ++voiceTurnRef.current
    setTranscribing(true)
    setVoiceError(null)
    try {
      const wav = await dictation.stop()
      if (!mountedRef.current || voiceTurn !== voiceTurnRef.current) return
      if (!wav) {
        setVoiceError('No audio captured. Try again, or type your request.')
        return
      }
      const voice = await transcribeScheduleVoice(wav)
      if (!mountedRef.current || voiceTurn !== voiceTurnRef.current) return
      if (!voice.available || !voice.transcript?.trim()) {
        setVoiceError("I couldn't understand the audio. Try again, or type your request.")
        return
      }
      await send(voice.transcript.trim())
    } catch (error: unknown) {
      if (mountedRef.current && voiceTurn === voiceTurnRef.current) {
        setVoiceError(error instanceof ApiError && error.status === 429
          ? 'Too many voice attempts. Wait a moment, or type your request.'
          : 'Voice transcription failed. Please type your request.')
      }
    } finally {
      if (mountedRef.current && voiceTurn === voiceTurnRef.current) setTranscribing(false)
    }
  }

  const action = getHuumeState(currentState).action
  const composerDisabled = !threadId || !!sessionError || busy || startingVoice || transcribing || dictation.status === 'recording'

  return (
    <section
      role="dialog"
      aria-modal="false"
      aria-label="Huume schedule assistant"
      className="absolute left-1/2 top-2 z-30 flex w-[min(460px,calc(100vw-2rem))] -translate-x-1/2 flex-col overflow-hidden rounded-xl border border-zinc-700 bg-zinc-950/95 shadow-2xl backdrop-blur"
    >
      <header className="flex items-center gap-2 border-b border-white/[0.08] px-3 py-2">
        <Sparkles className="h-4 w-4 text-emerald-300" />
        <span className="text-xs font-medium text-zinc-200">Huume · Schedule assistant</span>
        <span className="ml-auto text-[10px] text-zinc-600">{locationName || 'Location'} · {weekStart}</span>
        <button type="button" onClick={onClose} className="rounded p-1 text-zinc-500 hover:text-zinc-100" aria-label="Close schedule assistant"><X className="h-4 w-4" /></button>
      </header>
      {selectedShifts.length > 0 && (
        <div className="flex items-center gap-2 border-b border-emerald-400/20 bg-emerald-400/[0.06] px-3 py-2 text-[11px] text-emerald-100">
          <Sparkles className="h-3.5 w-3.5 shrink-0 text-emerald-300" />
          <span className="min-w-0 flex-1 truncate">Using {selectedShifts.length} selected shift{selectedShifts.length === 1 ? '' : 's'} as context</span>
          <button type="button" onClick={onClearSelectedShifts} className="shrink-0 text-emerald-300 hover:text-emerald-100">Clear</button>
        </div>
      )}
      <div className="flex max-h-[min(560px,70vh)] min-h-[220px] flex-col gap-3 overflow-y-auto px-3 py-3" role="log" aria-live="polite">
        {messages.length === 0 && !action && !sessionError && (
          <div className="space-y-3">
            <div className="text-xs text-zinc-400">Hi, {firstName}. I can review this week or build the whole schedule from confirmed availability.</div>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                disabled={!threadId || busy}
                onClick={() => { void send('Build this entire week for me. Check readiness first, preserve existing assignments, and use existing draft shifts as demand; if there are none, use the saved week template when there is only one choice. Show me the proposal for approval.') }}
                className="rounded-lg border border-emerald-500/30 bg-emerald-500/[0.08] px-3 py-2 text-left text-[11px] text-emerald-200 hover:bg-emerald-500/[0.14] disabled:opacity-40"
              >
                <span className="block font-medium">Build my week</span>
                <span className="mt-0.5 block text-emerald-300/60">Generate an editable draft</span>
              </button>
              <button
                type="button"
                disabled={!threadId || busy}
                onClick={() => { void send('Check whether this week is ready for you to build. Tell me about missing availability, staffing demand, or template choices, but do not generate it yet.') }}
                className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-left text-[11px] text-zinc-300 hover:bg-white/[0.06] disabled:opacity-40"
              >
                <span className="block font-medium">Check readiness</span>
                <span className="mt-0.5 block text-zinc-500">Find missing inputs first</span>
              </button>
            </div>
          </div>
        )}
        {action?.type === 'schedule_week_draft' && action.auto_generated && action.status === 'proposed' && (
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/[0.08] px-3 py-2 text-xs text-emerald-100">
            Huume prepared this suggestion automatically. Review the staffing below, then approve it or describe the changes you want.
          </div>
        )}
        {messages.map((message) => <MessageBubble key={message.id} message={message} lightMode={false} />)}
        {action && <HuumeActionCard action={action} streaming={busy} onSendChat={(text) => { void send(text) }} />}
        {action?.type === 'schedule_week_draft' && (
          <div className="max-h-80 overflow-y-auto rounded-lg border border-white/[0.08] bg-white/[0.02]">
            <ActionDocViewer action={action} lightMode={false} />
          </div>
        )}
        {steps.length > 0 && <div className="mr-4 rounded-lg bg-white/[0.03] px-3 py-2"><HuumeStepTimeline steps={steps} live /></div>}
        {status && <div className="flex items-center gap-2 text-[11px] text-zinc-500"><Loader2 className="h-3.5 w-3.5 animate-spin" />{status}</div>}
        {sessionError && (
          <div role="alert" className="rounded-lg border border-amber-500/30 bg-amber-500/[0.08] p-3 text-xs text-amber-200">
            <p>{sessionError}</p>
            <button type="button" onClick={() => setSessionAttempt((attempt) => attempt + 1)} className="mt-2 rounded border border-amber-400/40 px-2 py-1 text-[11px] hover:bg-amber-400/10">Try again</button>
          </div>
        )}
        {dictation.status === 'recording' && <div className="flex items-center gap-2 text-[11px] text-red-300"><span className="h-2 w-2 animate-pulse rounded-full bg-red-400" />Listening · tap stop when finished</div>}
        {voiceError && <p className="text-[11px] text-amber-400">{voiceError}</p>}
        <div ref={messagesEndRef} />
      </div>
      <form onSubmit={(event) => { event.preventDefault(); void send() }} className="flex items-center gap-2 border-t border-white/[0.08] p-2">
        <label htmlFor="schedule-huume-input" className="sr-only">Ask Huume about this schedule</label>
        <input id="schedule-huume-input" value={input} onChange={(event) => setInput(event.target.value)} disabled={composerDisabled} placeholder="Try: add an opener Monday" className="min-w-0 flex-1 rounded-lg border border-white/[0.08] bg-white/[0.04] px-3 py-2 text-xs text-zinc-100 outline-none placeholder:text-zinc-600" />
        <button type="button" onClick={() => { void (dictation.status === 'recording' ? finishVoiceTurn() : beginVoiceTurn()) }} disabled={!threadId || busy || startingVoice || transcribing || !!sessionError} className={'rounded-lg border p-2 disabled:opacity-40 ' + (dictation.status === 'recording' ? 'border-red-400/50 bg-red-500/15 text-red-300' : 'border-zinc-700 text-zinc-300 hover:border-emerald-500/50 hover:text-emerald-300')} aria-label={dictation.status === 'recording' ? 'Stop voice recording' : 'Talk to Huume'} title={dictation.status === 'recording' ? 'Stop recording' : 'Talk to Huume'}>
          {startingVoice || transcribing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : dictation.status === 'recording' ? <Square className="h-3.5 w-3.5 fill-current" /> : <Mic className="h-3.5 w-3.5" />}
        </button>
        <button type="submit" disabled={composerDisabled || !input.trim()} className="rounded-lg bg-emerald-500 p-2 text-zinc-950 disabled:opacity-40" aria-label="Send scheduling question"><Send className="h-4 w-4" /></button>
      </form>
      {voiceEnabled && <p className="border-t border-white/[0.05] px-3 py-1.5 text-[10px] text-zinc-600">Audio is transcribed for this turn and is not saved.</p>}
    </section>
  )
}
