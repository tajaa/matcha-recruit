import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bot, Loader2, Mic, Send, Sparkles, Square, X } from 'lucide-react'
import { useToast } from '../../ui'
import {
  applyScheduleChat,
  discardScheduleChat,
  sendScheduleChatMessage,
  transcribeScheduleVoice,
} from '../../../api/employees/scheduleChat'
import { ApiError } from '../../../api/client'
import type { ScheduleChatApplyResponse, ScheduleChatProposal, ScheduleChatTurnResponse } from '../../../types/scheduleChat'
import { fmtTime } from '../../../types/employeeSchedule'
import { useVoiceDictation } from '../../../hooks/useVoiceDictation'

interface ScheduleChatPanelProps {
  firstName: string
  weekStart: string
  locationId: string | null
  locationName?: string
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

function isScheduleKickoff(text: string): boolean {
  const normalized = text.toLowerCase().replace(/[^a-z0-9'\s]/g, ' ').replace(/\s+/g, ' ').trim()
  return /^(?:hey huume\s+)?(?:let'?s|can we|help me|i want to)\s+(?:make|build|start|work on)(?:\s+some)?\s+(?:the\s+)?schedules?$/.test(normalized)
}

function spokenTurn(turn: ScheduleChatTurnResponse): string {
  const proposal = turn.proposal
  if (turn.kind === 'unactionable' || !proposal) return turn.message
  if (turn.kind === 'clarify') {
    const options = proposal.clarify_options || []
    return `${proposal.clarify_question || turn.message}${options.length ? ` Options are ${options.join(', ')}.` : ''}`
  }
  const summary = proposalSummary(proposal)
  const lead = turn.message && turn.message !== summary ? `${turn.message} ${summary}.` : `${summary}.`
  return `${lead} Review the proposal, then say confirm to apply it or cancel to discard it.`
}

function formatVoiceTime(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

export default function ScheduleChatPanel({ firstName, weekStart, locationId, locationName, editPublished, onApplied, onClose }: ScheduleChatPanelProps) {
  const { toast } = useToast()
  const [messages, setMessages] = useState<ChatMessage[]>(() => [
    { id: 'welcome', role: 'assistant', text: `Hi, ${firstName}. Tell me what you want to build, change, save as a template, or review.` },
  ])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [pendingClarifyId, setPendingClarifyId] = useState<string | null>(null)
  const [activeProposal, setActiveProposal] = useState<ScheduleChatTurnResponse | null>(null)
  const [voiceEnabled, setVoiceEnabled] = useState(false)
  const [startingVoice, setStartingVoice] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [voiceError, setVoiceError] = useState<string | null>(null)
  const mountedRef = useRef(true)
  const voiceTurnRef = useRef(0)
  const dictation = useVoiceDictation({ maxDurationSeconds: 45, onMaxDuration: () => { void finishVoiceTurn() } })

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      voiceTurnRef.current += 1
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) window.speechSynthesis.cancel()
    }
  }, [])

  function speak(text: string) {
    if (!voiceEnabled || !text.trim() || typeof window === 'undefined' || !('speechSynthesis' in window) || typeof SpeechSynthesisUtterance === 'undefined') return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.rate = 0.98
    window.speechSynthesis.speak(utterance)
  }

  function appendVoiceExchange(userText: string, assistantText: string) {
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: 'user', text: userText },
      { id: crypto.randomUUID(), role: 'assistant', text: assistantText },
    ])
    speak(assistantText)
  }

  function kickoffResponse(): string {
    const scope = locationName ? ` at ${locationName}` : ''
    return `Okay, ${firstName}. What should we do with the week of ${weekStart}${scope}?`
  }

  async function send(message: string, existingProposalId?: string) {
    const value = message.trim()
    if (!value || busy) return
    const proposalId = existingProposalId ?? pendingClarifyId ?? undefined
    setInput('')
    setPendingClarifyId(null)
    if (!proposalId && !activeProposal && isScheduleKickoff(value)) {
      appendVoiceExchange(value, kickoffResponse())
      return
    }
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'user', text: value }])
    setBusy(true)
    try {
      const turn = await sendScheduleChatMessage({
        message: value, week_start: weekStart, location_id: locationId,
        edit_published: editPublished, existing_proposal_id: proposalId,
      })
      if (!mountedRef.current) return
      setPendingClarifyId(turn.kind === 'clarify' ? turn.proposal_id : null)
      if (turn.kind === 'proposal') setActiveProposal(turn)
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'assistant', turn }])
      speak(spokenTurn(turn))
    } catch (error) {
      if (mountedRef.current) toast(error instanceof Error ? error.message : 'Could not ask the scheduling assistant', 'error')
    } finally {
      if (mountedRef.current) setBusy(false)
    }
  }

  async function apply(turn: ScheduleChatTurnResponse, source: 'button' | 'voice' = 'button'): Promise<ScheduleChatApplyResponse | null> {
    if (!turn.proposal_id || busy || (source === 'button' && transcribing)) return null
    if (source === 'voice' && editPublished) {
      const text = 'Editing published shifts is enabled. Use the Apply button to confirm this change.'
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'assistant', text }])
      speak(text)
      return null
    }
    setBusy(true)
    try {
      const result = await applyScheduleChat(turn.proposal_id, { as_draft: true, edit_published: editPublished })
      if (!mountedRef.current) return null
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'assistant', result }])
      setActiveProposal((current) => current?.proposal_id === turn.proposal_id ? null : current)
      if (result.shift_ids.length) onApplied()
      speak(result.text)
      return result
    } catch (error) {
      if (mountedRef.current) toast(error instanceof Error ? error.message : 'Could not apply the schedule proposal', 'error')
      return null
    } finally {
      if (mountedRef.current) setBusy(false)
    }
  }

  async function discard(turn: ScheduleChatTurnResponse, source: 'button' | 'voice' = 'button') {
    if (!turn.proposal_id || busy || (source === 'button' && transcribing)) return
    setBusy(true)
    try {
      await discardScheduleChat(turn.proposal_id)
      if (!mountedRef.current) return
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'assistant', text: 'Discarded.' }])
      setActiveProposal((current) => current?.proposal_id === turn.proposal_id ? null : current)
      speak('Discarded.')
    } catch (error) {
      if (mountedRef.current) toast(error instanceof Error ? error.message : 'Could not discard the proposal', 'error')
    } finally {
      if (mountedRef.current) setBusy(false)
    }
  }

  async function beginVoiceTurn() {
    if (busy || transcribing || startingVoice) return
    setVoiceEnabled(true)
    setStartingVoice(true)
    setVoiceError(null)
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) window.speechSynthesis.cancel()
    try {
      await dictation.start()
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
      if (!voice.available) {
        setVoiceError("I couldn't understand the audio. Try again, or type your request.")
        return
      }
      const transcript = voice.transcript?.trim()
      if (!transcript) {
        setVoiceError("I didn't hear a request. Try speaking closer to the microphone.")
        return
      }

      if (activeProposal) {
        setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'user', text: transcript }])
        if (voice.command === 'confirm') {
          await apply(activeProposal, 'voice')
        } else if (voice.command === 'cancel') {
          await discard(activeProposal, 'voice')
        } else {
          const text = 'I still have a proposal waiting. Say confirm or cancel before starting another request.'
          setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'assistant', text }])
          speak(text)
        }
        return
      }

      await send(transcript)
    } catch (error) {
      if (mountedRef.current && voiceTurn === voiceTurnRef.current) {
        setVoiceError(error instanceof ApiError && error.status === 429
          ? 'Too many voice attempts. Wait a moment, or type your request.'
          : 'Voice transcription failed. Please type your request.')
      }
    } finally {
      if (mountedRef.current && voiceTurn === voiceTurnRef.current) setTranscribing(false)
    }
  }

  function close() {
    voiceTurnRef.current += 1
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) window.speechSynthesis.cancel()
    onClose()
  }

  return (
    <section className="absolute left-1/2 top-2 z-30 flex w-[min(440px,calc(100vw-2rem))] -translate-x-1/2 flex-col overflow-hidden rounded-xl border border-zinc-700 bg-zinc-950/95 shadow-2xl backdrop-blur">
      <header className="flex items-center gap-2 border-b border-white/[0.08] px-3 py-2">
        <Sparkles className="h-4 w-4 text-emerald-300" />
        <span className="text-xs font-medium text-zinc-200">Huume · Schedule assistant</span>
        <span className="ml-auto text-[10px] text-zinc-600">Week of {weekStart}</span>
        <button onClick={close} className="rounded p-1 text-zinc-500 hover:text-zinc-100" aria-label="Close schedule assistant"><X className="h-4 w-4" /></button>
      </header>
      <div className="max-h-[min(440px,55vh)] space-y-2 overflow-y-auto p-3">
        {messages.map((message) => (
          <div key={message.id} className={message.role === 'user' ? 'ml-8 rounded-lg bg-zinc-800 px-3 py-2 text-xs text-zinc-200' : 'mr-3'}>
            {message.role === 'assistant' && <Bot className="mb-1 h-3.5 w-3.5 text-emerald-300" />}
            {message.text && <p className="text-xs leading-5 text-zinc-300">{message.text}</p>}
            {message.result && (
              <div>
                <p className="text-xs leading-5 text-emerald-300">{message.result.text}</p>
                {message.result.week_template_id && (
                  <Link
                    to={`/ops/schedule?tab=templates&template=${message.result.week_template_id}`}
                    className="mt-1 inline-block text-[11px] text-emerald-400 underline decoration-emerald-400/40 hover:text-emerald-300"
                  >
                    View template →
                  </Link>
                )}
              </div>
            )}
            {message.turn && <TurnCard turn={message.turn} active={message.turn.proposal_id === activeProposal?.proposal_id} disabled={busy || startingVoice || transcribing || dictation.status === 'recording'} onApply={() => void apply(message.turn!)} onDiscard={() => void discard(message.turn!)} onClarify={(answer) => void send(answer, message.turn!.proposal_id ?? undefined)} />}
          </div>
        ))}
        {busy && <div className="flex items-center gap-2 text-[11px] text-zinc-500"><Loader2 className="h-3 w-3 animate-spin" /> Checking the schedule...</div>}
        {dictation.status === 'recording' && <div className="flex items-center gap-2 text-[11px] text-red-300"><span className="h-2 w-2 animate-pulse rounded-full bg-red-400" /> Listening · {formatVoiceTime(dictation.elapsedSeconds)} · tap stop when finished</div>}
        {startingVoice && <div className="flex items-center gap-2 text-[11px] text-zinc-500"><Loader2 className="h-3 w-3 animate-spin text-emerald-400" /> Starting microphone...</div>}
        {transcribing && <div className="flex items-center gap-2 text-[11px] text-zinc-500"><Loader2 className="h-3 w-3 animate-spin text-emerald-400" /> Transcribing your request...</div>}
        {dictation.status === 'denied' && <p className="text-[11px] text-amber-400">Microphone access denied. Enable it in your browser settings, or type your request.</p>}
        {dictation.status === 'error' && <p className="text-[11px] text-amber-400">Could not start the microphone. Please type your request.</p>}
        {voiceError && <p className="text-[11px] text-amber-400">{voiceError}</p>}
      </div>
      <form onSubmit={(event) => { event.preventDefault(); void send(input) }} className="flex items-center gap-2 border-t border-white/[0.08] p-2">
        <input value={input} onChange={(event) => setInput(event.target.value)} disabled={busy || startingVoice || transcribing || dictation.status === 'recording'} placeholder={pendingClarifyId ? 'Reply to the question above…' : 'Try: add an opener Monday'} className="min-w-0 flex-1 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-xs text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-emerald-500/50" />
        <button type="button" onClick={() => { void (dictation.status === 'recording' ? finishVoiceTurn() : beginVoiceTurn()) }} disabled={busy || startingVoice || transcribing} className={`rounded-lg border p-2 disabled:opacity-40 ${dictation.status === 'recording' ? 'border-red-400/50 bg-red-500/15 text-red-300' : 'border-zinc-700 text-zinc-300 hover:border-emerald-500/50 hover:text-emerald-300'}`} aria-label={dictation.status === 'recording' ? 'Stop voice recording' : 'Talk to Huume'} title={dictation.status === 'recording' ? 'Stop recording' : 'Talk to Huume'}>
          {startingVoice || transcribing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : dictation.status === 'recording' ? <Square className="h-3.5 w-3.5 fill-current" /> : <Mic className="h-3.5 w-3.5" />}
        </button>
        <button disabled={busy || startingVoice || transcribing || dictation.status === 'recording' || !input.trim()} className="rounded-lg bg-emerald-400 p-2 text-zinc-950 disabled:opacity-40" aria-label="Send scheduling question"><Send className="h-3.5 w-3.5" /></button>
      </form>
      {voiceEnabled && <p className="border-t border-white/[0.05] px-3 py-1.5 text-[10px] text-zinc-600">Audio is transcribed for this turn and is not saved.</p>}
    </section>
  )
}

function TurnCard({ turn, active, disabled, onApply, onDiscard, onClarify }: { turn: ScheduleChatTurnResponse; active: boolean; disabled: boolean; onApply(): void; onDiscard(): void; onClarify(answer: string): void }) {
  const proposal = turn.proposal
  if (turn.kind === 'unactionable' || !proposal) return <p className="text-xs leading-5 text-zinc-300">{turn.message}</p>
  if (turn.kind === 'clarify') return (
    <div className="rounded-lg border border-amber-500/20 bg-amber-500/[0.06] p-2 text-xs text-zinc-300">
      <p>{proposal.clarify_question || turn.message}</p>
      {(proposal.clarify_options || []).length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1.5">{(proposal.clarify_options || []).map((option) => <button key={option} onClick={() => onClarify(option)} disabled={disabled} className="rounded border border-zinc-700 px-2 py-1 text-[11px] text-zinc-300 hover:border-emerald-500/50 disabled:opacity-40">{option}</button>)}</div>
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
      <div className="mt-3 flex gap-2"><button onClick={onApply} disabled={!active || disabled} className="rounded bg-emerald-400 px-2.5 py-1 text-[11px] font-medium text-zinc-950 disabled:opacity-40">Add as draft</button><button onClick={onDiscard} disabled={!active || disabled} className="rounded border border-zinc-700 px-2.5 py-1 text-[11px] text-zinc-400 disabled:opacity-40">Discard</button></div>
    </div>
  )
}
