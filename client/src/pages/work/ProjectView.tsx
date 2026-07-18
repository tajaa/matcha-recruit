import { useEffect, useRef, useState, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, ChevronLeft, Send, Loader2, Plus, MessageSquare, HelpCircle, UserPlus, Mail, Pin, PinOff, Pencil, Menu, Paperclip, KanbanSquare, FileText } from 'lucide-react'
import { listConversations, getConversation, sendMessage as sendInboxMessage, getUnreadCount } from '../../api/inbox'
import type { ConversationSummary, Conversation } from '../../api/inbox'
import { ConversationList } from '../../components/inbox/ConversationList'
import { MessageThread } from '../../components/inbox/MessageThread'
import { ComposeModal } from '../../components/inbox/ComposeModal'
import { useMe } from '../../hooks/useMe'
import type { MWMessage, MWThreadDetail, MWSendResponse, MWStreamEvent, MWProject } from '../../types/matchaWork'
import { getProjectDetail, getThread, sendMessageStream, createProjectChat, addProjectSectionNew, updateProjectSectionNew, uploadProjectResumes, sendProjectInterviews, syncProjectInterviews, analyzeProjectCandidates, extractPlaceholderValue, generatePlaceholderQuestions, fetchUsageSummary, fetchUsageSummary24h, updateTitle, pinThread, getPdfProxyUrl } from '../../api/matchaWork'
import type { UsageSummary } from '../../api/matchaWork'
import MessageBubble from '../../components/matcha-work/MessageBubble'
import ProjectPanel from '../../components/matcha-work/ProjectPanel'
import ProjectKanbanBoard from '../../components/work/ProjectKanbanBoard'
import BoardFilesTab from '../../components/work/BoardFilesTab'
import RecruitingPipeline from '../../components/matcha-work/RecruitingPipeline'
import RecruitingWizard from '../../components/matcha-work/RecruitingWizard'
import CollaboratorPanel from '../../components/matcha-work/CollaboratorPanel'
import CollaboratorsPill from '../../components/matcha-work/CollaboratorsPill'
import PresenceLayer from '../../components/matcha-work/PresenceLayer'
import ProjectTour, { type TourStep } from '../../components/matcha-work/ProjectTour'
import { useProjectPresence } from '../../hooks/useProjectPresence'
import { useWorkBase } from '../../routes/WorkSurfaceContext'

const TOUR_DISMISSED_KEY = 'mw_project_tour_dismissed'

const TOUR_STEPS: TourStep[] = [
  {
    target: '[data-tour="sections-panel"]',
    title: 'Sections — your project document',
    description: 'Pre-filled when you pick a template. Click any [bracketed placeholder] to edit, drag to reorder, or send a message in chat to auto-fill all placeholders at once.',
    side: 'left',
  },
  {
    target: '[data-tour="chat-input"]',
    title: 'AI chat — your project copilot',
    description: 'Type something like "Acme Corp · B2B SaaS · $25k Q3" and Matcha fills bracketed placeholders across every section. Also use it to add new sections, rewrite, or summarize.',
    side: 'top',
  },
  {
    target: '[data-tour="collaborators-pill"]',
    title: 'See who else is here',
    description: 'When teammates open the same project, you see their colored cursors and carets in real time. Names appear in the header pill so you know who else is around.',
    side: 'bottom',
  },
  {
    target: '[data-tour="export-button"]',
    title: 'Export & share',
    description: 'Export the project as PDF or DOCX. Invite collaborators from the project menu — anyone you invite can edit alongside you.',
    side: 'left',
  },
]
import { MODEL_OPTIONS, formatTokens } from '../../components/matcha-work/constants'

export default function ProjectView() {
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
  const [inboxConversations, setInboxConversations] = useState<ConversationSummary[]>([])
  const [inboxActiveConvo, setInboxActiveConvo] = useState<Conversation | null>(null)
  const [inboxLoading, setInboxLoading] = useState(false)
  const [inboxUnread, setInboxUnread] = useState(0)
  const [inboxComposeOpen, setInboxComposeOpen] = useState(false)
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

  const loadInbox = useCallback(async () => {
    setInboxLoading(true)
    try {
      const data = await listConversations()
      setInboxConversations(data)
    } catch {}
    setInboxLoading(false)
  }, [])

  useEffect(() => {
    getUnreadCount().then((r) => setInboxUnread(r.count)).catch(() => {})
    const id = setInterval(() => {
      getUnreadCount().then((r) => setInboxUnread(r.count)).catch(() => {})
    }, 60_000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    if (sidebarMode === 'inbox') loadInbox()
  }, [sidebarMode, loadInbox])

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

  if (loading) {
    return (
      <div className="flex justify-center items-center h-[calc(100vh-49px)]">
        <Loader2 className="animate-spin text-w-dim" size={24} />
      </div>
    )
  }

  if (!project) {
    return (
      <div className="flex flex-col items-center justify-center h-[calc(100vh-49px)] gap-4">
        <p className="text-red-400">{error || 'Project not found'}</p>
        <Link to={base} className="text-sm text-w-dim hover:text-white">Back to threads</Link>
      </div>
    )
  }

  const chats = project.chats || []

  function dismissWizard() {
    setShowWizard(false)
    if (projectId) localStorage.setItem(`wizard-dismissed-${projectId}`, '1')
  }

  const isRecruiting = project.project_type === 'recruiting'
  // Scope for now: a workspace only needs Chat + Kanban (recruiting swaps in its
  // Pipeline in place of Kanban — it has no board surface anywhere else in the
  // product, so tasks created there would be orphaned). Presentations keep the
  // sections panel as "Notes": those sections ARE the deliverable, and the panel
  // is their only viewer/exporter on web. Files comes later — its render branch
  // below stays intact, just unreferenced by this tab set.
  const workspaceTabs = isRecruiting
    ? [
        { key: 'chat' as const, icon: MessageSquare, label: 'Chat' },
        { key: 'panel' as const, icon: FileText, label: 'Pipeline' },
      ]
    : project.project_type === 'presentation'
    ? [
        { key: 'chat' as const, icon: MessageSquare, label: 'Chat' },
        { key: 'panel' as const, icon: FileText, label: 'Notes' },
        { key: 'board' as const, icon: KanbanSquare, label: 'Kanban' },
      ]
    : [
        { key: 'chat' as const, icon: MessageSquare, label: 'Chat' },
        { key: 'board' as const, icon: KanbanSquare, label: 'Kanban' },
      ]
  // The sections panel is only reachable when a `panel` tab exists. Chat writes
  // into it ("Add to Project"), so that affordance has to follow the tab set —
  // otherwise sections accumulate in a surface the UI can't open.
  const hasPanelTab = workspaceTabs.some((t) => t.key === 'panel')

  const SidebarContent = (
    <>
      {/* Top: back + (new chat, non-recruiting only) */}
      <div className="px-3 py-3 flex items-center justify-between shrink-0" style={{ borderBottom: '1px solid var(--color-w-line)' }}>
        <Link to={base} className="text-[var(--color-w-dim)] hover:text-[var(--color-w-text)]">
          <ArrowLeft size={14} />
        </Link>
        {!isRecruiting && (
          <button
            onClick={handleNewChat}
            title="New chat"
            className="p-1 rounded transition-colors text-[var(--color-w-dim)] hover:text-[var(--color-w-accent)]"
          >
            <Plus size={14} />
          </button>
        )}
      </div>

      {/* Project title (recruiting) or Chat list (other) */}
      {isRecruiting ? (
        <div className="flex-1 overflow-y-auto py-2 px-3">
          <p className="text-[10px] uppercase tracking-wider text-[var(--color-w-dim)] mb-1">Project</p>
          <p className="text-xs font-medium text-[var(--color-w-text)] truncate" title={project.title}>{project.title}</p>
        </div>
      ) : (
      <div className="flex-1 overflow-y-auto py-1">
        {[...(chats || [])].sort((a, b) => (b.is_pinned ? 1 : 0) - (a.is_pinned ? 1 : 0)).map((c) => (
          <div
            key={c.id}
            className={`group flex items-center px-3 py-2 transition-colors cursor-pointer ${
              activeChatId === c.id && sidebarMode === 'chats'
                ? 'text-[var(--color-w-text)]'
                : 'text-[var(--color-w-dim)] hover:text-[var(--color-w-text)]'
            }`}
            style={activeChatId === c.id && sidebarMode === 'chats' ? { background: 'var(--color-w-surface2)' } : {}}
            onClick={() => { setActiveChatId(c.id); setSidebarMode('chats'); setMobileMenuOpen(false) }}
          >
            {renamingChatId === c.id ? (
              <input
                ref={renameInputRef}
                value={renameDraft}
                onChange={(e) => setRenameDraft(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleRenameChat(c.id); if (e.key === 'Escape') setRenamingChatId(null) }}
                onBlur={() => handleRenameChat(c.id)}
                autoFocus
                className="flex-1 text-xs bg-transparent border-b border-[var(--color-w-accent)] outline-none text-[var(--color-w-text)] min-w-0"
                onClick={(e) => e.stopPropagation()}
              />
            ) : (
              <>
                {c.is_pinned && <Pin size={8} className="shrink-0 mr-1 text-[var(--color-w-accent)]" />}
                <MessageSquare size={10} className="shrink-0 mr-1.5" />
                <span className="flex-1 text-xs truncate">{c.title}</span>
                <div className="hidden group-hover:flex items-center gap-0.5 shrink-0 ml-1">
                  <button
                    onClick={(e) => { e.stopPropagation(); setRenamingChatId(c.id); setRenameDraft(c.title) }}
                    className="p-0.5 rounded hover:text-[var(--color-w-accent)]"
                    title="Rename"
                  >
                    <Pencil size={9} />
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); handlePinChat(c.id, c.is_pinned) }}
                    className="p-0.5 rounded hover:text-[var(--color-w-accent)]"
                    title={c.is_pinned ? 'Unpin' : 'Pin'}
                  >
                    {c.is_pinned ? <PinOff size={9} /> : <Pin size={9} />}
                  </button>
                </div>
              </>
            )}
          </div>
        ))}
      </div>
      )}

      {/* Bottom: Inbox + User */}
      <div style={{ borderTop: '1px solid var(--color-w-line)' }} className="shrink-0">
        <button
          onClick={() => { setSidebarMode(sidebarMode === 'inbox' ? 'chats' : 'inbox'); setActiveTab('chat'); setMobileMenuOpen(false) }}
          className={`w-full flex items-center gap-1.5 px-3 py-2.5 text-xs transition-colors ${
            sidebarMode === 'inbox' ? 'text-[var(--color-w-text)]' : 'text-[var(--color-w-dim)] hover:text-[var(--color-w-text)]'
          }`}
          style={sidebarMode === 'inbox' ? { background: 'var(--color-w-surface2)' } : {}}
        >
          <Mail size={12} />
          <span className="flex-1 text-left">Inbox</span>
          {inboxUnread > 0 && (
            <span className="w-4 h-4 rounded-full bg-blue-500 text-[8px] font-bold text-white flex items-center justify-center">
              {inboxUnread > 9 ? '9+' : inboxUnread}
            </span>
          )}
        </button>
        <Link
          to="/app/settings"
          className="flex items-center gap-1.5 px-3 py-2.5 text-xs text-[var(--color-w-dim)] hover:text-[var(--color-w-text)] transition-colors"
        >
          {me?.user?.avatar_url ? (
            <img src={me.user.avatar_url} className="w-5 h-5 rounded-full object-cover" alt="" />
          ) : (
            <div className="w-5 h-5 rounded-full bg-w-surface2 flex items-center justify-center text-[8px] font-bold text-w-text">
              {(me?.profile?.name || me?.user?.email || '?')[0].toUpperCase()}
            </div>
          )}
          <span className="truncate">{me?.profile?.name || me?.user?.email || 'Settings'}</span>
        </Link>
      </div>
    </>
  )

  return (
    <div className="flex flex-col md:flex-row h-full min-h-0 relative overflow-hidden bg-w-bg">
      {/* Mobile Sidebar Overlay */}
      {mobileMenuOpen && (
        <div 
          className="fixed inset-0 bg-black/60 z-40 md:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* Mobile Chat Sidebar */}
      <div className={`fixed inset-y-0 left-0 z-50 transform transition-transform duration-200 ease-in-out md:hidden flex flex-col w-[240px] shrink-0 h-[calc(100dvh-49px)] top-[49px] ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}`} style={{ borderRight: '1px solid var(--color-w-line)', background: 'var(--color-w-surface)' }}>
        {SidebarContent}
      </div>

      {/* Desktop Chat Sidebar — hidden for recruiting projects (single-chat flow, no list needed) */}
      {!isRecruiting && (
        <div className="hidden md:flex flex-col w-[200px] shrink-0 border-r border-w-line bg-w-surface">
          {SidebarContent}
        </div>
      )}

      {/* Main column — back bar + tab strip (desktop) + the active surface + bottom bar (mobile) */}
      <div className="flex-1 min-w-0 min-h-0 flex flex-col">

      {/* Desktop back bar + tab strip */}
      <div className="hidden md:flex flex-col shrink-0 border-b border-w-line">
        <Link
          to={base}
          className="flex items-center gap-1 px-3 pt-2.5 pb-1 text-[12px] text-w-dim hover:text-w-text transition-colors w-fit"
        >
          <ChevronLeft size={13} />
          Workspaces
        </Link>
        <div className="flex items-center gap-1 px-2.5 pb-2">
          {workspaceTabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key)}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[13px] font-medium transition-colors border ${
                activeTab === t.key
                  ? 'bg-w-surface2 border-w-line text-w-accent'
                  : 'border-transparent text-w-dim hover:text-w-text hover:bg-w-surface2/60'
              }`}
            >
              <t.icon size={14} />
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Center — inbox view when sidebar is in inbox mode */}
      {sidebarMode === 'inbox' && (
        <div className={`flex-1 flex-col min-w-0 min-h-0 bg-w-bg ${activeTab === 'chat' ? 'flex' : 'hidden'}`}>
          {inboxActiveConvo ? (
            <MessageThread
              conversation={inboxActiveConvo}
              currentUserId={currentUserId}
              onSendMessage={async (content) => {
                const msg = await sendInboxMessage(inboxActiveConvo.id, content)
                setInboxActiveConvo((prev) => prev ? { ...prev, messages: [...prev.messages, msg] } : prev)
              }}
              onMarkRead={() => {}}
              onBack={() => { setInboxActiveConvo(null); loadInbox() }}
            />
          ) : inboxLoading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 size={20} className="animate-spin text-[var(--color-w-dim)]" />
            </div>
          ) : (
            <ConversationList
              conversations={inboxConversations}
              selectedId={null}
              currentUserId={currentUserId}
              onSelect={async (id) => {
                try {
                  const convo = await getConversation(id)
                  setInboxActiveConvo(convo)
                } catch {}
              }}
              onCompose={() => setInboxComposeOpen(true)}
              onMenuToggle={() => setMobileMenuOpen(true)}
            />
          )}
          <ComposeModal
            isOpen={inboxComposeOpen}
            onClose={() => setInboxComposeOpen(false)}
            onCreated={(convo) => {
              setInboxActiveConvo(convo)
              setInboxComposeOpen(false)
              loadInbox()
            }}
          />
        </div>
      )}

      {/* Center — chat messages */}
      {sidebarMode === 'chats' && (
      <div className={`flex-1 flex-col min-w-0 min-h-0 ${activeTab === 'chat' ? 'flex' : 'hidden'}`}>
        {/* Header */}
        <div className="px-4 py-2 flex items-center gap-2" style={{ borderBottom: '1px solid var(--color-w-line)' }}>
          {isRecruiting ? (
            <Link to={base} className="text-[var(--color-w-dim)] hover:text-[var(--color-w-text)]" title="Back to workspace">
              <ArrowLeft size={14} />
            </Link>
          ) : (
            <button onClick={() => setMobileMenuOpen(true)} className="sm:hidden text-[var(--color-w-dim)] hover:text-[var(--color-w-text)]">
              <Menu size={14} />
            </button>
          )}
          <h2 className="text-xs font-medium truncate" style={{ color: 'var(--color-w-text)' }}>
            {project.title}
          </h2>
          {activeThread && (
            <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ color: 'var(--color-w-dim)', background: 'var(--color-w-surface2)' }}>
              {activeThread.title}
            </span>
          )}
          <div className="flex items-center gap-1.5 ml-auto">
            {/* Share / collaborators (admin only) */}
            {project.collaborator_role && (
              <div className="relative">
                <button
                  onClick={() => { if (!showCollaborators) setShowCollaborators(true) }}
                  className="p-1 rounded transition-colors"
                  style={{ color: showCollaborators ? 'var(--color-w-accent)' : 'var(--color-w-dim)' }}
                  title="Share project"
                >
                  <UserPlus size={14} />
                </button>
                {showCollaborators && (
                  <CollaboratorPanel
                    projectId={projectId!}
                    currentUserRole={project.collaborator_role}
                    onClose={() => setShowCollaborators(false)}
                  />
                )}
              </div>
            )}
            {/* Model selector */}
            <select
              value={selectedModel}
              onChange={(e) => {
                setSelectedModel(e.target.value)
                localStorage.setItem('mw-model', e.target.value)
              }}
              className="shrink-0 text-[11px] font-medium rounded-full px-2.5 py-1 appearance-none cursor-pointer border-0"
              style={{ background: 'var(--color-w-surface2)', color: 'var(--color-w-dim)' }}
            >
              {MODEL_OPTIONS.map((m) => (
                <option key={m.id} value={m.id}>{m.label}</option>
              ))}
            </select>

            {/* Token counter */}
            {(usage24h?.totals.total_tokens || usageTotal?.totals.total_tokens) ? (
              <div className="hidden sm:flex items-center gap-1.5 text-[10px] font-mono" style={{ color: 'var(--color-w-dim)' }}>
                {usage24h && usage24h.totals.total_tokens > 0 && <span>24h: {formatTokens(usage24h.totals.total_tokens)}</span>}
                {usage24h?.totals.total_tokens && usageTotal?.totals.total_tokens ? <span>|</span> : null}
                {usageTotal && usageTotal.totals.total_tokens > 0 && <span>30d: {formatTokens(usageTotal.totals.total_tokens)}</span>}
              </div>
            ) : null}

            {project.project_type === 'recruiting' && messages.length === 0 && (
              <button
                onClick={() => setShowWizard(true)}
                title="How it works"
                className="p-1 rounded transition-colors text-[var(--color-w-dim)] hover:text-[var(--color-w-accent)]"
              >
                <HelpCircle size={14} />
              </button>
            )}
            {project.project_type !== 'recruiting' && (
              <button
                onClick={() => setShowTour(true)}
                title="Project tour"
                className="p-1 rounded transition-colors text-[var(--color-w-dim)] hover:text-[var(--color-w-accent)]"
              >
                <HelpCircle size={14} />
              </button>
            )}
          </div>
        </div>

        {/* Messages + drop zone */}
        <div
          className="flex-1 overflow-y-auto px-4 py-4 space-y-4 relative"
          onDragOver={(e) => { e.preventDefault(); if (!streaming) setIsDragOver(true) }}
          onDragLeave={(e) => { if (e.currentTarget.contains(e.relatedTarget as Node)) return; setIsDragOver(false) }}
          onDrop={(e) => {
            e.preventDefault()
            setIsDragOver(false)
            const files = Array.from(e.dataTransfer.files)
            if (files.length > 0 && project?.project_type === 'recruiting') {
              handleResumeDropForProject(files)
            }
          }}
        >
          {isDragOver && project?.project_type === 'recruiting' && (
            <div
              className="absolute inset-0 z-10 border-2 border-dashed rounded-lg flex items-center justify-center pointer-events-none"
              style={{
                background: isPostingFinalized ? 'rgba(242,106,33,0.08)' : 'rgba(245,158,11,0.08)',
                borderColor: isPostingFinalized ? 'var(--color-w-accent)' : '#f59e0b',
              }}
            >
              <p className="text-sm font-medium" style={{ color: isPostingFinalized ? 'var(--color-w-accent)' : '#f59e0b' }}>
                {isPostingFinalized ? 'Drop resumes here to add candidates' : 'Finalize the posting first before adding resumes'}
              </p>
            </div>
          )}
          {messages.length === 0 && showWizard && project?.project_type === 'recruiting' ? (
            <div className="flex items-center justify-center h-full">
              <RecruitingWizard
                onDismiss={dismissWizard}
                onStartHiring={() => {
                  dismissWizard()
                  setTimeout(() => textareaRef.current?.focus(), 50)
                }}
              />
            </div>
          ) : messages.length === 0 ? (
            <div className="flex items-center justify-center h-full text-sm" style={{ color: 'var(--color-w-dim)' }}>
              {project?.project_type === 'recruiting'
                ? (isPostingFinalized
                    ? 'Posting finalized. Drop resumes to add candidates.'
                    : 'Describe the role you\'re hiring for, then click "Add to Project" to build the posting.')
                : hasPanelTab
                ? 'Start chatting \u2014 use "Add to Project" to build your document.'
                : 'Start chatting.'}
            </div>
          ) : null}
          {messages.map((m) => (
            <MessageBubble
              key={m.id}
              message={m}
              isProjectThread
              // Only offer "Add to Project" when a panel tab exists to view the
              // result \u2014 otherwise the section is written somewhere unreachable.
              onAddToProject={hasPanelTab ? (msgId, content) => handleAddToProject(msgId, content) : undefined}
            />
          ))}
          {streaming && (
            <div className="flex justify-start">
              <div className="rounded-lg px-4 py-2.5 flex items-center gap-2" style={{ background: 'var(--color-w-surface)', border: '1px solid var(--color-w-line)' }}>
                <Loader2 size={14} className="animate-spin" style={{ color: 'var(--color-w-dim)' }} />
                <span className="text-sm" style={{ color: 'var(--color-w-dim)' }}>{statusMessage || 'Thinking...'}</span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Error */}
        {error && (
          <div className="mx-4 mb-2 p-2 bg-red-900/30 border border-red-800 rounded text-red-300 text-xs">
            {error}
            <button onClick={() => setError('')} className="ml-2 underline">Dismiss</button>
          </div>
        )}

        {/* Input */}
        <div className="px-4 py-3" style={{ borderTop: '1px solid var(--color-w-line)' }}>
          <div className="flex items-end gap-2">
            {project?.project_type === 'recruiting' && isPostingFinalized && (
              <>
                <input
                  type="file"
                  ref={resumeFileRef}
                  multiple
                  accept=".pdf,.doc,.docx,.txt"
                  className="hidden"
                  onChange={(e) => {
                    const files = Array.from(e.target.files || [])
                    if (files.length > 0) handleResumeDropForProject(files)
                    e.target.value = ''
                  }}
                />
                <button
                  onClick={() => resumeFileRef.current?.click()}
                  disabled={streaming}
                  className="p-2.5 rounded-lg transition-colors disabled:opacity-40 hover:bg-w-surface2/50"
                  style={{ color: 'var(--color-w-dim)' }}
                  title="Upload resumes"
                >
                  <Paperclip size={18} />
                </button>
              </>
            )}
            <textarea
              ref={textareaRef}
              data-tour="chat-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
              placeholder={project?.project_type === 'recruiting' && isPostingFinalized ? 'Type a message or upload resumes...' : 'Type a message...'}
              rows={1}
              disabled={streaming || (!activeChatId && pendingPlaceholders.current.length === 0)}
              className="flex-1 text-sm rounded-lg px-3 py-2.5 border focus:outline-none resize-none disabled:opacity-50 min-h-[44px]"
              style={{ background: 'var(--color-w-surface)', color: 'var(--color-w-text)', borderColor: 'var(--color-w-line)' }}
            />
            <button
              onClick={handleSend}
              disabled={streaming || !input.trim() || (!activeChatId && pendingPlaceholders.current.length === 0)}
              className="p-3 rounded-lg transition-colors disabled:opacity-40"
              style={{ background: 'var(--color-w-accent)', color: '#fff' }}
            >
              {streaming ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            </button>
          </div>
        </div>
      </div>
      )}

      {/* Right — Project panel or Recruiting pipeline */}
      <div
        className={`${activeTab === 'panel' ? 'flex' : 'hidden'} flex-1 w-full min-w-0 min-h-0 flex-col`}
        data-tour="sections-panel"
      >
        {/* Collaborator presence pill (cross-tab awareness). Always rendered
            so the onboarding tour can target it; shows "Working solo" when
            no one else is in the project. */}
        <div
          data-tour="collaborators-pill"
          className="flex items-center justify-end px-3 py-1"
          style={{ borderBottom: '1px solid var(--color-w-line)', background: 'var(--color-w-bg)' }}
        >
          {presence.members.length > 1 ? (
            <CollaboratorsPill members={presence.members} selfId={currentUserId} />
          ) : (
            <span style={{ fontSize: 10, color: 'var(--color-w-line)' }}>Working solo</span>
          )}
        </div>
        <PresenceLayer
          members={presence.members}
          remoteCursors={presence.remoteCursors}
          reportCursor={presence.reportCursor}
          selfId={currentUserId}
          pageKey={activePageKey}
          enabled={cursorsActive}
        >
        {project.project_type === 'recruiting' ? (
          <RecruitingPipeline
            project={project}
            projectId={projectId!}
            onUpdate={(updated) => setProject(updated)}
            streaming={streaming}
            offerPdfUrl={offerPdfUrl}
            onSendInterviews={async (ids, positionTitle) => {
              try {
                const result = await sendProjectInterviews(projectId!, ids, positionTitle)
                if (result.sent.length > 0) {
                  const updated = await getProjectDetail(projectId!)
                  setProject(updated)
                }
                if (result.failed.length > 0) {
                  setError(`Failed to send ${result.failed.length} interview(s): ${result.failed.map((f) => f.error).join(', ')}`)
                }
              } catch (e) {
                setError(e instanceof Error ? e.message : 'Failed to send interviews.')
              }
            }}
            onSyncInterviews={async () => {
              try {
                await syncProjectInterviews(projectId!)
                const updated = await getProjectDetail(projectId!)
                setProject(updated)
              } catch {
                setError('Failed to sync interview statuses.')
              }
            }}
            onAnalyzeCandidates={async () => {
              try {
                await analyzeProjectCandidates(projectId!)
                const updated = await getProjectDetail(projectId!)
                setProject(updated)
              } catch (e) {
                setError(e instanceof Error ? e.message : 'Failed to analyze candidates.')
              }
            }}
            onPromptChat={async (placeholders) => {
              setMessages((prev) => [...prev, makeLocalMsg('assistant', `Let me figure out what's missing...`)])
              try {
                const { questions } = await generatePlaceholderQuestions(placeholders)
                pendingPlaceholders.current = questions
              } catch {
                // Fallback to raw labels
                pendingPlaceholders.current = placeholders.map((p) => ({ ...p, question: `What's the ${p.placeholder}?` }))
              }
              setMessages((prev) => [...prev, makeLocalMsg('assistant', `Let's fill in the missing fields for the posting.`)])
              askNextPlaceholder()
              setTimeout(() => textareaRef.current?.focus(), 50)
            }}
          />
        ) : (
          <ProjectPanel
            projectId={projectId!}
            project={project}
            onProjectUpdate={(updated) => setProject(updated)}
            selfId={currentUserId}
            members={presence.members}
            remoteCarets={presence.remoteCarets}
            onCaretChange={presence.reportCaret}
          />
        )}
        </PresenceLayer>
      </div>

      {/* Kanban board */}
      {activeTab === 'board' && !isRecruiting && (
        <div className="flex-1 min-h-0 flex flex-col bg-w-bg">
          <ProjectKanbanBoard projectId={projectId!} />
        </div>
      )}

      {/* Files */}
      {activeTab === 'files' && (
        <div className="flex-1 min-h-0 flex flex-col bg-w-bg">
          <BoardFilesTab projectId={projectId!} />
        </div>
      )}

      {/* Mobile bottom tab bar — same tab set as the desktop strip */}
      <nav
        className="md:hidden shrink-0 flex items-stretch border-t border-w-line bg-w-surface"
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      >
        {workspaceTabs.map((t) => {
          const active = activeTab === t.key
          return (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key)}
              className={`flex-1 flex flex-col items-center justify-center gap-0.5 py-2 transition-colors ${
                active ? 'text-w-accent' : 'text-w-dim'
              }`}
            >
              <span
                className={`flex items-center justify-center rounded-lg px-3.5 py-1 transition-colors ${
                  active ? 'bg-w-accent/15' : ''
                }`}
              >
                <t.icon size={18} />
              </span>
              <span className="text-[10px] font-medium">{t.label}</span>
            </button>
          )
        })}
      </nav>

      </div>

      {showTour && project.project_type !== 'recruiting' && (
        // Three of the four steps point into the sections panel (and its export
        // button). Without a panel tab those targets never render, and the tour
        // would narrate — then dead-end on — UI the user can't reach.
        <ProjectTour
          steps={hasPanelTab ? TOUR_STEPS : TOUR_STEPS.filter((s) => s.target === '[data-tour="chat-input"]')}
          onComplete={dismissTour}
        />
      )}
    </div>
  )
}
