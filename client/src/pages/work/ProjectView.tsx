import { useEffect, useRef, useState, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Send, Loader2, Plus, MessageSquare, ChevronRight, FileText, Users, Video, Star, HelpCircle, UserPlus, Mail, Pin, PinOff, Pencil } from 'lucide-react'
import { listConversations, getConversation, sendMessage as sendInboxMessage, getUnreadCount } from '../../api/inbox'
import type { ConversationSummary, Conversation } from '../../api/inbox'
import { ConversationList } from '../../components/inbox/ConversationList'
import { MessageThread } from '../../components/inbox/MessageThread'
import { ComposeModal } from '../../components/inbox/ComposeModal'
import { useMe } from '../../hooks/useMe'
import type { MWMessage, MWThreadDetail, MWSendResponse, MWStreamEvent, MWProject } from '../../types/matcha-work'
import { getProjectDetail, getThread, sendMessageStream, createProjectChat, addProjectSectionNew, updateProjectSectionNew, uploadProjectResumes, sendProjectInterviews, syncProjectInterviews, analyzeProjectCandidates, extractPlaceholderValue, generatePlaceholderQuestions, fetchUsageSummary, fetchUsageSummary24h, updateTitle, pinThread } from '../../api/matchaWork'
import type { UsageSummary } from '../../api/matchaWork'
import MessageBubble from '../../components/matcha-work/MessageBubble'
import ProjectPanel from '../../components/matcha-work/ProjectPanel'
import RecruitingPipeline from '../../components/matcha-work/RecruitingPipeline'
import CollaboratorPanel from '../../components/matcha-work/CollaboratorPanel'
import { MODEL_OPTIONS, formatTokens } from '../../components/matcha-work/constants'

export default function ProjectView() {
  const { projectId } = useParams<{ projectId: string }>()
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

  // Mobile panel toggle: chat vs panel
  const [mobileView, setMobileView] = useState<'chat' | 'panel'>('chat')

  // Sidebar mode: 'chats' or 'inbox'
  const [sidebarMode, setSidebarMode] = useState<'chats' | 'inbox'>('chats')
  const [inboxConversations, setInboxConversations] = useState<ConversationSummary[]>([])
  const [inboxActiveConvo, setInboxActiveConvo] = useState<Conversation | null>(null)
  const [inboxLoading, setInboxLoading] = useState(false)
  const [inboxUnread, setInboxUnread] = useState(0)
  const [inboxComposeOpen, setInboxComposeOpen] = useState(false)
  const { me } = useMe()
  const currentUserId = me?.user?.id ?? ''

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

  // Recruiting wizard + drag-and-drop
  const [showWizard, setShowWizard] = useState(false)
  const [wizardStep, setWizardStep] = useState(0)
  const [isDragOver, setIsDragOver] = useState(false)
  const [showCollaborators, setShowCollaborators] = useState(false)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Load project
  useEffect(() => {
    if (!projectId) return
    setLoading(true)
    getProjectDetail(projectId)
      .then((p) => {
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
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load project'))
      .finally(() => setLoading(false))
    return () => { abortRef.current?.abort() }
  }, [projectId])

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
      onComplete: (data: MWSendResponse) => {
        setStatusMessage('')
        setMessages((prev) => {
          const withoutTemp = prev.filter((m) => m.id !== tempMsg.id)
          return [...withoutTemp, data.user_message, data.assistant_message]
        })
        setStreaming(false)
        refreshUsage()
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
        <Loader2 className="animate-spin text-zinc-500" size={24} />
      </div>
    )
  }

  if (!project) {
    return (
      <div className="flex flex-col items-center justify-center h-[calc(100vh-49px)] gap-4">
        <p className="text-red-400">{error || 'Project not found'}</p>
        <Link to="/work" className="text-sm text-zinc-400 hover:text-white">Back to threads</Link>
      </div>
    )
  }

  const chats = project.chats || []

  const WIZARD_STEPS = [
    {
      icon: FileText,
      title: 'Draft your job posting',
      desc: 'Use the chat to describe the role. The AI will help you write a job description, requirements, and compensation details.',
    },
    {
      icon: Users,
      title: 'Upload candidate resumes',
      desc: 'Drag and drop resume files (PDF, DOCX, TXT) into the chat. The AI extracts key candidate info automatically and adds them to your pipeline.',
    },
    {
      icon: Star,
      title: 'Review and shortlist',
      desc: 'Browse candidates in the right panel. Star your top picks to build a shortlist. Search and sort by experience, skills, or location.',
    },
    {
      icon: Video,
      title: 'Send to AI interview',
      desc: 'Select candidates and send them a Gemini Live voice interview. They get an email link — no account needed. Results sync back with scores and summaries.',
    },
  ]

  function dismissWizard() {
    setShowWizard(false)
    if (projectId) localStorage.setItem(`wizard-dismissed-${projectId}`, '1')
  }

  if (showWizard) {
    const step = WIZARD_STEPS[wizardStep]
    const StepIcon = step.icon
    const isLast = wizardStep === WIZARD_STEPS.length - 1

    return (
      <div className="flex items-center justify-center h-[calc(100vh-49px)]" style={{ background: '#1e1e1e' }}>
        <div className="w-full max-w-md mx-4 rounded-xl border p-6" style={{ background: '#252526', borderColor: '#333' }}>
          {/* Progress dots */}
          <div className="flex items-center justify-center gap-2 mb-6">
            {WIZARD_STEPS.map((_, i) => (
              <div
                key={i}
                className="rounded-full transition-colors"
                style={{
                  width: i === wizardStep ? 24 : 8,
                  height: 8,
                  background: i === wizardStep ? '#ce9178' : i < wizardStep ? '#22c55e' : '#444',
                  borderRadius: 4,
                }}
              />
            ))}
          </div>

          {/* Icon */}
          <div className="flex justify-center mb-4">
            <div className="p-3 rounded-full" style={{ background: '#ce9178' + '20' }}>
              <StepIcon size={28} style={{ color: '#ce9178' }} />
            </div>
          </div>

          {/* Content */}
          <h2 className="text-center text-lg font-semibold mb-2" style={{ color: '#e8e8e8' }}>
            {step.title}
          </h2>
          <p className="text-center text-sm leading-relaxed mb-6" style={{ color: '#9ca3af' }}>
            {step.desc}
          </p>

          {/* Step indicator */}
          <p className="text-center text-[10px] mb-4" style={{ color: '#6a737d' }}>
            Step {wizardStep + 1} of {WIZARD_STEPS.length}
          </p>

          {/* Buttons */}
          <div className="flex items-center justify-between">
            <button
              onClick={dismissWizard}
              className="text-xs transition-colors"
              style={{ color: '#6a737d' }}
            >
              Skip
            </button>
            <div className="flex gap-2">
              {wizardStep > 0 && (
                <button
                  onClick={() => setWizardStep(wizardStep - 1)}
                  className="px-4 py-2 text-xs font-medium rounded-lg transition-colors"
                  style={{ color: '#d4d4d4', background: '#333' }}
                >
                  Back
                </button>
              )}
              <button
                onClick={() => isLast ? dismissWizard() : setWizardStep(wizardStep + 1)}
                className="px-4 py-2 text-xs font-medium rounded-lg transition-colors flex items-center gap-1"
                style={{ background: '#22c55e', color: '#fff' }}
              >
                {isLast ? 'Get Started' : 'Next'}
                {!isLast && <ChevronRight size={12} />}
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-[calc(100vh-49px)]" style={{ background: '#1e1e1e' }}>
      {/* Chat sidebar */}
      <div className="hidden sm:flex flex-col w-[180px] shrink-0" style={{ borderRight: '1px solid #333', background: '#252526' }}>
        {/* Top: back + new chat */}
        <div className="px-3 py-3 flex items-center justify-between" style={{ borderBottom: '1px solid #333' }}>
          <Link to="/work" className="text-[#6a737d] hover:text-[#e8e8e8]">
            <ArrowLeft size={14} />
          </Link>
          <button
            onClick={handleNewChat}
            title="New chat"
            className="p-1 rounded transition-colors text-[#6a737d] hover:text-[#ce9178]"
          >
            <Plus size={14} />
          </button>
        </div>

        {/* Chat list */}
        <div className="flex-1 overflow-y-auto py-1">
          {[...(chats || [])].sort((a, b) => (b.is_pinned ? 1 : 0) - (a.is_pinned ? 1 : 0)).map((c) => (
            <div
              key={c.id}
              className={`group flex items-center px-3 py-2 transition-colors cursor-pointer ${
                activeChatId === c.id && sidebarMode === 'chats'
                  ? 'text-[#e8e8e8]'
                  : 'text-[#6a737d] hover:text-[#d4d4d4]'
              }`}
              style={activeChatId === c.id && sidebarMode === 'chats' ? { background: '#2a2d2e' } : {}}
              onClick={() => { setActiveChatId(c.id); setSidebarMode('chats') }}
            >
              {renamingChatId === c.id ? (
                <input
                  ref={renameInputRef}
                  value={renameDraft}
                  onChange={(e) => setRenameDraft(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleRenameChat(c.id); if (e.key === 'Escape') setRenamingChatId(null) }}
                  onBlur={() => handleRenameChat(c.id)}
                  autoFocus
                  className="flex-1 text-xs bg-transparent border-b border-[#ce9178] outline-none text-[#e8e8e8] min-w-0"
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <>
                  {c.is_pinned && <Pin size={8} className="shrink-0 mr-1 text-[#ce9178]" />}
                  <MessageSquare size={10} className="shrink-0 mr-1.5" />
                  <span className="flex-1 text-xs truncate">{c.title}</span>
                  <div className="hidden group-hover:flex items-center gap-0.5 shrink-0 ml-1">
                    <button
                      onClick={(e) => { e.stopPropagation(); setRenamingChatId(c.id); setRenameDraft(c.title) }}
                      className="p-0.5 rounded hover:text-[#ce9178]"
                      title="Rename"
                    >
                      <Pencil size={9} />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); handlePinChat(c.id, c.is_pinned) }}
                      className="p-0.5 rounded hover:text-[#ce9178]"
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

        {/* Bottom: Inbox + User */}
        <div style={{ borderTop: '1px solid #333' }}>
          <button
            onClick={() => { setSidebarMode(sidebarMode === 'inbox' ? 'chats' : 'inbox') }}
            className={`w-full flex items-center gap-1.5 px-3 py-2.5 text-xs transition-colors ${
              sidebarMode === 'inbox' ? 'text-[#e8e8e8]' : 'text-[#6a737d] hover:text-[#d4d4d4]'
            }`}
            style={sidebarMode === 'inbox' ? { background: '#2a2d2e' } : {}}
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
            className="flex items-center gap-1.5 px-3 py-2.5 text-xs text-[#6a737d] hover:text-[#d4d4d4] transition-colors"
          >
            {me?.user?.avatar_url ? (
              <img src={me.user.avatar_url} className="w-5 h-5 rounded-full object-cover" alt="" />
            ) : (
              <div className="w-5 h-5 rounded-full bg-zinc-700 flex items-center justify-center text-[8px] font-bold text-zinc-300">
                {(me?.profile?.name || me?.user?.email || '?')[0].toUpperCase()}
              </div>
            )}
            <span className="truncate">{me?.profile?.name || me?.user?.email || 'Settings'}</span>
          </Link>
        </div>
      </div>

      {/* Center — inbox view when sidebar is in inbox mode */}
      {sidebarMode === 'inbox' && (
        <div className={`flex-1 flex flex-col min-w-0 ${mobileView === 'panel' ? 'hidden md:flex' : 'flex'}`} style={{ borderRight: '1px solid #333', background: '#1e1e1e' }}>
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
              <Loader2 size={20} className="animate-spin text-[#6a737d]" />
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
      <div className={`flex-1 flex flex-col min-w-0 ${mobileView === 'panel' ? 'hidden md:flex' : 'flex'}`} style={{ borderRight: '1px solid #333' }}>
        {/* Header */}
        <div className="px-4 py-2 flex items-center gap-2" style={{ borderBottom: '1px solid #333' }}>
          <Link to="/work" className="sm:hidden text-[#6a737d] hover:text-[#e8e8e8]">
            <ArrowLeft size={14} />
          </Link>
          <h2 className="text-xs font-medium truncate" style={{ color: '#e8e8e8' }}>
            {project.title}
          </h2>
          {activeThread && (
            <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ color: '#6a737d', background: '#2a2d2e' }}>
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
                  style={{ color: showCollaborators ? '#ce9178' : '#6a737d' }}
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
            {/* Mobile view toggle */}
            <div className="flex md:hidden rounded overflow-hidden" style={{ border: '1px solid #444' }}>
              <button
                onClick={() => setMobileView('chat')}
                className="px-2.5 py-1 text-[10px] font-medium"
                style={{ background: mobileView === 'chat' ? '#ce9178' : '#2a2d2e', color: mobileView === 'chat' ? '#fff' : '#6a737d' }}
              >
                Chat
              </button>
              <button
                onClick={() => setMobileView('panel')}
                className="px-2.5 py-1 text-[10px] font-medium"
                style={{ background: mobileView === 'panel' ? '#ce9178' : '#2a2d2e', color: mobileView === 'panel' ? '#fff' : '#6a737d' }}
              >
                {project.project_type === 'recruiting' ? 'Pipeline' : 'Project'}
              </button>
            </div>
            {/* Model selector */}
            <select
              value={selectedModel}
              onChange={(e) => {
                setSelectedModel(e.target.value)
                localStorage.setItem('mw-model', e.target.value)
              }}
              className="shrink-0 text-[11px] font-medium rounded-full px-2.5 py-1 appearance-none cursor-pointer border-0"
              style={{ background: '#2a2d2e', color: '#9ca3af' }}
            >
              {MODEL_OPTIONS.map((m) => (
                <option key={m.id} value={m.id}>{m.label}</option>
              ))}
            </select>

            {/* Token counter */}
            {(usage24h?.totals.total_tokens || usageTotal?.totals.total_tokens) ? (
              <div className="hidden sm:flex items-center gap-1.5 text-[10px] font-mono" style={{ color: '#6a737d' }}>
                {usage24h && usage24h.totals.total_tokens > 0 && <span>24h: {formatTokens(usage24h.totals.total_tokens)}</span>}
                {usage24h?.totals.total_tokens && usageTotal?.totals.total_tokens ? <span>|</span> : null}
                {usageTotal && usageTotal.totals.total_tokens > 0 && <span>30d: {formatTokens(usageTotal.totals.total_tokens)}</span>}
              </div>
            ) : null}

            {project.project_type === 'recruiting' && (
              <button
                onClick={() => { setWizardStep(0); setShowWizard(true) }}
                title="How it works"
                className="p-1 rounded transition-colors text-[#6a737d] hover:text-[#ce9178]"
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
                background: isPostingFinalized ? '#22c55e10' : '#f59e0b10',
                borderColor: isPostingFinalized ? '#22c55e' : '#f59e0b',
              }}
            >
              <p className="text-sm font-medium" style={{ color: isPostingFinalized ? '#22c55e' : '#f59e0b' }}>
                {isPostingFinalized ? 'Drop resumes here to add candidates' : 'Finalize the posting first before adding resumes'}
              </p>
            </div>
          )}
          {messages.length === 0 && (
            <div className="flex items-center justify-center h-full text-sm" style={{ color: '#6a737d' }}>
              {project?.project_type === 'recruiting'
                ? (isPostingFinalized
                    ? 'Posting finalized. Drop resumes to add candidates.'
                    : 'Describe the role you\'re hiring for, then click "Add to Project" to build the posting.')
                : 'Start chatting \u2014 use "Add to Project" to build your document.'}
            </div>
          )}
          {messages.map((m) => (
            <MessageBubble
              key={m.id}
              message={m}
              isProjectThread
              onAddToProject={(msgId, content) => handleAddToProject(msgId, content)}
            />
          ))}
          {streaming && (
            <div className="flex justify-start">
              <div className="rounded-lg px-4 py-2.5 flex items-center gap-2" style={{ background: '#252526', border: '1px solid #333' }}>
                <Loader2 size={14} className="animate-spin" style={{ color: '#6a737d' }} />
                <span className="text-sm" style={{ color: '#6a737d' }}>{statusMessage || 'Thinking...'}</span>
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
        <div className="px-4 py-3" style={{ borderTop: '1px solid #333' }}>
          <div className="flex items-end gap-2">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
              placeholder="Type a message..."
              rows={1}
              disabled={streaming || (!activeChatId && pendingPlaceholders.current.length === 0)}
              className="flex-1 text-sm rounded-lg px-3 py-2.5 border focus:outline-none resize-none disabled:opacity-50 min-h-[44px]"
              style={{ background: '#1a1a1a', color: '#d4d4d4', borderColor: '#555' }}
            />
            <button
              onClick={handleSend}
              disabled={streaming || !input.trim() || (!activeChatId && pendingPlaceholders.current.length === 0)}
              className="p-3 rounded-lg transition-colors disabled:opacity-40"
              style={{ background: '#22c55e', color: '#fff' }}
            >
              {streaming ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            </button>
          </div>
        </div>
      </div>
      )}

      {/* Right — Project panel or Recruiting pipeline */}
      <div className={`${mobileView === 'panel' ? 'flex w-full' : 'hidden'} md:flex flex-1 min-w-0`}>
        {project.project_type === 'recruiting' ? (
          <RecruitingPipeline
            project={project}
            projectId={projectId!}
            onUpdate={(updated) => setProject(updated)}
            streaming={streaming}
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
          />
        )}
      </div>
    </div>
  )
}
