import { useCallback, useEffect, useRef, useState } from 'react'
import { useToast } from '../../components/ui'
import { ApiError } from '../../api/client'
import {
  archiveScheduleHuumeSession,
  getScheduleHuumeSession,
  listScheduleHuumeSessions,
  transcribeScheduleVoice,
  type ScheduleHuumeSessionSummary,
} from '../../api/employees/scheduleAssistant'
import { sendMessageStream } from '../../work/api/matchaWork/messaging'
import type { HuumeAction, HuumeChoice, HuumeStep, MWMessage, MWSendResponse, MWStreamEvent } from '../../work/types'
import { getHuumeState } from '../../work/utils/huumeState'
import { useVoiceDictation } from '../useVoiceDictation'
import type { Shift } from '../../types/employeeSchedule'
import { fmtDayLabel, fmtTime } from '../../types/employeeSchedule'

/** The interview kickoff. Deliberately tells Huume NOT to build: the server
 *  refuses anyway, and a request that asks for both reads as permission to
 *  try the build first. */
export const SETUP_KICKOFF_PROMPT = "Set up this location's week. Read the saved scheduling profile first, then ask me one question at a time for whatever is still missing — the hours for every day, the shift blocks a normal week needs, and whether a shift lead has to be on every shift. Don't build the week yet."

export function selectedShiftContext(shifts: Shift[]): string {
  if (!shifts.length) return ''
  const blocks = shifts.map((shift, index) => {
    const assignees = shift.assignments.map((assignment) => assignment.name).filter(Boolean)
    return `${index + 1}. ${fmtDayLabel(shift.starts_at)} · ${fmtTime(shift.starts_at)}–${fmtTime(shift.ends_at)} · ${shift.role || 'Untitled shift'} · ${assignees.length ? `assigned: ${assignees.join(', ')}` : 'open'} · staffing: ${assignees.length}/${shift.required_staff}`
  })
  return `\n\nSelected schedule blocks — authoritative context for this request:\n${blocks.join('\n')}\nUse these exact blocks as the shift references. Keep any assignee not named in my request on their current shift.`
}

export function relativeChatTime(value: string, now = Date.now()): string {
  const at = new Date(value).getTime()
  if (Number.isNaN(at)) return ''
  const minutes = Math.floor((now - at) / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return days < 7 ? `${days}d ago` : new Date(at).toLocaleDateString()
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
  const status = String(record.status)
  const applied = ['applied', 'created', 'updated'].includes(status)
  // A failed confirmed schedule attempt may still have applied a subset of a
  // batch, or committed successfully before its verification read failed.
  // Reconcile the board for both outcomes; the confirm id keeps this one-shot.
  const scheduleAttemptSettled = record.type === 'schedule_change' && status === 'failed'
  if (!applied && !scheduleAttemptSettled) return null
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

export interface ScheduleHuumeThreadOptions {
  locationId: string | null
  weekStart: string
  /** Shifts the manager picked on the board — appended to every turn as
   *  authoritative context (`selectedShiftContext`). */
  selectedShifts: Shift[]
  /** A confirmed action landed: the caller reloads the week, the planning
   *  inputs and the week rules. Fired once per applied action. */
  onApplied(): void
  /** An automatically prepared proposal is no longer `proposed` (applied,
   *  cancelled, failed) — the caller drops its "review suggestion" banner. */
  onAutomaticActionSettled(): void
}

export interface ScheduleHuumeVoice {
  enabled: boolean
  starting: boolean
  transcribing: boolean
  recording: boolean
  error: string | null
  begin(): Promise<void>
  finish(): Promise<void>
}

export interface ScheduleHuumeThread {
  threadId: string | null
  sessionId: string | null
  sessions: ScheduleHuumeSessionSummary[]
  historyOpen: boolean
  setHistoryOpen(open: boolean): void
  refreshSessions(): void
  messages: MWMessage[]
  currentState: Record<string, unknown>
  /** Replace the thread state from outside the stream — the Schedule Pilot
   *  does this after adopting a fill scenario as the staged action. */
  setCurrentState(state: Record<string, unknown>): void
  action: HuumeAction | undefined
  choice: HuumeChoice | undefined
  input: string
  setInput(value: string): void
  status: string
  sessionError: string | null
  retry(): void
  steps: HuumeStep[]
  busy: boolean
  composerDisabled: boolean
  send(contentOverride?: string): Promise<void>
  openChat(sessionId: string | null): void
  archiveChat(summary: ScheduleHuumeSessionSummary): Promise<void>
  voice: ScheduleHuumeVoice
}

/** The schedule workspace's durable Huume thread: session open/resume,
 *  history, streaming turns with the board's selected shifts as context, and
 *  push-to-talk. Lifted out of `ScheduleHuumePanel` so the page owns
 *  `currentState` — the staged action's `review` is what the review pane
 *  renders, and the panel is presentational. */
export function useScheduleHuumeThread({ locationId, weekStart, selectedShifts, onApplied, onAutomaticActionSettled }: ScheduleHuumeThreadOptions): ScheduleHuumeThread {
  const { toast } = useToast()
  const [threadId, setThreadId] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  // Which chat the next mount opens: null starts a fresh one, an id reopens
  // the chat the manager picked out of history.
  const [resumeSessionId, setResumeSessionId] = useState<string | null>(null)
  const [sessions, setSessions] = useState<ScheduleHuumeSessionSummary[]>([])
  const [historyOpen, setHistoryOpen] = useState(false)
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
  const selectedShiftsRef = useRef(selectedShifts)
  selectedShiftsRef.current = selectedShifts
  const onAppliedRef = useRef(onApplied)
  onAppliedRef.current = onApplied
  const onSettledRef = useRef(onAutomaticActionSettled)
  onSettledRef.current = onAutomaticActionSettled

  const dictation = useVoiceDictation({
    maxDurationSeconds: 45,
    onMaxDuration: () => { void finishVoiceTurn() },
  })

  useEffect(() => () => {
    mountedRef.current = false
    voiceTurnRef.current += 1
    abortRef.current?.abort()
  }, [])

  const refreshSessions = useCallback(() => {
    if (!locationId) return
    void listScheduleHuumeSessions(locationId, weekStart)
      .then((result) => { if (mountedRef.current) setSessions(result.sessions) })
      .catch(() => { /* history is a convenience; a failed list never blocks the chat */ })
  }, [locationId, weekStart])

  useEffect(() => {
    let cancelled = false
    // React StrictMode re-runs effects after their simulated cleanup. The
    // cleanup below marks the hook unmounted, so restore the live state
    // before accepting this scope's session response.
    mountedRef.current = true
    abortRef.current?.abort()
    setThreadId(null)
    setSessionId(null)
    setMessages([])
    setCurrentState({})
    setSessionError(null)
    setSteps([])
    setBusy(false)
    setStatus(locationId ? 'Opening the schedule workspace…' : '')
    if (!locationId) {
      setStatus('Choose a location to start the schedule assistant.')
      setSessions([])
      return () => { cancelled = true }
    }

    void getScheduleHuumeSession(locationId, weekStart, resumeSessionId)
      .then((session) => {
        if (cancelled || !mountedRef.current) return
        setThreadId(session.thread_id)
        setSessionId(session.session_id)
        setMessages(session.messages)
        setCurrentState(session.current_state || {})
        setStatus('')
        refreshSessions()
      })
      .catch((error: unknown) => {
        if (cancelled || !mountedRef.current) return
        setStatus('')
        setSessionError(error instanceof Error ? error.message : 'Could not open the schedule assistant.')
      })
    return () => { cancelled = true }
  }, [locationId, weekStart, sessionAttempt, resumeSessionId, refreshSessions])

  const settledAutomaticKey = settledAutomaticActionKey(currentState)
  useEffect(() => {
    if (!settledAutomaticKey || settledAutomaticKeysRef.current.has(settledAutomaticKey)) return
    settledAutomaticKeysRef.current.add(settledAutomaticKey)
    onSettledRef.current()
  }, [settledAutomaticKey])

  const openChat = useCallback((nextSessionId: string | null) => {
    if (busy) return
    setHistoryOpen(false)
    setResumeSessionId(nextSessionId)
    setSessionAttempt((attempt) => attempt + 1)
  }, [busy])

  const archiveChat = useCallback(async (summary: ScheduleHuumeSessionSummary) => {
    try {
      await archiveScheduleHuumeSession(summary.session_id)
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : 'Could not remove that chat.', 'error')
      return
    }
    if (!mountedRef.current) return
    setSessions((current) => current.filter((item) => item.session_id !== summary.session_id))
    // Archiving the chat that is open leaves nothing to talk in — start a new
    // one rather than keeping a thread the server will now refuse turns on.
    if (summary.session_id === sessionId) openChat(null)
  }, [openChat, sessionId, toast])

  const send = useCallback(async (contentOverride?: string) => {
    const displayContent = (contentOverride ?? input).trim()
    if (!displayContent || !threadId || busy || sessionError) return
    const content = displayContent + selectedShiftContext(selectedShiftsRef.current)
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
        // The first turn is what names this chat in history.
        refreshSessions()
        const key = appliedActionKey(response)
        if (key && !appliedKeysRef.current.has(key)) {
          appliedKeysRef.current.add(key)
          onAppliedRef.current()
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
  }, [busy, input, refreshSessions, sessionError, threadId, toast])

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

  const { action, choice } = getHuumeState(currentState)
  const recording = dictation.status === 'recording'
  const composerDisabled = !threadId || !!sessionError || busy || startingVoice || transcribing || recording

  return {
    threadId, sessionId, sessions, historyOpen, setHistoryOpen, refreshSessions,
    messages, currentState, setCurrentState, action, choice,
    input, setInput, status, sessionError,
    retry: () => setSessionAttempt((attempt) => attempt + 1),
    steps, busy, composerDisabled, send, openChat, archiveChat,
    voice: {
      enabled: voiceEnabled, starting: startingVoice, transcribing, recording, error: voiceError,
      begin: beginVoiceTurn, finish: finishVoiceTurn,
    },
  }
}
