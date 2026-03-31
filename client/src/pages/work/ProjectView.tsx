import { useEffect, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Send, Loader2, Plus, MessageSquare, ChevronRight, FileText, Users, Video, Star, HelpCircle } from 'lucide-react'
import type { MWMessage, MWThreadDetail, MWSendResponse, MWStreamEvent, MWProject } from '../../types/matcha-work'
import { getProjectDetail, getThread, sendMessageStream, createProjectChat, addProjectSectionNew, uploadProjectResumes, sendProjectInterviews, syncProjectInterviews } from '../../api/matchaWork'
import MessageBubble from '../../components/matcha-work/MessageBubble'
import ProjectPanel from '../../components/matcha-work/ProjectPanel'
import RecruitingPipeline from '../../components/matcha-work/RecruitingPipeline'

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

  // Recruiting wizard + drag-and-drop
  const [showWizard, setShowWizard] = useState(false)
  const [wizardStep, setWizardStep] = useState(0)
  const [isDragOver, setIsDragOver] = useState(false)

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

  function handleSend() {
    const content = input.trim()
    if (!activeChatId || !content || streaming) return
    setInput('')
    setStreaming(true)
    setError('')

    const tempMsg: MWMessage = {
      id: crypto.randomUUID(),
      thread_id: activeChatId,
      role: 'user',
      content,
      metadata: null,
      version_created: null,
      created_at: new Date().toISOString(),
    }
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
      },
      onError: (err) => {
        setStatusMessage('')
        setError(err)
        setStreaming(false)
      },
    })
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
    } catch {}
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
      <div className="hidden sm:flex flex-col w-[130px] shrink-0" style={{ borderRight: '1px solid #333', background: '#252526' }}>
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

        <div className="flex-1 overflow-y-auto py-1">
          {chats.map((c) => (
            <button
              key={c.id}
              onClick={() => setActiveChatId(c.id)}
              className={`w-full text-left px-3 py-2 text-xs truncate transition-colors ${
                activeChatId === c.id
                  ? 'text-[#e8e8e8]'
                  : 'text-[#6a737d] hover:text-[#d4d4d4]'
              }`}
              style={activeChatId === c.id ? { background: '#2a2d2e' } : {}}
            >
              <MessageSquare size={10} className="inline mr-1.5" />
              {c.title}
            </button>
          ))}
        </div>
      </div>

      {/* Center — chat messages */}
      <div className="flex-1 flex flex-col min-w-0" style={{ borderRight: '1px solid #333' }}>
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
          {project.project_type === 'recruiting' && (
            <button
              onClick={() => { setWizardStep(0); setShowWizard(true) }}
              title="How it works"
              className="ml-auto p-1 rounded transition-colors text-[#6a737d] hover:text-[#ce9178]"
            >
              <HelpCircle size={14} />
            </button>
          )}
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
              disabled={streaming || !activeChatId}
              className="flex-1 text-sm rounded-lg px-3 py-2.5 border focus:outline-none resize-none disabled:opacity-50 min-h-[44px]"
              style={{ background: '#1a1a1a', color: '#d4d4d4', borderColor: '#555' }}
            />
            <button
              onClick={handleSend}
              disabled={streaming || !input.trim() || !activeChatId}
              className="p-3 rounded-lg transition-colors disabled:opacity-40"
              style={{ background: '#22c55e', color: '#fff' }}
            >
              {streaming ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            </button>
          </div>
        </div>
      </div>

      {/* Right — Project panel or Recruiting pipeline */}
      <div className="hidden md:flex md:w-1/2 shrink-0">
        {project.project_type === 'recruiting' ? (
          <RecruitingPipeline
            project={project}
            projectId={projectId!}
            onUpdate={(updated) => setProject(updated)}
            streaming={streaming}
            onSendInterviews={async (ids, positionTitle) => {
              const result = await sendProjectInterviews(projectId!, ids, positionTitle)
              if (result.sent.length > 0) {
                const updated = await getProjectDetail(projectId!)
                setProject(updated)
              }
              if (result.failed.length > 0) {
                setError(`Failed to send ${result.failed.length} interview(s): ${result.failed.map((f) => f.error).join(', ')}`)
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
            onPromptChat={(message) => {
              setInput(message)
              setTimeout(() => {
                const el = textareaRef.current
                if (el) {
                  el.focus()
                  el.style.height = 'auto'
                  el.style.height = el.scrollHeight + 'px'
                  // Place cursor at end
                  el.selectionStart = el.selectionEnd = el.value.length
                }
              }, 50)
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
