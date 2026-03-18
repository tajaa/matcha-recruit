import { useEffect, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import Markdown from 'react-markdown'
import { ArrowLeft, Send, Loader2, Pencil, Check, X, Database, Shield } from 'lucide-react'
import type { MWMessage, MWThreadDetail, MWSendResponse, MWStreamEvent } from '../../types/matcha-work'
import { getThread, sendMessageStream, updateTitle, getPdfProxyUrl, setNodeMode, setComplianceMode } from '../../api/matchaWork'

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
  const [error, setError] = useState('')
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)

  // Node mode
  const [nodeMode, setNodeModeState] = useState(false)
  const [togglingNode, setTogglingNode] = useState(false)

  // Compliance mode
  const [complianceMode, setComplianceModeState] = useState(false)
  const [togglingCompliance, setTogglingCompliance] = useState(false)

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
        setNodeModeState(data.node_mode)
        setComplianceModeState(data.compliance_mode)
        // Check if there's already a PDF-worthy task type
        if (data.task_type === 'offer_letter' || data.task_type === 'presentation') {
          setPdfUrl(getPdfProxyUrl(threadId, data.version))
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load thread'))
      .finally(() => setLoading(false))

    return () => { abortRef.current?.abort() }
  }, [threadId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  function handleSend() {
    if (!threadId || !input.trim() || streaming) return

    const content = input.trim()
    setInput('')
    setStreaming(true)
    setError('')

    // Optimistically add user message
    const tempUserMsg: MWMessage = {
      id: crypto.randomUUID(),
      thread_id: threadId,
      role: 'user',
      content,
      version_created: null,
      created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, tempUserMsg])

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
        // Show PDF if returned
        if (data.pdf_url) {
          setPdfUrl(data.pdf_url)
        } else if (data.task_type === 'offer_letter' || data.task_type === 'presentation') {
          setPdfUrl(getPdfProxyUrl(threadId, data.version))
        }
        setStreaming(false)
      },
      onError: (err) => {
        setStatusMessage('')
        setError(err)
        setStreaming(false)
      },
    })
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

  async function handleNodeToggle() {
    if (!threadId || togglingNode) return
    const newVal = !nodeMode
    setTogglingNode(true)
    try {
      await setNodeMode(threadId, newVal)
      setNodeModeState(newVal)
    } catch {}
    setTogglingNode(false)
  }

  async function handleComplianceToggle() {
    if (!threadId || togglingCompliance) return
    const newVal = !complianceMode
    setTogglingCompliance(true)
    try {
      await setComplianceMode(threadId, newVal)
      setComplianceModeState(newVal)
    } catch {}
    setTogglingCompliance(false)
  }

  const isFinalized = thread?.status === 'finalized'
  const isArchived = thread?.status === 'archived'
  const inputDisabled = streaming || isFinalized || isArchived

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
    <div className="flex h-[calc(100vh-49px)]">
      {/* Chat panel */}
      <div className={`flex flex-col ${pdfUrl ? 'w-1/2' : 'w-full'} border-r border-zinc-800`}>
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-zinc-800">
          <Link to="/work" className="text-zinc-400 hover:text-white transition-colors">
            <ArrowLeft size={18} />
          </Link>

          {editingTitle ? (
            <div className="flex items-center gap-2 flex-1">
              <input
                value={titleDraft}
                onChange={(e) => setTitleDraft(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleTitleSave()}
                className="bg-zinc-800 text-white text-sm px-2 py-1 rounded border border-zinc-600 flex-1"
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
              <h2 className="text-white font-medium truncate">{thread?.title}</h2>
              <button
                onClick={() => {
                  setTitleDraft(thread?.title ?? '')
                  setEditingTitle(true)
                }}
                className="text-zinc-500 hover:text-white transition-colors shrink-0"
              >
                <Pencil size={14} />
              </button>
            </div>
          )}

          {thread?.task_type && (
            <span className="shrink-0 px-2 py-0.5 text-xs font-medium rounded-full bg-zinc-700 text-zinc-300">
              {TASK_LABELS[thread.task_type] ?? thread.task_type}
            </span>
          )}

          <button
            onClick={handleNodeToggle}
            disabled={togglingNode}
            title={nodeMode ? 'Node mode ON — AI uses internal company data' : 'Node mode OFF — click to enable internal data search'}
            className={`shrink-0 flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full transition-colors disabled:opacity-50 ${
              nodeMode
                ? 'bg-purple-600 text-white hover:bg-purple-500'
                : 'bg-zinc-700 text-zinc-400 hover:bg-zinc-600 hover:text-zinc-200'
            }`}
          >
            <Database size={12} />
            Node
          </button>

          <button
            onClick={handleComplianceToggle}
            disabled={togglingCompliance}
            title={complianceMode ? 'Compliance mode ON — AI uses jurisdiction requirements' : 'Compliance mode OFF — click to enable compliance context'}
            className={`shrink-0 flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full transition-colors disabled:opacity-50 ${
              complianceMode
                ? 'bg-cyan-600 text-white hover:bg-cyan-500'
                : 'bg-zinc-700 text-zinc-400 hover:bg-zinc-600 hover:text-zinc-200'
            }`}
          >
            <Shield size={12} />
            Compliance
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {messages.length === 0 && (
            <div className="flex items-center justify-center h-full text-zinc-500 text-sm">
              Start a conversation — ask about offer letters, reviews, handbooks, and more.
            </div>
          )}
          {messages.map((m) => (
            <div
              key={m.id}
              className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[80%] rounded-lg px-4 py-2.5 text-sm ${
                  m.role === 'user'
                    ? 'bg-zinc-700 text-white whitespace-pre-wrap'
                    : 'bg-zinc-800/60 text-zinc-200 border border-zinc-700/50 prose prose-sm prose-invert prose-zinc max-w-none'
                }`}
              >
                {m.role === 'assistant' ? (
                  <Markdown>{m.content}</Markdown>
                ) : (
                  m.content
                )}
              </div>
            </div>
          ))}

          {streaming && (
            <div className="flex justify-start">
              <div className="bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-4 py-2.5 flex items-center gap-2">
                <Loader2 size={14} className="animate-spin text-zinc-500" />
                <span className="text-sm text-zinc-400">{statusMessage || 'Thinking...'}</span>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Error */}
        {error && (
          <div className="mx-4 mb-2 p-2 bg-red-900/30 border border-red-800 rounded text-red-300 text-xs">
            {error}
          </div>
        )}

        {/* Input */}
        <div className="px-4 py-3 border-t border-zinc-800">
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
                className="flex-1 bg-zinc-800 text-white text-sm rounded-lg px-3 py-2.5 border border-zinc-700 focus:border-emerald-600 focus:outline-none resize-none disabled:opacity-50 placeholder-zinc-500"
              />
              <button
                onClick={handleSend}
                disabled={inputDisabled || !input.trim()}
                className="p-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg transition-colors disabled:opacity-40 disabled:hover:bg-emerald-600"
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

      {/* PDF preview panel */}
      {pdfUrl && (
        <div className="w-1/2 bg-zinc-900">
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
