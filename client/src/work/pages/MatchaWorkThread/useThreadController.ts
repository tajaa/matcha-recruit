import { useEffect, useRef, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import type { MWMessage, MWModeKey, MWThreadDetail, MWSendResponse, MWStreamEvent, HuumeStep } from '../../types'
import { getThread, sendMessageStream, uploadResumes, uploadInventory, updateTitle, getPdfProxyUrl, setThreadMode, fetchUsageSummary, fetchUsageSummary24h, notifyThreadsChanged, notifyUsageChanged } from '../../api/matchaWork'
import type { UsageSummary } from '../../api/matchaWork'
import { fetchLocations } from '../../../api/compliance'
import type { BusinessLocation } from '../../../types/compliance'
import { useMe } from '../../../hooks/useMe'
import { useWorkBase } from '../../routes/WorkSurfaceContext'
import { RESUME_EXTENSIONS, RESUME_MAX_SIZE, INVENTORY_EXTENSIONS } from './constants'
import { useThreadCollaboration } from './useThreadCollaboration'
import { useOptimisticMessages, makeTempId } from '../../hooks/useOptimisticMessages'
import { useToast } from '../../../components/ui'
import { detectMentionToken } from '../../utils/mentions'

// @-mention source list for the composer. v1 has exactly one entry (Huume);
// a second agent later is a new row here + a branch in applyHuumeMention's
// caller, not a new subsystem.
export interface MentionMatch {
  key: 'huume'
  label: string
  description: string
}

export function useThreadController() {
  const { me, hasFeature } = useMe()
  const { toast } = useToast()
  const isIndividual = me?.user?.role === 'individual'
  const { threadId } = useParams<{ threadId: string }>()
  const base = useWorkBase()
  const [thread, setThread] = useState<MWThreadDetail | null>(null)
  const [messages, setMessages] = useState<MWMessage[]>([])
  const { appendOptimistic, reconcileById } = useOptimisticMessages(setMessages)
  const [input, setInput] = useState('')
  // @-mention dropdown state (matches ChannelView/useChannelView's shape).
  // mentionCursor is the index right after '@' — where the query text starts.
  const [mentionQuery, setMentionQuery] = useState<string | null>(null)
  const [mentionCursor, setMentionCursor] = useState(0)
  const [streaming, setStreaming] = useState(false)
  const [loading, setLoading] = useState(true)
  const [lightMode, setLightMode] = useState(() => localStorage.getItem('mw-chat-theme') === 'light')
  const [error, setError] = useState('')
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)

  // Agent mode (local toggle, no backend persistence)
  const [agentMode, setAgentMode] = useState(false)

  // Language tutor panel (shown before thread gets task_type, dismissable)
  const [showTutorSetup, setShowTutorSetup] = useState(false)
  const [tutorDismissed, setTutorDismissed] = useState(false)

  // Mobile panel toggle
  const [mobileView, setMobileView] = useState<'chat' | 'panel'>('chat')

  // Model selector
  const [selectedModel, setSelectedModel] = useState(() => localStorage.getItem('mw-model') || 'gemini-3.6-flash')

  // Token usage
  const [usageTotal, setUsageTotal] = useState<UsageSummary | null>(null)
  const [usage24h, setUsage24h] = useState<UsageSummary | null>(null)

  // Resume drag-and-drop
  const [isDragOver, setIsDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Refetch current_state/version only — merge, don't replace: keeps local
  // title edits and never touches `messages` (a WS push already appended the
  // new message; replacing messages here could drop an in-flight optimistic
  // one). Used when a pushed message signals current_state changed
  // server-side without a normal send/complete cycle (offer accept/decline).
  const refreshThreadState = useCallback(() => {
    if (!threadId) return
    getThread(threadId)
      .then(t => setThread(prev => prev ? { ...prev, current_state: t.current_state, version: t.version } : t))
      .catch(() => {})
  }, [threadId])

  // Real-time collaboration
  const { onlineUsers, typingUsers, threadSocketRef, lastTypingSentRef } =
    useThreadCollaboration(threadId, setMessages, refreshThreadState)

  // Mode toggles — derived from thread, only toggling state is local
  const [togglingMode, setTogglingMode] = useState<MWModeKey | null>(null)
  const modeValue = (key: MWModeKey) => thread?.[`${key}_mode`] ?? false
  const complianceMode = modeValue('compliance')

  // Compliance locations — loaded when compliance mode is on
  const [locations, setLocations] = useState<BusinessLocation[]>([])
  const [locationsLoaded, setLocationsLoaded] = useState(false)
  const [locationsUnavailable, setLocationsUnavailable] = useState(false)
  // GET /compliance/locations needs any of these — matches the backend
  // lite_router gate (same tuple as ClientSidebar's compliance-calendar gate).
  const hasComplianceLocationAccess =
    hasFeature('compliance') || hasFeature('compliance_lite') || hasFeature('incidents')

  const refreshUsage = useCallback(() => {
    Promise.all([fetchUsageSummary(30), fetchUsageSummary24h()])
      .then(([total, daily]) => { setUsageTotal(total); setUsage24h(daily) })
      .catch(() => {})
  }, [])
  useEffect(refreshUsage, [refreshUsage])

  useEffect(() => {
    if (!complianceMode || locationsLoaded) return
    if (!hasComplianceLocationAccess) {
      // Company lost/never had compliance access — don't attempt the fetch (403),
      // just show the unavailable hint below the toggle.
      setLocationsUnavailable(true)
      setLocationsLoaded(true)
      return
    }
    fetchLocations()
      .then((locs) => { setLocations(locs); setLocationsLoaded(true) })
      .catch((e) => {
        console.warn('Failed to load compliance locations', e)
        setLocationsUnavailable(true)
        setLocationsLoaded(true)
      })
  }, [complianceMode, locationsLoaded, hasComplianceLocationAccess])

  // Stream status
  const [statusMessage, setStatusMessage] = useState('')
  // Huume 'step' frames, accumulated live during a turn so the tool-call
  // timeline renders in the pending bubble while streaming — previously
  // parsed and dropped, only appearing post-hoc from the persisted
  // assistant message's metadata once the turn had already completed.
  const [pendingHuumeSteps, setPendingHuumeSteps] = useState<HuumeStep[]>([])

  // Title editing
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  // Pending "did the backend auto-title this yet?" pickup timers — the title
  // lands via a fire-and-forget background task on the server, not the SSE
  // response, so we poll a couple of times rather than block the turn on it.
  const autotitleTimersRef = useRef<ReturnType<typeof setTimeout>[]>([])

  function clearAutotitleTimers() {
    autotitleTimersRef.current.forEach(clearTimeout)
    autotitleTimersRef.current = []
  }

  useEffect(() => {
    if (!threadId) return
    setLoading(true)
    setError('')
    // Switching threads mid-stream: the abort below fires no onComplete/onError
    // (user-initiated), so nothing else resets `streaming` — without this the
    // new thread mounts with a disabled composer and a permanent "Thinking…".
    setStreaming(false)
    getThread(threadId)
      .then((data) => {
        setThread(data)
        setMessages(data.messages)
        // Check if there's already a PDF-worthy task type (presentations use the panel instead)
        if (data.task_type === 'offer_letter') {
          setPdfUrl(getPdfProxyUrl(threadId, data.version))
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load thread'))
      .finally(() => setLoading(false))

    return () => {
      abortRef.current?.abort('thread-switch')
      clearAutotitleTimers()
    }
  }, [threadId])

  const prevLenRef = useRef(0)
  useEffect(() => {
    if (messages.length > prevLenRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
    prevLenRef.current = messages.length
  }, [messages.length])

  function handleSend(overrideContent?: string, slideIndex?: number) {
    const content = (overrideContent ?? input).trim()
    if (!threadId || !content || streaming || togglingMode) return

    setInput('')
    setMentionQuery(null)
    setStreaming(true)
    setError('')

    // Optimistically add user message
    const tempUserMsg: MWMessage = {
      id: makeTempId(),
      thread_id: threadId,
      role: 'user',
      content,
      metadata: null,
      version_created: null,
      created_at: new Date().toISOString(),
    }
    appendOptimistic(tempUserMsg)

    const streamOpts: Record<string, unknown> = {}
    if (slideIndex != null) streamOpts.slide_index = slideIndex
    if (selectedModel) streamOpts.model = selectedModel

    setPendingHuumeSteps([])
    abortRef.current = sendMessageStream(threadId, content, {
      onEvent: (event: MWStreamEvent) => {
        if (event.type === 'status') setStatusMessage(event.message)
        if (event.type === 'step') setPendingHuumeSteps((prev) => [...prev, event.data])
      },
      onComplete: (data: MWSendResponse) => {
        setStatusMessage('')
        setPendingHuumeSteps([])
        // Replace temp user message + add assistant message
        reconcileById(tempUserMsg.id, data.user_message, data.assistant_message)
        // Update thread state
        setThread((prev) =>
          prev
            ? {
                ...prev,
                current_state: data.current_state,
                version: data.version,
                task_type: data.task_type ?? prev.task_type,
              }
            : prev
        )
        // Show PDF if returned (for offer letters — presentations use the panel)
        if (data.task_type === 'presentation') {
          setPdfUrl(null) // presentation panel handles display
        } else if (data.pdf_url) {
          setPdfUrl(data.pdf_url)
        } else if (data.task_type === 'offer_letter') {
          setPdfUrl(getPdfProxyUrl(threadId, data.version))
        }
        setStreaming(false)
        refreshUsage()
        notifyUsageChanged()

        if (thread?.title.startsWith('New Chat')) {
          const pickUpTitle = () => {
            getThread(threadId)
              .then((t) => {
                if (!t.title.startsWith('New Chat')) {
                  setThread((prev) => (prev ? { ...prev, title: t.title } : prev))
                  notifyThreadsChanged()
                }
              })
              .catch(() => {})
          }
          // The title write is a detached background task with no WS push
          // and nothing on the `complete` frame — polling is the only pickup
          // path. Staggered with backoff so a title that lands slower than
          // the old fixed 4s cutoff (a slow Gemini call) still surfaces
          // without the user having to re-navigate into the thread.
          for (const delay of [2500, 4000, 7000, 12000, 20000]) {
            autotitleTimersRef.current.push(setTimeout(pickUpTitle, delay))
          }
        }
      },
      onError: (err) => {
        setStatusMessage('')
        setPendingHuumeSteps([])
        setError(err)
        setStreaming(false)
        // A 429/402 quota refusal is exactly when the meter should snap to
        // red without waiting for the next poll.
        notifyUsageChanged()
      },
    }, streamOpts)
  }

  function handleResumeUpload(files: File | File[]) {
    if (!threadId || streaming) return
    const fileList = Array.isArray(files) ? files : [files]

    for (const file of fileList) {
      const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
      if (!RESUME_EXTENSIONS.includes(ext)) {
        setError(`Unsupported file type: ${file.name}. Please upload PDF, DOCX, or TXT files.`)
        return
      }
      if (file.size > RESUME_MAX_SIZE) {
        setError(`File exceeds 10 MB limit: ${file.name}`)
        return
      }
    }

    setStreaming(true)
    setError('')

    const tempMsg: MWMessage = {
      id: makeTempId(),
      thread_id: threadId,
      role: 'user',
      content: `[Resume batch: ${fileList.length} files]`,
      metadata: null,
      version_created: null,
      created_at: new Date().toISOString(),
    }
    appendOptimistic(tempMsg)

    abortRef.current = uploadResumes(threadId, fileList, {
      onEvent: (event: MWStreamEvent) => {
        if (event.type === 'status') setStatusMessage(event.message)
      },
      onComplete: (data: MWSendResponse) => {
        setStatusMessage('')
        reconcileById(tempMsg.id, data.user_message, data.assistant_message)
        setThread((prev) =>
          prev
            ? { ...prev, current_state: data.current_state, version: data.version, task_type: data.task_type ?? prev.task_type }
            : prev
        )
        setPdfUrl(null)
        setStreaming(false)
      },
      onError: (err) => {
        setStatusMessage('')
        setError(err)
        setStreaming(false)
      },
    })
  }

  function handleInventoryUpload(files: File[]) {
    if (!threadId || streaming) return

    for (const file of files) {
      const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
      if (![...RESUME_EXTENSIONS, ...INVENTORY_EXTENSIONS].includes(ext)) {
        setError(`Unsupported file type: ${file.name}`)
        return
      }
      if (file.size > 15 * 1024 * 1024) {
        setError(`File exceeds 15 MB limit: ${file.name}`)
        return
      }
    }

    setStreaming(true)
    setError('')

    const tempMsg: MWMessage = {
      id: makeTempId(),
      thread_id: threadId,
      role: 'user',
      content: `[Inventory batch: ${files.length} file${files.length !== 1 ? 's' : ''}]`,
      metadata: null,
      version_created: null,
      created_at: new Date().toISOString(),
    }
    appendOptimistic(tempMsg)

    abortRef.current = uploadInventory(threadId, files, {
      onEvent: (event: MWStreamEvent) => {
        if (event.type === 'status') setStatusMessage(event.message)
      },
      onComplete: (data: MWSendResponse) => {
        setStatusMessage('')
        reconcileById(tempMsg.id, data.user_message, data.assistant_message)
        setThread((prev) =>
          prev
            ? { ...prev, current_state: data.current_state, version: data.version, task_type: data.task_type ?? prev.task_type }
            : prev
        )
        setPdfUrl(null)
        setStreaming(false)
      },
      onError: (err) => {
        setStatusMessage('')
        setError(err)
        setStreaming(false)
      },
    })
  }

  function handleFileUpload(files: File | File[]) {
    const fileList = Array.isArray(files) ? files : [files]
    const isInventoryThread = thread?.task_type === 'inventory'
    const hasSpreadsheets = fileList.some((f) => INVENTORY_EXTENSIONS.some((ext) => f.name.toLowerCase().endsWith(ext)))

    if (isInventoryThread || hasSpreadsheets) {
      handleInventoryUpload(fileList)
    } else {
      handleResumeUpload(fileList)
    }
  }

  // Autocomplete candidates for the active @-token. Empty when no token is
  // open, or the company doesn't have huume — @ offers nothing in that case.
  const mentionMatches: MentionMatch[] = (() => {
    if (mentionQuery === null || !hasFeature('huume')) return []
    if (mentionQuery.length === 0) return []
    if (!'huume'.startsWith(mentionQuery.toLowerCase())) return []
    return [{
      key: 'huume', label: 'Huume',
      description: 'Agentic assistant — offers, onboarding plans, HR-ops actions',
    }]
  })()

  // Removes the "@huume" token at [atIndex, tokenEnd) from `value` and turns
  // Huume mode on. `@huume` is a UI gesture only — it never reaches the
  // model as text (per "strip it", the token was chosen over keeping it as
  // a rendered chip so the sent message reads as plain prose). Guarded on
  // the current value because handleModeToggle *flips* — calling it when
  // huume_mode is already true would silently turn Huume back off.
  function stripMentionAndActivateHuume(value: string, atIndex: number, tokenEnd: number) {
    const head = value.slice(0, atIndex)
    const tail = value.slice(tokenEnd)
    setInput(head + tail)
    setMentionQuery(null)
    if (!modeValue('huume')) {
      handleModeToggle('huume')
    }
    requestAnimationFrame(() => {
      const ta = textareaRef.current
      if (!ta) return
      ta.focus()
      ta.setSelectionRange(head.length, head.length)
    })
  }

  // Dropdown-driven pick (click, Enter, Tab) — uses the tracked
  // mentionCursor/mentionQuery rather than re-deriving from the live
  // textarea value.
  function applyHuumeMention() {
    if (mentionQuery === null) return
    stripMentionAndActivateHuume(input, mentionCursor - 1, mentionCursor + mentionQuery.length)
  }

  function handleInputChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const value = e.target.value
    const caret = e.target.selectionStart ?? value.length

    if (hasFeature('huume')) {
      // Typed-through completion, case 1: caret sits right after a
      // just-finished "@huume" with no trailing space yet — consume
      // immediately rather than waiting for Enter/Tab, so typing the word
      // out behaves the same as picking it from the dropdown.
      const active = detectMentionToken(value, caret)
      if (active && active.query.toLowerCase() === 'huume') {
        stripMentionAndActivateHuume(value, active.tokenStart - 1, caret)
        return
      }
      // Case 2: a space was just typed after "@huume" — detectMentionToken
      // no longer sees an active token (it stops at whitespace), so check
      // the tail of the string directly for a token immediately before the
      // caret, bounded by start-of-string or whitespace before the '@'.
      const before = value.slice(0, caret)
      if (before.slice(-7).toLowerCase() === '@huume ') {
        const atIndex = before.length - 7
        const prevChar = atIndex === 0 ? '' : before[atIndex - 1]
        if (atIndex === 0 || /\s/.test(prevChar)) {
          stripMentionAndActivateHuume(value, atIndex, atIndex + 6)
          return
        }
      }
    }

    setInput(value)
    const token = detectMentionToken(value, caret)
    if (token && token.query.length <= 32 && /^[A-Za-z0-9._-]*$/.test(token.query)) {
      setMentionQuery(token.query)
      setMentionCursor(token.tokenStart)
    } else {
      setMentionQuery(null)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    // When the mention dropdown is open, Tab/Enter selects the match and
    // Escape closes it — same contract as ChannelView's composer.
    if (mentionQuery !== null && mentionMatches.length > 0) {
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault()
        applyHuumeMention()
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        setMentionQuery(null)
        return
      }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  async function handleTitleSave() {
    if (!threadId || !titleDraft.trim()) return
    try {
      const updated = await updateTitle(threadId, titleDraft.trim())
      setThread((prev) => (prev ? { ...prev, title: updated.title } : prev))
      setEditingTitle(false)
      notifyThreadsChanged()
    } catch {}
  }

  async function handleModeToggle(mode: MWModeKey) {
    if (!threadId || togglingMode) return
    const current = modeValue(mode)
    setTogglingMode(mode)
    try {
      await setThreadMode(threadId, mode, !current)
      setThread((prev) => prev ? { ...prev, [`${mode}_mode`]: !current } : prev)
    } catch (e) {
      // A silently-failed toggle leaves the user believing the mode is on
      // while the backend answers without it.
      console.error(`Failed to toggle ${mode} mode`, e)
      toast(`Couldn't toggle ${mode} mode`, 'error')
    }
    setTogglingMode(null)
  }

  const handleSendRef = useRef(handleSend)
  handleSendRef.current = handleSend

  const handleEditSlide = useCallback(
    (slideIndex: number, instruction: string) => {
      handleSendRef.current(instruction, slideIndex)
    },
    []
  )

  function toggleLightMode() {
    setLightMode((prev) => {
      const next = !prev
      localStorage.setItem('mw-chat-theme', next ? 'light' : 'dark')
      return next
    })
  }

  return {
    me, hasFeature, isIndividual, threadId, base,
    thread, setThread,
    messages, setMessages,
    input, setInput,
    mentionQuery, mentionMatches, applyHuumeMention, handleInputChange,
    streaming,
    loading,
    lightMode,
    error, setError,
    pdfUrl,
    agentMode, setAgentMode,
    showTutorSetup, setShowTutorSetup,
    tutorDismissed, setTutorDismissed,
    mobileView, setMobileView,
    selectedModel, setSelectedModel,
    usageTotal, usage24h,
    isDragOver, setIsDragOver,
    fileInputRef,
    onlineUsers, typingUsers, threadSocketRef, lastTypingSentRef,
    togglingMode, modeValue, complianceMode,
    locations, locationsUnavailable,
    statusMessage, pendingHuumeSteps,
    editingTitle, setEditingTitle,
    titleDraft, setTitleDraft,
    messagesEndRef, textareaRef,
    refreshUsage, refreshThreadState,
    handleSend, handleFileUpload, handleKeyDown, handleTitleSave, handleModeToggle, handleEditSlide,
    toggleLightMode,
  }
}

export type ThreadController = ReturnType<typeof useThreadController>
