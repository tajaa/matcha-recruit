import { useEffect, useRef, useState, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Send, Loader2, Pencil, Check, X, Database, Shield, Stethoscope, MapPin, Sun, Moon } from 'lucide-react'
import type { MWMessage, MWThreadDetail, MWSendResponse, MWStreamEvent } from '../../types/matcha-work'
import { getThread, sendMessageStream, updateTitle, getPdfProxyUrl, setNodeMode, setComplianceMode, setPayerMode } from '../../api/matchaWork'
import { fetchLocations } from '../../api/compliance'
import type { BusinessLocation } from '../../types/compliance'
import MessageBubble from '../../components/matcha-work/MessageBubble'
import PresentationPanel from '../../components/matcha-work/PresentationPanel'

const TASK_LABELS: Record<string, string> = {
  chat: 'Chat',
  offer_letter: 'Offer Letter',
  review: 'Review',
  workbook: 'Workbook',
  onboarding: 'Onboarding',
  presentation: 'Presentation',
  handbook: 'Handbook',
  policy: 'Policy',
}

export default function MatchaWorkThread() {
  const { threadId } = useParams<{ threadId: string }>()
  const [thread, setThread] = useState<MWThreadDetail | null>(null)
  const [messages, setMessages] = useState<MWMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [loading, setLoading] = useState(true)
  const [lightMode, setLightMode] = useState(() => localStorage.getItem('mw-chat-theme') === 'light')
  const [error, setError] = useState('')
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)

  // Mode toggles — derived from thread, only toggling state is local
  const [togglingMode, setTogglingMode] = useState<'node' | 'compliance' | 'payer' | null>(null)
  const nodeMode = thread?.node_mode ?? false
  const complianceMode = thread?.compliance_mode ?? false
  const payerMode = thread?.payer_mode ?? false

  // Compliance locations — loaded when compliance mode is on
  const [locations, setLocations] = useState<BusinessLocation[]>([])
  const [locationsLoaded, setLocationsLoaded] = useState(false)

  useEffect(() => {
    if (complianceMode && !locationsLoaded) {
      fetchLocations()
        .then((locs) => { setLocations(locs); setLocationsLoaded(true) })
        .catch(() => setLocationsLoaded(true))
    }
  }, [complianceMode, locationsLoaded])

  // Stream status
  const [statusMessage, setStatusMessage] = useState('')

  // Title editing
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (!threadId) return
    setLoading(true)
    setError('')
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

    return () => { abortRef.current?.abort() }
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
    if (!threadId || !content || streaming) return

    setInput('')
    setStreaming(true)
    setError('')

    // Optimistically add user message
    const tempUserMsg: MWMessage = {
      id: crypto.randomUUID(),
      thread_id: threadId,
      role: 'user',
      content,
      metadata: null,
      version_created: null,
      created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, tempUserMsg])

    const streamOpts = slideIndex != null ? { slide_index: slideIndex } : undefined

    abortRef.current = sendMessageStream(threadId, content, {
      onEvent: (event: MWStreamEvent) => {
        if (event.type === 'status') setStatusMessage(event.message)
      },
      onComplete: (data: MWSendResponse) => {
        setStatusMessage('')
        // Replace temp user message + add assistant message
        setMessages((prev) => {
          const withoutTemp = prev.filter((m) => m.id !== tempUserMsg.id)
          return [...withoutTemp, data.user_message, data.assistant_message]
        })
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
      },
      onError: (err) => {
        setStatusMessage('')
        setError(err)
        setStreaming(false)
      },
    }, streamOpts)
  }

  function handleKeyDown(e: React.KeyboardEvent) {
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
    } catch {}
  }

  async function handleModeToggle(mode: 'node' | 'compliance' | 'payer') {
    if (!threadId || togglingMode) return
    const apiFn = { node: setNodeMode, compliance: setComplianceMode, payer: setPayerMode }[mode]
    const current = { node: nodeMode, compliance: complianceMode, payer: payerMode }[mode]
    setTogglingMode(mode)
    try {
      await apiFn(threadId, !current)
      setThread((prev) => prev ? { ...prev, [`${mode}_mode`]: !current } : prev)
    } catch {}
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

  const isPresentation = thread?.task_type === 'presentation'
  const showPresentationPanel = isPresentation && thread?.current_state
  const isFinalized = thread?.status === 'finalized'
  const isArchived = thread?.status === 'archived'
  const inputDisabled = streaming || isFinalized || isArchived

  function toggleLightMode() {
    setLightMode((prev) => {
      const next = !prev
      localStorage.setItem('mw-chat-theme', next ? 'light' : 'dark')
      return next
    })
  }

  const lm = lightMode
  const th = {
    border:      lm ? 'border-zinc-200'  : 'border-zinc-800',
    panelBg:     lm ? 'bg-white'         : '',
    backArrow:   lm ? 'text-zinc-500 hover:text-zinc-900' : 'text-zinc-400 hover:text-white',
    titleInput:  lm ? 'bg-zinc-100 text-zinc-900 border border-zinc-300' : 'bg-zinc-800 text-white border border-zinc-600',
    titleText:   lm ? 'text-zinc-900'    : 'text-white',
    editBtn:     lm ? 'text-zinc-400 hover:text-zinc-900' : 'text-zinc-500 hover:text-white',
    badge:       lm ? 'bg-zinc-100 text-zinc-600' : 'bg-zinc-700 text-zinc-300',
    modeOff:     lm ? 'bg-zinc-100 text-zinc-500 hover:bg-zinc-200 hover:text-zinc-700' : 'bg-zinc-700 text-zinc-400 hover:bg-zinc-600 hover:text-zinc-200',
    jurisdBar:   lm ? 'bg-zinc-50/50'   : 'bg-zinc-900/50',
    jurisdLabel: lm ? 'text-zinc-400'   : 'text-zinc-500',
    emptyText:   lm ? 'text-zinc-400'   : 'text-zinc-500',
    streamBg:    lm ? 'bg-zinc-100/80 border border-zinc-200' : 'bg-zinc-800/60 border border-zinc-700/50',
    streamText:  lm ? 'text-zinc-500'   : 'text-zinc-400',
    textarea:    lm
      ? 'bg-zinc-100 text-zinc-900 border-zinc-300 focus:border-emerald-600 placeholder-zinc-400'
      : 'bg-zinc-800 text-white border-zinc-700 focus:border-emerald-600 placeholder-zinc-500',
    finText:     lm ? 'text-zinc-500'   : 'text-zinc-500',
  }

  if (loading) {
    return (
      <div className="flex justify-center items-center h-[calc(100vh-49px)]">
        <Loader2 className="animate-spin text-zinc-500" size={24} />
      </div>
    )
  }

  if (error && !thread) {
    return (
      <div className="flex flex-col items-center justify-center h-[calc(100vh-49px)] gap-4">
        <p className="text-red-400">{error}</p>
        <Link to="/work" className="text-sm text-zinc-400 hover:text-white">
          Back to threads
        </Link>
      </div>
    )
  }

  return (
    <div className="flex flex-col md:flex-row h-[calc(100vh-49px)]">
      {/* Chat panel */}
      <div className={`flex flex-col ${pdfUrl || showPresentationPanel ? 'w-full md:w-1/2' : 'w-full'} border-r ${th.border} ${th.panelBg}`}>
        {/* Header */}
        <div className={`flex items-center gap-3 px-4 py-3 border-b ${th.border}`}>
          <Link to="/work" className={`${th.backArrow} transition-colors`}>
            <ArrowLeft size={18} />
          </Link>

          {editingTitle ? (
            <div className="flex items-center gap-2 flex-1">
              <input
                value={titleDraft}
                onChange={(e) => setTitleDraft(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleTitleSave()}
                className={`${th.titleInput} text-sm px-2 py-2 rounded flex-1`}
                autoFocus
              />
              <button onClick={handleTitleSave} className="text-emerald-400 hover:text-emerald-300">
                <Check size={16} />
              </button>
              <button onClick={() => setEditingTitle(false)} className="text-zinc-400 hover:text-white">
                <X size={16} />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <h2 className={`${th.titleText} font-medium truncate`}>{thread?.title}</h2>
              <button
                onClick={() => {
                  setTitleDraft(thread?.title ?? '')
                  setEditingTitle(true)
                }}
                className={`${th.editBtn} transition-colors shrink-0`}
              >
                <Pencil size={14} />
              </button>
            </div>
          )}

          {thread?.task_type && (
            <span className={`shrink-0 px-2 py-0.5 text-xs font-medium rounded-full ${th.badge}`}>
              {TASK_LABELS[thread.task_type] ?? thread.task_type}
            </span>
          )}

          <button
            onClick={() => handleModeToggle('node')}
            disabled={togglingMode === 'node'}
            title={nodeMode ? 'Node ON — Try: "Our CA clinical staff vs NY clinical staff — which group is missing meal break policy coverage?" or "Do any of our CO employees fall under departments with no active handbook?"' : 'Node OFF — click to query your employees, policies, and handbooks'}
            className={`hidden sm:inline-flex shrink-0 items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full transition-colors disabled:opacity-50 ${
              nodeMode
                ? 'bg-purple-600 text-white hover:bg-purple-500'
                : th.modeOff
            }`}
          >
            <Database size={12} />
            Node
          </button>

          <button
            onClick={() => handleModeToggle('compliance')}
            disabled={togglingMode === 'compliance'}
            title={complianceMode ? 'Compliance ON — Try: "CA allows healthcare meal break waivers for shifts over 12 hours — does this override the standard 6-hour waiver threshold, and what\'s the penalty if we miss it?" or "Compare overtime rules for our NY vs IL employees"' : 'Compliance OFF — click to inject jurisdiction requirements into AI context'}
            className={`hidden sm:inline-flex shrink-0 items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full transition-colors disabled:opacity-50 ${
              complianceMode
                ? 'bg-cyan-600 text-white hover:bg-cyan-500'
                : th.modeOff
            }`}
          >
            <Shield size={12} />
            Compliance
          </button>

          <button
            onClick={() => handleModeToggle('payer')}
            disabled={togglingMode === 'payer'}
            title={payerMode ? 'Payer ON — Try: "Medicare NCD 30.3 covers acupuncture for chronic lower back pain but not fibromyalgia — what are the exact clinical criteria that distinguish covered vs non-covered?" or "Does NCD 260.1 liver transplant coverage require the patient to have end-stage liver disease, and what documentation is needed?"' : 'Payer OFF — click to search Medicare NCD/LCD coverage policies'}
            className={`hidden sm:inline-flex shrink-0 items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full transition-colors disabled:opacity-50 ${
              payerMode
                ? 'bg-emerald-600 text-white hover:bg-emerald-500'
                : th.modeOff
            }`}
          >
            <Stethoscope size={12} />
            Payer
          </button>

          <button
            onClick={toggleLightMode}
            title={lightMode ? 'Switch to dark mode' : 'Switch to light mode'}
            className={`shrink-0 p-1.5 rounded-full transition-colors ${th.backArrow}`}
          >
            {lightMode ? <Moon size={14} /> : <Sun size={14} />}
          </button>
        </div>

        {/* Jurisdiction bar — shows when compliance mode is on */}
        {complianceMode && locations.length > 0 && (
          <div className={`px-4 py-2 border-b ${th.border} ${th.jurisdBar} flex items-center gap-2 overflow-x-auto`}>
            <MapPin size={12} className="text-cyan-500 shrink-0" />
            <span className={`text-[10px] ${th.jurisdLabel} uppercase tracking-wider font-medium shrink-0`}>Your jurisdictions:</span>
            <div className="flex gap-1.5 flex-wrap">
              {locations.map((loc) => (
                <span
                  key={loc.id}
                  className="text-[11px] bg-cyan-950/40 text-cyan-300 border border-cyan-800/40 px-2 py-0.5 rounded whitespace-nowrap"
                >
                  {loc.city}, {loc.state}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {messages.length === 0 && (
            <div className={`flex items-center justify-center h-full ${th.emptyText} text-sm`}>
              Start a conversation — ask about offer letters, reviews, handbooks, and more.
            </div>
          )}
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} lightMode={lightMode} />
          ))}

          {streaming && (
            <div className="flex justify-start">
              <div className={`${th.streamBg} rounded-lg px-4 py-2.5 flex items-center gap-2`}>
                <Loader2 size={14} className={`animate-spin ${th.streamText}`} />
                <span className={`text-sm ${th.streamText}`}>{statusMessage || 'Thinking...'}</span>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Error */}
        {error && (
          <div className="mx-4 mb-2 p-2 bg-red-900/30 border border-red-800 rounded text-red-300 text-xs flex items-center justify-between">
            <span>{error}</span>
            <button onClick={() => setError('')} className="text-red-200 hover:text-white text-xs underline ml-2 shrink-0">
              Dismiss
            </button>
          </div>
        )}

        {/* Input */}
        <div className={`px-4 py-3 border-t ${th.border} pb-[env(safe-area-inset-bottom)]`}>
          {isFinalized ? (
            <div className="text-center text-sm text-zinc-500 py-2">
              This thread has been finalized.
            </div>
          ) : isArchived ? (
            <div className="text-center text-sm text-zinc-500 py-2">
              This thread has been archived.
            </div>
          ) : (
            <div className="flex items-end gap-2">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Type a message..."
                rows={1}
                disabled={inputDisabled}
                className={`flex-1 text-sm rounded-lg px-3 py-2.5 border focus:outline-none resize-none disabled:opacity-50 min-h-[44px] ${th.textarea}`}
              />
              <button
                onClick={() => handleSend()}
                disabled={inputDisabled || !input.trim()}
                className="p-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg transition-colors disabled:opacity-40 disabled:hover:bg-emerald-600"
              >
                {streaming ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Send size={16} />
                )}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Presentation panel */}
      {showPresentationPanel && (
        <PresentationPanel
          state={thread!.current_state}
          threadId={threadId!}
          onEditSlide={handleEditSlide}
          lightMode={lightMode}
          streaming={streaming}
        />
      )}

      {/* PDF preview panel (offer letters, etc.) */}
      {pdfUrl && !showPresentationPanel && (
        <div className="hidden md:block md:w-1/2 bg-zinc-900">
          <iframe
            src={pdfUrl}
            className="w-full h-full border-0"
            title="Document preview"
          />
        </div>
      )}
    </div>
  )
}
