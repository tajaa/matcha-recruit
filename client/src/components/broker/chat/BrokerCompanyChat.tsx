import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Loader2, Plus, Send, Paperclip, X, MessageSquare, FileText,
  ShieldAlert, ClipboardList, Archive, ArchiveRestore,
} from 'lucide-react'
import { Button, Modal, Input, Textarea, Select, useToast } from '../../ui'
import type { BrokerChatAdapter } from './adapter'
import type {
  ChatMessage, ChatReferenceType, ChatTarget, Conversation, MessageReference,
} from '../../../types/brokerChat'

const REFERENCE_TYPES: { value: ChatReferenceType; label: string }[] = [
  { value: 'general', label: 'General' },
  { value: 'claim', label: 'Claim' },
  { value: 'loss_run', label: 'Loss run' },
  { value: 'document', label: 'Document' },
  { value: 'flagged_data', label: 'Flagged data' },
  { value: 'incident', label: 'Incident' },
  { value: 'submission', label: 'Submission' },
  { value: 'policy', label: 'Policy' },
]

function referenceIcon(type: ChatReferenceType) {
  switch (type) {
    case 'claim':
    case 'loss_run':
      return ClipboardList
    case 'flagged_data':
      return ShieldAlert
    case 'incident':
      return ShieldAlert
    default:
      return FileText
  }
}

function ReferenceChip({ reference }: { reference: MessageReference }) {
  const Icon = referenceIcon(reference.type)
  const typeLabel = REFERENCE_TYPES.find((t) => t.value === reference.type)?.label ?? reference.type
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md border border-emerald-800/60 bg-emerald-950/40 px-2 py-1 text-xs text-emerald-300">
      <Icon className="h-3.5 w-3.5 shrink-0" />
      <span className="font-medium">{typeLabel}:</span>
      <span className="truncate max-w-[16rem]">{reference.label}</span>
    </span>
  )
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  if (sameDay) return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  return d.toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function conversationTitle(c: Conversation, side: 'broker' | 'company'): string {
  if (c.subject) return c.subject
  return side === 'broker' ? (c.company_name || 'Client') : (c.broker_name || 'Broker')
}

// The 5s poll re-fetches the same rows almost every time. Comparing identity
// before committing keeps React (and the auto-scroll effect below) from seeing a
// change that isn't one.
function sameMessages(a: ChatMessage[], b: ChatMessage[]): boolean {
  if (a.length !== b.length) return false
  return a.every((m, i) => m.id === b[i].id && m.edited_at === b[i].edited_at && m.body === b[i].body)
}

export default function BrokerCompanyChat({ adapter }: { adapter: BrokerChatAdapter }) {
  const { toast } = useToast()
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [loadingConvs, setLoadingConvs] = useState(true)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loadingMsgs, setLoadingMsgs] = useState(false)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [composerRef, setComposerRef] = useState<MessageReference | null>(null)
  const [showNew, setShowNew] = useState(false)
  const [showArchived, setShowArchived] = useState(false)

  const selectedIdRef = useRef<string | null>(null)
  selectedIdRef.current = selectedId
  const scrollRef = useRef<HTMLDivElement | null>(null)
  // Only auto-scroll when the reader is already at the bottom — otherwise the
  // poll yanks someone reading history back down every few seconds.
  const atBottomRef = useRef(true)
  // Newest message already acknowledged, so an idle open thread stops re-PUTting
  // /read on every poll tick.
  const lastReadIdRef = useRef<string | null>(null)

  const selected = useMemo(
    () => conversations.find((c) => c.id === selectedId) || null,
    [conversations, selectedId],
  )

  const loadConversations = useCallback(async () => {
    try {
      const res = await adapter.listConversations(showArchived)
      setConversations(res.conversations)
    } catch {
      // best-effort; a transient list refresh failure is non-fatal
    } finally {
      setLoadingConvs(false)
    }
  }, [adapter, showArchived])

  const markConversationRead = useCallback(
    async (conversationId: string, lastMessageId?: string) => {
      try {
        await adapter.markRead(conversationId, lastMessageId)
        setConversations((prev) =>
          prev.map((c) => (c.id === conversationId ? { ...c, unread_count: 0 } : c)),
        )
      } catch {
        // Leave the watermark unacknowledged so the next poll retries it.
        lastReadIdRef.current = null
      }
    },
    [adapter],
  )

  const loadMessages = useCallback(
    async (conversationId: string, opts: { showSpinner?: boolean } = {}) => {
      if (opts.showSpinner) setLoadingMsgs(true)
      try {
        const msgs = await adapter.getMessages(conversationId)
        // Only apply if the user hasn't switched conversations mid-request.
        if (selectedIdRef.current !== conversationId) return
        setMessages((prev) => {
          // Keep optimistic sends the server hasn't echoed back yet.
          const pending = prev.filter(
            (m) =>
              m.id.startsWith('pending-') &&
              !msgs.some((s) => s.client_message_id && s.client_message_id === m.client_message_id),
          )
          const next = pending.length ? [...msgs, ...pending] : msgs
          return sameMessages(prev, next) ? prev : next
        })
        const last = msgs[msgs.length - 1]
        if (last && lastReadIdRef.current !== last.id) {
          lastReadIdRef.current = last.id
          markConversationRead(conversationId, last.id)
        }
      } catch {
        /* non-fatal — polling will retry */
      } finally {
        if (opts.showSpinner) setLoadingMsgs(false)
      }
    },
    [adapter, markConversationRead],
  )

  // Initial conversation load.
  useEffect(() => {
    loadConversations()
  }, [loadConversations])

  // Poll the conversation list for unread/new-thread changes.
  useEffect(() => {
    const id = setInterval(loadConversations, 15000)
    return () => clearInterval(id)
  }, [loadConversations])

  // Load + poll messages for the selected conversation.
  useEffect(() => {
    if (!selectedId) {
      setMessages([])
      return
    }
    // A newly-opened thread starts pinned to the newest message.
    atBottomRef.current = true
    lastReadIdRef.current = null
    loadMessages(selectedId, { showSpinner: true })
    const id = setInterval(() => loadMessages(selectedId), 5000)
    return () => clearInterval(id)
  }, [selectedId, loadMessages])

  // Follow the newest message only while the reader is already at the bottom.
  useEffect(() => {
    const el = scrollRef.current
    if (el && atBottomRef.current) el.scrollTop = el.scrollHeight
  }, [messages])

  const handleSend = useCallback(async () => {
    const trimmed = input.trim()
    if (!trimmed || !selectedId || sending) return
    // The server requires a non-empty reference label (MessageReference.label is
    // min_length=1), so an attached-but-unlabelled reference 422s the whole send.
    // Same guard the new-conversation modal already has.
    if (composerRef && !composerRef.label.trim()) {
      toast('Reference needs a label', 'error')
      return
    }
    setSending(true)
    // Own message: follow it down even if the reader had scrolled up.
    atBottomRef.current = true
    const cmid = crypto.randomUUID()
    const reference = composerRef
    // Optimistic append.
    const optimistic: ChatMessage = {
      id: `pending-${cmid}`,
      conversation_id: selectedId,
      sender_user_id: 'me',
      sender_side: adapter.side,
      sender_name: 'You',
      body: trimmed,
      reference: reference,
      client_message_id: cmid,
      created_at: new Date().toISOString(),
      edited_at: null,
    }
    setMessages((prev) => [...prev, optimistic])
    setInput('')
    setComposerRef(null)
    try {
      const saved = await adapter.sendMessage(selectedId, {
        body: trimmed,
        reference,
        client_message_id: cmid,
      })
      setMessages((prev) => prev.map((m) => (m.client_message_id === cmid ? saved : m)))
      loadConversations()
    } catch {
      // Roll the optimistic message back and restore the draft.
      setMessages((prev) => prev.filter((m) => m.client_message_id !== cmid))
      setInput(trimmed)
      setComposerRef(reference)
      toast('Message failed to send', 'error')
    } finally {
      setSending(false)
    }
  }, [input, selectedId, sending, composerRef, adapter, loadConversations, toast])

  const handleArchive = useCallback(async () => {
    if (!selected || !adapter.archive) return
    try {
      await adapter.archive(selected.id, selected.status !== 'archived')
      await loadConversations()
    } catch {
      toast('Could not update the conversation', 'error')
    }
  }, [selected, adapter, loadConversations, toast])

  return (
    <div className="flex h-[calc(100vh-8rem)] min-h-[32rem] overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950">
      {/* Conversation list */}
      <aside className="flex w-72 shrink-0 flex-col border-r border-zinc-800">
        <div className="border-b border-zinc-800 px-4 py-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-zinc-200">Messages</h2>
            <Button size="sm" onClick={() => setShowNew(true)} className="!px-2 !py-1">
              <Plus className="h-4 w-4" />
              New
            </Button>
          </div>
          {/* Archive status is shared between the two sides, so both need a way
              back to an archived thread — not just whoever archived it. */}
          <label className="mt-2 flex cursor-pointer items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(e) => setShowArchived(e.target.checked)}
              className="h-3 w-3 accent-emerald-600"
            />
            Show archived
          </label>
        </div>
        <div className="flex-1 overflow-y-auto">
          {loadingConvs ? (
            <div className="flex items-center justify-center py-10 text-zinc-500">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
          ) : conversations.length === 0 ? (
            <div className="px-4 py-10 text-center text-sm text-zinc-500">
              No conversations yet.
            </div>
          ) : (
            conversations.map((c) => (
              <button
                key={c.id}
                onClick={() => setSelectedId(c.id)}
                className={`flex w-full flex-col gap-1 border-b border-zinc-900 px-4 py-3 text-left transition-colors hover:bg-zinc-900 ${
                  selectedId === c.id ? 'bg-zinc-900' : ''
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium text-zinc-200">
                    {conversationTitle(c, adapter.side)}
                  </span>
                  {c.unread_count > 0 && (
                    <span className="ml-auto inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-emerald-600 px-1.5 text-xs font-semibold text-white">
                      {c.unread_count}
                    </span>
                  )}
                </div>
                <span className="truncate text-xs text-zinc-500">
                  {c.status === 'archived' ? '(archived) ' : ''}
                  {c.last_message_preview || 'No messages yet'}
                </span>
              </button>
            ))
          )}
        </div>
      </aside>

      {/* Thread */}
      <section className="flex min-w-0 flex-1 flex-col">
        {!selected ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 text-zinc-500">
            <MessageSquare className="h-8 w-8" />
            <p className="text-sm">Select a conversation to start messaging.</p>
          </div>
        ) : (
          <>
            <header className="flex items-center justify-between gap-2 border-b border-zinc-800 px-5 py-3">
              <div className="min-w-0">
                <h3 className="truncate text-sm font-semibold text-zinc-100">
                  {conversationTitle(selected, adapter.side)}
                </h3>
                <p className="truncate text-xs text-zinc-500">
                  {adapter.side === 'broker' ? selected.company_name : selected.broker_name}
                  {selected.reference ? ` · ${selected.reference.label}` : ''}
                </p>
              </div>
              {adapter.archive && (
                <Button variant="ghost" size="sm" onClick={handleArchive}>
                  {selected.status === 'archived' ? (
                    <><ArchiveRestore className="h-4 w-4" /> Unarchive</>
                  ) : (
                    <><Archive className="h-4 w-4" /> Archive</>
                  )}
                </Button>
              )}
            </header>

            <div
              ref={scrollRef}
              onScroll={(e) => {
                const el = e.currentTarget
                atBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
              }}
              className="flex-1 space-y-3 overflow-y-auto px-5 py-4"
            >
              {loadingMsgs ? (
                <div className="flex items-center justify-center py-10 text-zinc-500">
                  <Loader2 className="h-5 w-5 animate-spin" />
                </div>
              ) : messages.length === 0 ? (
                <div className="py-10 text-center text-sm text-zinc-500">
                  No messages yet. Say hello.
                </div>
              ) : (
                messages.map((m) => {
                  const mine = m.sender_side === adapter.side
                  return (
                    <div
                      key={m.id}
                      className={`flex flex-col ${mine ? 'items-end' : 'items-start'}`}
                    >
                      <div
                        className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm ${
                          mine
                            ? 'bg-emerald-700 text-white'
                            : 'bg-zinc-800 text-zinc-100'
                        }`}
                      >
                        {!mine && (
                          <div className="mb-0.5 text-xs font-medium text-zinc-400">
                            {m.sender_name}
                          </div>
                        )}
                        {m.reference && (
                          <div className="mb-1.5">
                            <ReferenceChip reference={m.reference} />
                          </div>
                        )}
                        <div className="whitespace-pre-wrap break-words">{m.body}</div>
                      </div>
                      <span className="mt-0.5 px-1 text-[11px] text-zinc-600">
                        {formatTime(m.created_at)}
                        {m.edited_at ? ' · edited' : ''}
                      </span>
                    </div>
                  )
                })
              )}
            </div>

            {/* Composer */}
            <div className="border-t border-zinc-800 px-4 py-3">
              {composerRef && (
                <div className="mb-2 flex items-center gap-2">
                  <ReferenceChip reference={composerRef} />
                  <button
                    onClick={() => setComposerRef(null)}
                    className="text-zinc-500 hover:text-zinc-300"
                    aria-label="Remove reference"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              )}
              <div className="flex items-end gap-2">
                <button
                  onClick={() => setComposerRef(composerRef ? null : { type: 'general', label: '' })}
                  className="mb-1 shrink-0 text-zinc-500 hover:text-emerald-400"
                  title="Attach a reference (claim, document, …)"
                  aria-label="Attach reference"
                >
                  <Paperclip className="h-5 w-5" />
                </button>
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      handleSend()
                    }
                  }}
                  rows={1}
                  placeholder="Write a message…"
                  className="max-h-32 min-h-[2.5rem] flex-1 resize-none rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 focus:border-emerald-600 focus:outline-none"
                />
                <Button
                  onClick={handleSend}
                  disabled={!input.trim() || sending}
                  className="mb-0.5 !px-3"
                >
                  {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                </Button>
              </div>
              {composerRef && (
                <ReferenceEditor value={composerRef} onChange={setComposerRef} />
              )}
            </div>
          </>
        )}
      </section>

      {showNew && (
        <NewConversationModal
          adapter={adapter}
          onClose={() => setShowNew(false)}
          onCreated={async (conv) => {
            setShowNew(false)
            await loadConversations()
            setSelectedId(conv.id)
          }}
        />
      )}
    </div>
  )
}

function ReferenceEditor({
  value,
  onChange,
}: {
  value: MessageReference
  onChange: (r: MessageReference) => void
}) {
  return (
    <div className="mt-2 flex gap-2">
      <Select
        value={value.type}
        onChange={(e) => onChange({ ...value, type: e.target.value as ChatReferenceType })}
        options={REFERENCE_TYPES}
        className="w-40"
      />
      <Input
        value={value.label}
        onChange={(e) => onChange({ ...value, label: e.target.value })}
        placeholder="Reference label (e.g. Claim #10432)"
        className="flex-1"
      />
    </div>
  )
}

function NewConversationModal({
  adapter,
  onClose,
  onCreated,
}: {
  adapter: BrokerChatAdapter
  onClose: () => void
  onCreated: (conv: Conversation) => void
}) {
  const { toast } = useToast()
  const [targets, setTargets] = useState<ChatTarget[]>([])
  const [loadingTargets, setLoadingTargets] = useState(true)
  const [targetId, setTargetId] = useState<string>('')
  const [subject, setSubject] = useState('')
  const [firstMessage, setFirstMessage] = useState('')
  const [reference, setReference] = useState<MessageReference | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    adapter
      .listTargets()
      .then((t) => {
        setTargets(t)
        if (t.length === 1) setTargetId(t[0].id)
      })
      .catch(() => setTargets([]))
      .finally(() => setLoadingTargets(false))
  }, [adapter])

  const needsTarget = targets.length !== 1

  const submit = async () => {
    if (needsTarget && !targetId) {
      toast(`Pick a ${adapter.targetNoun} first`, 'error')
      return
    }
    if (reference && !reference.label.trim()) {
      toast('Reference needs a label', 'error')
      return
    }
    setSaving(true)
    try {
      const conv = await adapter.createConversation({
        targetId: targetId || targets[0]?.id,
        subject: subject.trim() || null,
        reference: reference && reference.label.trim() ? reference : null,
        body: firstMessage.trim() || null,
      })
      onCreated(conv)
    } catch {
      toast('Could not start the conversation', 'error')
      setSaving(false)
    }
  }

  return (
    <Modal open onClose={onClose} title="New conversation" width="md">
      {loadingTargets ? (
        <div className="flex items-center justify-center py-8 text-zinc-500">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      ) : targets.length === 0 ? (
        <p className="py-6 text-sm text-zinc-400">
          No {adapter.targetNoun} is available to message right now.
        </p>
      ) : (
        <div className="space-y-4">
          {needsTarget && (
            <div>
              <label className="mb-1 block text-xs font-medium text-zinc-400 capitalize">
                {adapter.targetNoun}
              </label>
              <Select
                value={targetId}
                onChange={(e) => setTargetId(e.target.value)}
                options={targets.map((t) => ({ value: t.id, label: t.name }))}
                placeholder="Select…"
                className="w-full"
              />
            </div>
          )}
          <Input
            label="Subject (optional)"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="e.g. Q3 loss run questions"
          />
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-400">
              Reference (optional)
            </label>
            {reference ? (
              <ReferenceEditor value={reference} onChange={setReference} />
            ) : (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setReference({ type: 'general', label: '' })}
              >
                <Paperclip className="h-4 w-4" /> Attach a claim or document
              </Button>
            )}
          </div>
          <Textarea
            label="First message (optional)"
            value={firstMessage}
            onChange={(e) => setFirstMessage(e.target.value)}
            rows={3}
            placeholder="Write your message…"
          />
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={onClose}>Cancel</Button>
            <Button onClick={submit} disabled={saving}>
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Start conversation
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )
}
