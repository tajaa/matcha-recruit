import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useMe } from '../../../hooks/useMe'
import type { MWMessage, MWThreadDetail, MWSendResponse, MWStreamEvent, MWProject } from '../../types'
import { getProjectDetail, getThread, sendMessageStream, createProjectChat, addProjectSectionNew, updateProjectSectionNew, uploadProjectResumes, syncProjectInterviews, extractPlaceholderValue, fetchUsageSummary, fetchUsageSummary24h, updateTitle, pinThread, getPdfProxyUrl } from '../../api/matchaWork'
import type { UsageSummary } from '../../api/matchaWork'
import { useProjectPresence } from '../../hooks/useProjectPresence'
import { useWorkBase } from '../../routes/WorkSurfaceContext'
import { useInbox } from './useInbox'
import { TOUR_DISMISSED_KEY } from './tour'

/**
 * All state, effects, and handlers for the project view. Presentational panes
 * (sidebar, chat, inbox, workspace panel) consume the returned view-model.
 */
export function useProjectView() {
  const { projectId } = useParams<{ projectId: string }>()
  const base = useWorkBase()
  const [project, setProject] = useState<MWProject | null>(null)
  const [activeChatId, setActiveChatId] = useState<string | null>(null)
  const [activeThread, setActiveThread] = useState<MWThreadDetail | null>(null)
  const [messages, setMessages] = useState<MWMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [statusMessage, setStatusMessage] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedModel, setSelectedModel] = useState(() => localStorage.getItem('mw-model') || 'gemini-3-flash-preview')
  const [usageTotal, setUsageTotal] = useState<UsageSummary | null>(null)
  const [usage24h, setUsage24h] = useState<UsageSummary | null>(null)

  // Placeholder fill-in tracking: when user clicks finalize with missing fields,
  // we track which placeholders need answers. Each user chat message fills the next one.
  const pendingPlaceholders = useRef<{ placeholder: string; label: string; question: string }[]>([])

  // Which surface of the workspace is showing. Mirrors desktop Werk's collab tab
  // strip (CollabRightPanel): one tab set driving one content pane, rendered as a
  // top strip on desktop and a bottom bar on mobile.
  const [activeTab, setActiveTab] = useState<'chat' | 'panel' | 'board' | 'files'>('chat')

  // Sidebar mode: 'chats' or 'inbox'
  const [sidebarMode, setSidebarMode] = useState<'chats' | 'inbox'>('chats')
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const inbox = useInbox(sidebarMode)
  const { me } = useMe()
  const currentUserId = me?.user?.id ?? ''

  // Real-time presence: which sub-tab is the user on inside this project?
  // The page_key drives cursor + caret fan-out on the server. Only Sections
  // gets cursors/carets (recruiting Pipeline + Chat are passive — collaborators
  // still appear in the header pill, but no cursor traffic flows).
  const [activePageKey, setActivePageKey] = useState<string>('sections')
  const presence = useProjectPresence(projectId ?? null, activePageKey)
  const cursorsActive = activePageKey === 'sections'

  // Onboarding tour: spotlight Sections / Chat / Collaborators / Export the
  // first time the user lands on a project, until they hit Skip / Done. Open
  // again from the "?" button on the project header.
  const [showTour, setShowTour] = useState(false)
  useEffect(() => {
    if (!project) return
    const dismissed = localStorage.getItem(TOUR_DISMISSED_KEY) === 'true'
    if (!dismissed) setShowTour(true)
  }, [project?.id])

  function dismissTour(_dismissed: boolean) {
    setShowTour(false)
    // Persist regardless of whether the user clicked Skip or finished — both
    // signal "I've seen this." Re-open via the "?" button if they want a
    // refresher.
    localStorage.setItem(TOUR_DISMISSED_KEY, 'true')
  }

  // Switch the page_key when the project type loads so the recruiting view
  // shows the "Pipeline" pill state and the project view shows "Sections".
  useEffect(() => {
    if (!project) return
    setActivePageKey(project.project_type === 'recruiting' ? 'pipeline' : 'sections')
  }, [project?.project_type])

  // Clamp the active tab to one the *current* project actually offers. This
  // component stays mounted across `projects/:projectId` changes, so without
  // this a user on Kanban who opens a recruiting workspace (no board tab) would
  // land on a pane that renders nothing at all.
  useEffect(() => {
    if (!project) return
    const type = project.project_type
    const allowed =
      type === 'recruiting'
        ? ['chat', 'panel']
        : type === 'presentation'
        ? ['chat', 'panel', 'board']
        : ['chat', 'board']
    setActiveTab((prev) => (allowed.includes(prev) ? prev : 'chat'))
  }, [projectId, project?.project_type])

  // Chat rename/pin
  const [renamingChatId, setRenamingChatId] = useState<string | null>(null)
  const [renameDraft, setRenameDraft] = useState('')
  const renameInputRef = useRef<HTMLInputElement>(null)

  async function handleRenameChat(chatId: string) {
    if (!renameDraft.trim()) { setRenamingChatId(null); return }
    try {
      await updateTitle(chatId, renameDraft.trim())
      setProject((prev) => prev ? {
        ...prev,
        chats: prev.chats?.map((c) => c.id === chatId ? { ...c, title: renameDraft.trim() } : c),
      } : prev)
    } catch {}
    setRenamingChatId(null)
  }

  async function handlePinChat(chatId: string, currentlyPinned: boolean) {
    try {
      await pinThread(chatId, !currentlyPinned)
      setProject((prev) => prev ? {
        ...prev,
        chats: prev.chats?.map((c) => c.id === chatId ? { ...c, is_pinned: !currentlyPinned } : c),
      } : prev)
    } catch {}
  }

  // Offer letter PDF panel (for recruiting projects)
  const [offerPdfUrl, setOfferPdfUrl] = useState<string | null>(null)

  // Recruiting wizard + drag-and-drop
  const [showWizard, setShowWizard] = useState(false)
  const [isDragOver, setIsDragOver] = useState(false)
  const [showCollaborators, setShowCollaborators] = useState(false)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const resumeFileRef = useRef<HTMLInputElement>(null)

  // Load project
  useEffect(() => {
    if (!projectId) return
    setLoading(true)
    getProjectDetail(projectId)
      .then(async (p) => {
        setProject(p)
        if (p.chats && p.chats.length > 0) {
          setActiveChatId(p.chats[0].id)
        }
        // Show wizard for new recruiting projects (no candidates yet)
        if (p.project_type === 'recruiting') {
          const data = p.project_data as Record<string, unknown>
          const candidates = (data?.candidates as unknown[]) || []
          if (candidates.length === 0 && !localStorage.getItem(`wizard-dismissed-${projectId}`)) {
            setShowWizard(true)
          }
          // Auto-sync interview statuses on load if any candidates have pending interviews
          const hasPendingInterview = (candidates as Record<string, unknown>[]).some(
            (c) => c.interview_id && c.status !== 'interview_completed'
          )
          if (hasPendingInterview) {
            try {
              await syncProjectInterviews(projectId)
              const refreshed = await getProjectDetail(projectId)
              setProject(refreshed)
            } catch {
              // ignore — user can still manually refresh
            }
          }
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load project'))
      .finally(() => setLoading(false))
    return () => { abortRef.current?.abort() }
  }, [projectId])

  // Periodic auto-sync for pending interviews while the page is open
  useEffect(() => {
    if (!projectId || !project || project.project_type !== 'recruiting') return
    const data = (project.project_data || {}) as Record<string, unknown>
    const candidates = (data.candidates as Record<string, unknown>[]) || []
    const hasPendingInterview = candidates.some(
      (c) => c.interview_id && c.status !== 'interview_completed'
    )
    if (!hasPendingInterview) return
    const interval = setInterval(async () => {
      try {
        await syncProjectInterviews(projectId)
        const updated = await getProjectDetail(projectId)
        setProject(updated)
      } catch {
        // ignore
      }
    }, 30_000)
    return () => clearInterval(interval)
  }, [projectId, project])

  // Load token usage
  const refreshUsage = () => {
    Promise.all([fetchUsageSummary(30), fetchUsageSummary24h()])
      .then(([total, daily]) => { setUsageTotal(total); setUsage24h(daily) })
      .catch(() => {})
  }
  useEffect(refreshUsage, [])

  // Load active chat messages
  useEffect(() => {
    if (!activeChatId) return
    getThread(activeChatId)
      .then((t) => {
        setActiveThread(t)
        setMessages(t.messages)
        if (t.task_type === 'offer_letter' || t.linked_offer_letter_id) {
          setOfferPdfUrl(getPdfProxyUrl(activeChatId, t.version))
        }
      })
      .catch(() => {})
  }, [activeChatId])

  // Auto-scroll
  const prevLen = useRef(0)
  useEffect(() => {
    if (messages.length > prevLen.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
    prevLen.current = messages.length
  }, [messages.length])

  function makeLocalMsg(role: 'user' | 'assistant', content: string): MWMessage {
    return {
      id: crypto.randomUUID(),
      thread_id: activeChatId || '',
      role,
      content,
      metadata: null,
      version_created: null,
      created_at: new Date().toISOString(),
    }
  }

  function askNextPlaceholder() {
    const next = pendingPlaceholders.current[0]
    if (!next) {
      setMessages((prev) => [...prev, makeLocalMsg('assistant', 'All fields filled! You can now finalize the posting.')])
      return
    }
    setMessages((prev) => [...prev, makeLocalMsg('assistant', next.question)])
  }

  async function handlePlaceholderAnswer(rawInput: string) {
    const entry = pendingPlaceholders.current.shift()
    if (!entry || !projectId) return
    const { placeholder, label } = entry

    // Add user message locally
    setMessages((prev) => [...prev, makeLocalMsg('user', rawInput)])

    // Extract clean value — uses AI for complex inputs, direct for simple ones
    let value = rawInput
    try {
      const result = await extractPlaceholderValue(rawInput, placeholder, label)
      value = result.value || rawInput
    } catch {
      // Fall back to raw input
    }

    // Fetch fresh project to get latest section content (avoid stale state)
    const fresh = await getProjectDetail(projectId)
    for (const section of fresh.sections ?? []) {
      if (section.content.includes(placeholder)) {
        const updated = section.content.replaceAll(placeholder, value)
        await updateProjectSectionNew(projectId, section.id, { content: updated })
      }
    }

    // Refresh to get the updated content into state
    const refreshed = await getProjectDetail(projectId)
    setProject(refreshed)

    // Ask next or finish
    askNextPlaceholder()
    setTimeout(() => textareaRef.current?.focus(), 50)
  }

  function handleSend() {
    const content = input.trim()
    if (!content) return
    setInput('')

    // If filling placeholders, handle locally — no AI round-trip
    if (pendingPlaceholders.current.length > 0) {
      handlePlaceholderAnswer(content)
      return
    }

    if (!activeChatId || streaming) return
    setStreaming(true)
    setError('')

    const tempMsg = makeLocalMsg('user', content)
    setMessages((prev) => [...prev, tempMsg])

    abortRef.current = sendMessageStream(activeChatId, content, {
      onEvent: (event: MWStreamEvent) => {
        if (event.type === 'status') setStatusMessage(event.message)
      },
      onComplete: async (data: MWSendResponse) => {
        setStatusMessage('')
        setMessages((prev) => {
          const withoutTemp = prev.filter((m) => m.id !== tempMsg.id)
          return [...withoutTemp, data.user_message, data.assistant_message]
        })
        if (data.task_type === 'offer_letter' || data.pdf_url) {
          setOfferPdfUrl(getPdfProxyUrl(activeChatId, data.version))
        }
        setStreaming(false)
        refreshUsage()
        // Refresh project data so side panel picks up AI-generated updates (posting, sections, etc.)
        if (projectId) {
          const updated = await getProjectDetail(projectId)
          setProject(updated)
        }
      },
      onError: (err) => {
        setStatusMessage('')
        setError(err)
        setStreaming(false)
      },
    }, { model: selectedModel })
  }

  async function handleNewChat() {
    if (!projectId) return
    try {
      const chat = await createProjectChat(projectId)
      setProject((prev) => prev ? { ...prev, chats: [...(prev.chats || []), chat], chat_count: (prev.chat_count || 0) + 1 } : prev)
      setActiveChatId(chat.id)
    } catch {}
  }

  const isPostingFinalized = project?.project_type === 'recruiting'
    && !!(((project.project_data || {}) as Record<string, unknown>).posting as Record<string, unknown> | undefined)?.finalized

  function handleResumeDropForProject(files: File[]) {
    if (!projectId || streaming) return
    if (!isPostingFinalized) {
      setError('Finalize the job posting before uploading resumes.')
      return
    }
    setStreaming(true)
    setStatusMessage('Uploading resumes...')
    uploadProjectResumes(projectId, files, {
      onEvent: (event: MWStreamEvent) => {
        if (event.type === 'status') setStatusMessage(event.message)
      },
      onComplete: async () => {
        setStatusMessage('')
        setStreaming(false)
        const updated = await getProjectDetail(projectId)
        setProject(updated)
      },
      onError: (err) => {
        setStatusMessage('')
        setError(err)
        setStreaming(false)
      },
    })
  }

  async function handleAddToProject(messageId: string, content: string) {
    if (!projectId) return
    try {
      await addProjectSectionNew(projectId, { content, source_message_id: messageId })
      const updated = await getProjectDetail(projectId)
      setProject(updated)
    } catch (e) {
      console.error('Add to project failed:', e)
      setError(e instanceof Error ? e.message : 'Failed to add to project')
    }
  }

  function dismissWizard() {
    setShowWizard(false)
    if (projectId) localStorage.setItem(`wizard-dismissed-${projectId}`, '1')
  }

  return {
    projectId,
    base,
    project,
    setProject,
    activeChatId,
    setActiveChatId,
    activeThread,
    messages,
    setMessages,
    input,
    setInput,
    streaming,
    statusMessage,
    loading,
    error,
    setError,
    selectedModel,
    setSelectedModel,
    usageTotal,
    usage24h,
    pendingPlaceholders,
    activeTab,
    setActiveTab,
    sidebarMode,
    setSidebarMode,
    mobileMenuOpen,
    setMobileMenuOpen,
    inbox,
    me,
    currentUserId,
    activePageKey,
    presence,
    cursorsActive,
    showTour,
    setShowTour,
    dismissTour,
    renamingChatId,
    setRenamingChatId,
    renameDraft,
    setRenameDraft,
    renameInputRef,
    handleRenameChat,
    handlePinChat,
    offerPdfUrl,
    showWizard,
    setShowWizard,
    isDragOver,
    setIsDragOver,
    showCollaborators,
    setShowCollaborators,
    messagesEndRef,
    textareaRef,
    resumeFileRef,
    makeLocalMsg,
    askNextPlaceholder,
    handleSend,
    handleNewChat,
    handleResumeDropForProject,
    handleAddToProject,
    isPostingFinalized,
    dismissWizard,
  }
}

export type ProjectViewModel = ReturnType<typeof useProjectView>
