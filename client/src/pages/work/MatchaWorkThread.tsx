import { useEffect, useRef, useState, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Send, Loader2, Pencil, Check, X, Database, Shield, Stethoscope, MapPin, Sun, Moon, Paperclip, Bot, FileText, Users, Presentation, Package, ClipboardList, Scale, BookOpen, FileCheck, MessageSquare, Briefcase } from 'lucide-react'
import type { MWMessage, MWThreadDetail, MWSendResponse, MWStreamEvent } from '../../types/matcha-work'
import { getThread, sendMessageStream, uploadResumes, uploadInventory, sendCandidateInterviews, syncInterviewStatuses, addProjectSection, updateTitle, getPdfProxyUrl, setNodeMode, setComplianceMode, setPayerMode } from '../../api/matchaWork'
import { fetchLocations } from '../../api/compliance'
import type { BusinessLocation } from '../../types/compliance'
import MessageBubble from '../../components/matcha-work/MessageBubble'
import { useMe } from '../../hooks/useMe'
import PresentationPanel from '../../components/matcha-work/PresentationPanel'
import ResumeBatchPanel from '../../components/matcha-work/ResumeBatchPanel'
import InventoryPanel from '../../components/matcha-work/InventoryPanel'
import ProjectPanel from '../../components/matcha-work/ProjectPanel'
import AgentPanel from '../../components/matcha-work/AgentPanel'

const RESUME_EXTENSIONS = ['.pdf', '.doc', '.docx', '.txt']
const RESUME_MAX_SIZE = 10 * 1024 * 1024
const INVENTORY_EXTENSIONS = ['.csv', '.xlsx', '.xls']
// INVENTORY_EXTENSIONS is used in handleFileUpload for routing detection

const MODEL_OPTIONS = [
  { id: 'gemini-3.1-flash-lite-preview', label: 'Flash Lite 3.1' },
  { id: 'gemini-3-flash-preview', label: 'Flash 3.0' },
  { id: 'gemini-3.1-pro-preview', label: 'Pro 3.1' },
] as const

// Skills available in the chat — requiresCompany gates visibility for individual users
const SKILLS = [
  { id: 'chat', icon: MessageSquare, label: 'HR Chat', desc: 'Ask any HR question', prompt: '', requiresCompany: false },
  { id: 'project', icon: FileText, label: 'Project', desc: 'Build reports & plans from chat', prompt: 'Create a new project called ', requiresCompany: false },
  { id: 'presentation', icon: Presentation, label: 'Presentation', desc: 'Generate slide decks', prompt: 'Create a presentation about ', requiresCompany: false },
  { id: 'resume_batch', icon: ClipboardList, label: 'Resume Batch', desc: 'Analyze candidate resumes', prompt: '', requiresCompany: false, dropHint: 'Drop resumes to start' },
  { id: 'inventory', icon: Package, label: 'Inventory', desc: 'Process invoices & track stock', prompt: '', requiresCompany: false, dropHint: 'Drop invoices to start' },
  { id: 'offer_letter', icon: FileCheck, label: 'Offer Letter', desc: 'Draft & send offer letters', prompt: 'Create an offer letter for ', requiresCompany: true },
  { id: 'handbook', icon: BookOpen, label: 'Handbook', desc: 'Generate employee handbooks', prompt: 'Create an employee handbook', requiresCompany: true },
  { id: 'policy', icon: Scale, label: 'Policy', desc: 'Draft compliance policies', prompt: 'Draft a policy for ', requiresCompany: true },
  { id: 'onboarding', icon: Users, label: 'Onboarding', desc: 'Create employee records', prompt: 'Onboard a new employee', requiresCompany: true },
  { id: 'review', icon: Briefcase, label: 'Review', desc: 'Run performance reviews', prompt: 'Create a performance review for ', requiresCompany: true },
] as const

const TASK_LABELS: Record<string, string> = {
  chat: 'Chat',
  offer_letter: 'Offer Letter',
  review: 'Review',
  workbook: 'Workbook',
  onboarding: 'Onboarding',
  presentation: 'Presentation',
  handbook: 'Handbook',
  policy: 'Policy',
  resume_batch: 'Resume Batch',
  inventory: 'Inventory',
  project: 'Project',
}

export default function MatchaWorkThread() {
  const { me } = useMe()
  const isIndividual = me?.user?.role === 'individual'
  const { threadId } = useParams<{ threadId: string }>()
  const [thread, setThread] = useState<MWThreadDetail | null>(null)
  const [messages, setMessages] = useState<MWMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [loading, setLoading] = useState(true)
  const [lightMode, setLightMode] = useState(() => localStorage.getItem('mw-chat-theme') === 'light')
  const [error, setError] = useState('')
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)

  // Agent mode (local toggle, no backend persistence)
  const [agentMode, setAgentMode] = useState(false)

  // Mobile panel toggle
  const [mobileView, setMobileView] = useState<'chat' | 'panel'>('chat')

  // Model selector
  const [selectedModel, setSelectedModel] = useState(() => localStorage.getItem('mw-model') || 'gemini-3-flash-preview')

  // Resume drag-and-drop
  const [isDragOver, setIsDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

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

    const streamOpts: Record<string, unknown> = {}
    if (slideIndex != null) streamOpts.slide_index = slideIndex
    if (selectedModel) streamOpts.model = selectedModel

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
      id: crypto.randomUUID(),
      thread_id: threadId,
      role: 'user',
      content: `[Resume batch: ${fileList.length} files]`,
      metadata: null,
      version_created: null,
      created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, tempMsg])

    abortRef.current = uploadResumes(threadId, fileList, {
      onEvent: (event: MWStreamEvent) => {
        if (event.type === 'status') setStatusMessage(event.message)
      },
      onComplete: (data: MWSendResponse) => {
        setStatusMessage('')
        setMessages((prev) => {
          const withoutTemp = prev.filter((m) => m.id !== tempMsg.id)
          return [...withoutTemp, data.user_message, data.assistant_message]
        })
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
      id: crypto.randomUUID(),
      thread_id: threadId,
      role: 'user',
      content: `[Inventory batch: ${files.length} file${files.length !== 1 ? 's' : ''}]`,
      metadata: null,
      version_created: null,
      created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, tempMsg])

    abortRef.current = uploadInventory(threadId, files, {
      onEvent: (event: MWStreamEvent) => {
        if (event.type === 'status') setStatusMessage(event.message)
      },
      onComplete: (data: MWSendResponse) => {
        setStatusMessage('')
        setMessages((prev) => {
          const withoutTemp = prev.filter((m) => m.id !== tempMsg.id)
          return [...withoutTemp, data.user_message, data.assistant_message]
        })
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
  const isResumeBatch = thread?.task_type === 'resume_batch'
  const showResumeBatchPanel = isResumeBatch && thread?.current_state
  const isInventory = thread?.task_type === 'inventory'
  const showInventoryPanel = isInventory && thread?.current_state
  const isProject = thread?.task_type === 'project'
  const showProjectPanel = isProject && thread?.current_state
  const hasRightPanel = !!(pdfUrl || showPresentationPanel || showResumeBatchPanel || showInventoryPanel || showProjectPanel || agentMode)
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

  // Project threads always use the dark editor theme; others respect lightMode
  const lm = isProject ? false : lightMode
  const th = isProject ? {
    border:      'border-[#333]',
    panelBg:     'bg-[#1e1e1e]',
    backArrow:   'text-[#6a737d] hover:text-[#e8e8e8]',
    titleInput:  'bg-[#252526] text-[#e8e8e8] border border-[#555]',
    titleText:   'text-[#e8e8e8]',
    editBtn:     'text-[#6a737d] hover:text-[#e8e8e8]',
    badge:       'bg-[#ce9178]/20 text-[#ce9178]',
    modeOff:     'bg-[#2a2d2e] text-[#6a737d] hover:bg-[#333] hover:text-[#d4d4d4]',
    jurisdBar:   'bg-[#252526]',
    jurisdLabel: 'text-[#6a737d]',
    emptyText:   'text-[#6a737d]',
    streamBg:    'bg-[#252526] border border-[#333]',
    streamText:  'text-[#6a737d]',
    textarea:    'bg-[#1a1a1a] text-[#d4d4d4] border-[#555] focus:border-[#ce9178] placeholder-[#6a737d]',
    finText:     'text-[#6a737d]',
  } : {
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
      <div className={`${mobileView === 'panel' && hasRightPanel ? 'hidden md:flex' : 'flex'} flex-col ${hasRightPanel ? 'w-full md:w-1/2' : 'w-full'} border-r ${th.border} ${th.panelBg}`}>
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

          {/* Mobile panel toggle */}
          {hasRightPanel && (
            <div className="flex md:hidden rounded overflow-hidden shrink-0" style={{ border: '1px solid' + (lightMode ? '#d4d4d8' : '#444') }}>
              <button
                onClick={() => setMobileView('chat')}
                className="px-2 py-1 text-[10px] font-medium"
                style={{ background: mobileView === 'chat' ? (lightMode ? '#22c55e' : '#ce9178') : (lightMode ? '#f4f4f5' : '#2a2d2e'), color: mobileView === 'chat' ? '#fff' : (lightMode ? '#71717a' : '#6a737d') }}
              >
                Chat
              </button>
              <button
                onClick={() => setMobileView('panel')}
                className="px-2 py-1 text-[10px] font-medium"
                style={{ background: mobileView === 'panel' ? (lightMode ? '#22c55e' : '#ce9178') : (lightMode ? '#f4f4f5' : '#2a2d2e'), color: mobileView === 'panel' ? '#fff' : (lightMode ? '#71717a' : '#6a737d') }}
              >
                Panel
              </button>
            </div>
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
            onClick={() => setAgentMode(!agentMode)}
            title={agentMode ? 'Agent ON — email inbox and AI drafting' : 'Agent OFF — click to open email agent'}
            className={`hidden sm:inline-flex shrink-0 items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full transition-colors ${
              agentMode
                ? 'text-white hover:bg-orange-500'
                : th.modeOff
            }`}
            style={agentMode ? { background: '#ce9178' } : {}}
          >
            <Bot size={12} />
            Agent
          </button>

          <select
            value={selectedModel}
            onChange={(e) => {
              setSelectedModel(e.target.value)
              localStorage.setItem('mw-model', e.target.value)
            }}
            className={`hidden sm:block shrink-0 text-[11px] font-medium rounded-full px-2.5 py-1 appearance-none cursor-pointer transition-colors ${th.modeOff} ${
              lightMode ? 'bg-zinc-100 text-zinc-600' : 'bg-zinc-700 text-zinc-300'
            }`}
          >
            {MODEL_OPTIONS.map((m) => (
              <option key={m.id} value={m.id}>{m.label}</option>
            ))}
          </select>

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

        {/* Messages — drop zone for resumes */}
        <div
          className="flex-1 overflow-y-auto px-4 py-4 space-y-4 relative"
          onDragOver={(e) => { e.preventDefault(); if (!streaming) setIsDragOver(true) }}
          onDragLeave={(e) => {
            // Only hide overlay when leaving the container (not entering a child)
            if (e.currentTarget.contains(e.relatedTarget as Node)) return
            setIsDragOver(false)
          }}
          onDrop={(e) => {
            e.preventDefault()
            setIsDragOver(false)
            const files = Array.from(e.dataTransfer.files)
            if (files.length > 0) handleFileUpload(files)
          }}
        >
          {isDragOver && (
            <div className="absolute inset-0 z-10 bg-emerald-600/10 border-2 border-dashed border-emerald-500 rounded-lg flex items-center justify-center pointer-events-none">
              <p className={`text-sm font-medium ${lightMode ? 'text-emerald-700' : 'text-emerald-400'}`}>
                Drop files here (resumes, invoices, spreadsheets)
              </p>
            </div>
          )}

          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full px-4">
              <p className={`text-sm font-medium mb-4 ${isProject ? 'text-[#e8e8e8]' : th.emptyText}`}>
                What would you like to work on?
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 max-w-md w-full">
                {SKILLS.filter((s) => !s.requiresCompany || !isIndividual).map((skill) => {
                  const Icon = skill.icon
                  return (
                    <button
                      key={skill.id}
                      onClick={() => {
                        if (skill.prompt) {
                          setInput(skill.prompt)
                          textareaRef.current?.focus()
                        }
                      }}
                      className={`flex flex-col items-center gap-1.5 rounded-lg px-3 py-3 text-center transition-colors ${
                        isProject
                          ? 'bg-[#252526] hover:bg-[#2a2d2e] text-[#d4d4d4]'
                          : lightMode
                            ? 'bg-zinc-100 hover:bg-zinc-200 text-zinc-600'
                            : 'bg-zinc-800/60 hover:bg-zinc-700/60 text-zinc-400'
                      }`}
                    >
                      <Icon size={16} className={isProject ? 'text-[#ce9178]' : 'text-emerald-500'} />
                      <span className="text-[11px] font-medium">{skill.label}</span>
                      <span className={`text-[9px] leading-tight ${isProject ? 'text-[#6a737d]' : lightMode ? 'text-zinc-400' : 'text-zinc-500'}`}>
                        {'dropHint' in skill ? skill.dropHint : skill.desc}
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>
          )}
          {messages.map((m) => (
            <MessageBubble
              key={m.id}
              message={m}
              lightMode={lightMode}
              isProjectThread={isProject}
              onAddToProject={isProject ? async (msgId, content) => {
                const result = await addProjectSection(threadId!, { content, source_message_id: msgId })
                setThread((prev) => prev ? { ...prev, current_state: result.current_state, version: result.version } : prev)
              } : undefined}
            />
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
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.doc,.docx,.txt,.csv,.xlsx,.xls"
                className="hidden"
                multiple
                onChange={(e) => {
                  const files = e.target.files ? Array.from(e.target.files) : []
                  if (files.length > 0) handleFileUpload(files)
                  e.target.value = ''
                }}
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={inputDisabled}
                title="Upload files (resumes, invoices, spreadsheets)"
                className={`p-3 rounded-lg transition-colors disabled:opacity-40 ${
                  lightMode ? 'text-zinc-400 hover:text-zinc-700 hover:bg-zinc-100' : 'text-zinc-400 hover:text-white hover:bg-zinc-800'
                }`}
              >
                <Paperclip size={16} />
              </button>
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
      {/* Right panels — visible on desktop always, on mobile via toggle */}
      <div className={`${mobileView === 'panel' ? 'flex w-full' : 'hidden'} md:contents`}>
        {showPresentationPanel && (
          <PresentationPanel
            state={thread!.current_state}
            threadId={threadId!}
            onEditSlide={handleEditSlide}
            lightMode={lightMode}
            streaming={streaming}
          />
        )}

        {showResumeBatchPanel && (
          <ResumeBatchPanel
            state={thread!.current_state}
            threadId={threadId!}
            lightMode={lightMode}
            streaming={streaming}
            onSendInterviews={async (ids, positionTitle) => {
              const result = await sendCandidateInterviews(threadId!, ids, positionTitle)
              if (result.sent.length > 0) {
                const refreshed = await getThread(threadId!)
                setThread(refreshed)
              }
              if (result.failed.length > 0) {
                setError(`Failed to send ${result.failed.length} interview(s): ${result.failed.map(f => f.error).join(', ')}`)
              }
            }}
            onSyncInterviews={async () => {
              const { updated } = await syncInterviewStatuses(threadId!)
              if (updated > 0) {
                const refreshed = await getThread(threadId!)
                setThread(refreshed)
              }
            }}
          />
        )}

        {showInventoryPanel && (
          <InventoryPanel
            state={thread!.current_state}
            threadId={threadId!}
            lightMode={lightMode}
            streaming={streaming}
          />
        )}

        {showProjectPanel && (
          <ProjectPanel
            state={thread!.current_state}
            threadId={threadId!}
            lightMode={lightMode}
            streaming={streaming}
            onStateUpdate={(newState, newVersion) => {
              setThread((prev) => prev ? { ...prev, current_state: newState, version: newVersion } : prev)
            }}
          />
        )}

        {agentMode && !showPresentationPanel && !showResumeBatchPanel && !showInventoryPanel && !showProjectPanel && (
          <AgentPanel />
        )}

        {pdfUrl && !showPresentationPanel && !showResumeBatchPanel && !showInventoryPanel && !showProjectPanel && !agentMode && (
          <div className={`${mobileView === 'panel' ? 'block w-full' : 'hidden md:block'} md:w-1/2 bg-zinc-900`}>
            <iframe
              src={pdfUrl}
              className="w-full h-full border-0"
              title="Document preview"
            />
          </div>
        )}
      </div>
    </div>
  )
}
