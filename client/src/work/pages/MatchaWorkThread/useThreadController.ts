import { useEffect, useRef, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import type { MWMessage, MWModeKey, MWThreadDetail, MWSendResponse, MWStreamEvent } from '../../types'
import { getThread, sendMessageStream, uploadResumes, uploadInventory, updateTitle, getPdfProxyUrl, setThreadMode, fetchUsageSummary, fetchUsageSummary24h } from '../../api/matchaWork'
import type { UsageSummary } from '../../api/matchaWork'
import { fetchLocations } from '../../../api/compliance/compliance'
import type { BusinessLocation } from '../../../types/compliance'
import { useMe } from '../../../hooks/useMe'
import { useWorkBase } from '../../routes/WorkSurfaceContext'
import { RESUME_EXTENSIONS, RESUME_MAX_SIZE, INVENTORY_EXTENSIONS } from './constants'
import { useThreadCollaboration } from './useThreadCollaboration'

export function useThreadController() {
  const { me, hasFeature } = useMe()
  const isIndividual = me?.user?.role === 'individual'
  const { threadId } = useParams<{ threadId: string }>()
  const base = useWorkBase()
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

  // Language tutor panel (shown before thread gets task_type, dismissable)
  const [showTutorSetup, setShowTutorSetup] = useState(false)
  const [tutorDismissed, setTutorDismissed] = useState(false)

  // Mobile panel toggle
  const [mobileView, setMobileView] = useState<'chat' | 'panel'>('chat')

  // Model selector
  const [selectedModel, setSelectedModel] = useState(() => localStorage.getItem('mw-model') || 'gemini-3-flash-preview')

  // Token usage
  const [usageTotal, setUsageTotal] = useState<UsageSummary | null>(null)
  const [usage24h, setUsage24h] = useState<UsageSummary | null>(null)

  // Resume drag-and-drop
  const [isDragOver, setIsDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Real-time collaboration
  const { onlineUsers, typingUsers, threadSocketRef, lastTypingSentRef } = useThreadCollaboration(threadId, setMessages)

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

    return () => { abortRef.current?.abort('thread-switch') }
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
        refreshUsage()
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
    statusMessage,
    editingTitle, setEditingTitle,
    titleDraft, setTitleDraft,
    messagesEndRef, textareaRef,
    refreshUsage,
    handleSend, handleFileUpload, handleKeyDown, handleTitleSave, handleModeToggle, handleEditSlide,
    toggleLightMode,
  }
}

export type ThreadController = ReturnType<typeof useThreadController>
