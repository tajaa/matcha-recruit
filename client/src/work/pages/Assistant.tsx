import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { Loader2, Maximize2, PanelLeft, SlidersHorizontal, Sparkles, X } from 'lucide-react'
import { ensureAssistantChannel } from '../api/matchaWork/assistant'
import AssistantAbilities from '../components/assistant/AssistantAbilities'
import AssistantSessions from '../components/assistant/AssistantSessions'
import { useAssistantSessions } from '../hooks/useAssistantSessions'
import { useEntitlements } from '../hooks/useEntitlements'
import { useMe } from '../../hooks/useMe'
import { apiErrorText } from '../utils/apiErrorText'
import MessageComposer from './ChannelView/MessageComposer'
import MessageList from './ChannelView/MessageList'
import { useChannelView } from './ChannelView/useChannelView'
import { useWorkBase } from '../routes/WorkSurfaceContext'

/** Something typed outside the conversation (Home's "Ask Espresso") to send
 *  into it. `id` changes per ask, so the same words can be asked twice. */
export type AssistantAsk = { id: number; text: string }

/** Navigation state that opens the conversation with words already in its
 *  composer, for the person to finish and send (Job search's Ask Espresso). */
export type AssistantDraftState = { draft: AssistantAsk }

/**
 * A person's private conversation with Espresso. It is a channel underneath,
 * so messages, cards and quick replies are the chat's own; what is left out
 * is everything about other people (members, invites, calls), because there
 * are none here. Every message is addressed to Espresso: no mention needed.
 */

function Conversation({ channelId, ask, draft, onClose, title, onShowSessions }: {
  channelId: string
  ask?: AssistantAsk | null
  /** Words to put in the composer, unsent. */
  draft?: AssistantAsk | null
  /** Set when shown as Home's side panel: a close button and a way to the full page. */
  onClose?: () => void
  /** The session's name, for the header. */
  title?: string
  /** Set on a narrow screen, where the session list is behind a button. */
  onShowSessions?: () => void
}) {
  const [showAbilities, setShowAbilities] = useState(false)
  const { quotas } = useEntitlements()
  const base = useWorkBase()
  const view = useChannelView(channelId, true)
  const runs = quotas?.assistant_runs
  const compact = !!onClose
  // Each ask is sent once, after the conversation has loaded (StrictMode runs
  // effects twice; the ref keeps it to one send).
  const sentAsk = useRef<number | null>(null)
  const placedDraft = useRef<number | null>(null)
  const { loading, sendText, setInput, inputTextareaRef } = view

  useEffect(() => {
    if (loading || !ask || sentAsk.current === ask.id) return
    sentAsk.current = ask.id
    sendText(ask.text)
  }, [loading, ask, sendText])

  // A draft goes in once, with the caret at its end for the person's own words.
  useEffect(() => {
    if (loading || !draft || placedDraft.current === draft.id) return
    placedDraft.current = draft.id
    setInput(draft.text)
    requestAnimationFrame(() => {
      const box = inputTextareaRef.current
      if (!box) return
      box.focus()
      box.setSelectionRange(draft.text.length, draft.text.length)
    })
  }, [loading, draft, setInput, inputTextareaRef])

  if (view.loading) {
    return <div className="flex h-full items-center justify-center"><Loader2 className="animate-spin text-w-dim" /></div>
  }
  if (view.error) {
    return <p role="alert" className="p-6 text-sm text-red-400">{view.error}</p>
  }
  return (
    <div className="flex h-full min-h-0">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-2 border-b border-w-line px-4 py-3">
          {onShowSessions ? (
            <button type="button" onClick={onShowSessions} aria-label="Show sessions"
              className="rounded-md p-1 text-w-dim hover:bg-w-surface2 hover:text-w-text md:hidden">
              <PanelLeft size={16} />
            </button>
          ) : null}
          <Sparkles size={16} className={`text-w-accent ${onShowSessions ? 'hidden md:block' : ''}`} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-w-text">{title ?? 'Espresso'}</p>
            <p className="truncate text-[11px] text-w-dim">
              {compact ? 'Private to you.' : 'Private to you. Ask it to look something up, or to do something for you.'}
              {runs ? ` ${runs.remaining} of ${runs.limit} requests left today.` : ''}
            </p>
          </div>
          {compact ? (
            <>
              <Link
                to={`${base}/assistant/${encodeURIComponent(channelId)}`}
                aria-label="Open the full conversation"
                title="Open the full conversation"
                className="rounded-md p-1.5 text-w-dim hover:bg-w-surface2 hover:text-w-text"
              >
                <Maximize2 size={14} />
              </Link>
              <button
                type="button"
                onClick={onClose}
                aria-label="Close Espresso"
                className="rounded-md p-1.5 text-w-dim hover:bg-w-surface2 hover:text-w-text"
              >
                <X size={15} />
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={() => setShowAbilities((v) => !v)}
              aria-pressed={showAbilities}
              className="inline-flex items-center gap-1.5 rounded-lg border border-w-line px-2.5 py-1.5 text-xs font-semibold text-w-text hover:bg-w-surface2"
            >
              <SlidersHorizontal size={13} /> What it can do
            </button>
          )}
        </header>
        <MessageList
          messages={view.messages}
          messagesContainerRef={view.messagesContainerRef}
          messagesEndRef={view.messagesEndRef}
          userId={view.userId}
          canModerate={false}
          members={view.channel?.members ?? []}
          onDelete={view.handleDeleteMessage}
          onReply={view.handleReply}
          onQuickReply={view.handleQuickReply}
          onRetry={view.handleRetryMessage}
          onLoadOlder={view.loadOlder}
          hasMore={view.hasMore}
          loadingOlder={view.loadingOlder}
        />
        <MessageComposer
          pendingFiles={view.pendingFiles}
          setPendingFiles={view.setPendingFiles}
          fileInputRef={view.fileInputRef}
          mentionQuery={null}
          mentionMatches={[]}
          applyMention={view.applyMention}
          inputTextareaRef={view.inputTextareaRef}
          input={view.input}
          onInputChange={view.handleInputChange}
          onKeyDown={view.handleKeyDown}
          channelName="Espresso"
          onSend={view.handleSend}
          uploading={view.uploading}
          replyTo={view.replyTo}
          onClearReply={() => view.setReplyTo(null)}
        />
      </div>
      {showAbilities && !compact && <AssistantAbilities onClose={() => setShowAbilities(false)} />}
    </div>
  )
}

export default function Assistant() {
  const { isPersonal } = useMe()
  const location = useLocation()
  const navigate = useNavigate()
  // Read once, then dropped from history so a reload doesn't put it back.
  const [draft] = useState(() => (location.state as Partial<AssistantDraftState> | null)?.draft ?? null)
  useEffect(() => {
    if (draft) navigate(location.pathname, { replace: true, state: null })
  }, [draft, navigate, location.pathname])
  if (!isPersonal) {
    return (
      <p className="p-6 text-sm text-w-dim">
        The Espresso assistant comes with a personal Espresso account.
      </p>
    )
  }
  return <SessionsPage draft={draft} />
}

const sessionKey = (userId: string) => `espresso.assistant.session:${userId}`

function rememberedSession(userId: string): string | null {
  try { return localStorage.getItem(sessionKey(userId)) } catch { return null }
}

/** The full page: the person's sessions on the left, the open one beside
 *  them. The open session is in the URL (`/assistant/:conversationId`), so a
 *  link or a reload lands on it; without one, the last session opened here,
 *  else the most recent, else the main conversation. */
function SessionsPage({ draft }: { draft: AssistantAsk | null }) {
  const { conversationId } = useParams<{ conversationId?: string }>()
  const { me } = useMe()
  const userId = me?.user.id
  const base = useWorkBase()
  const navigate = useNavigate()
  const sessions = useAssistantSessions()
  const [railOpen, setRailOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // A draft belongs to the session the page opened with, not to one switched to after.
  const [draftFor, setDraftFor] = useState<string | null>(null)
  if (draft && conversationId && draftFor === null) setDraftFor(conversationId)

  const path = (id: string) => `${base}/assistant/${encodeURIComponent(id)}`
  const open = (id: string) => {
    setRailOpen(false)
    navigate(path(id))
  }

  // No session in the URL: pick one once the list is in.
  useEffect(() => {
    if (conversationId || !sessions.loaded || !userId) return
    const saved = rememberedSession(userId)
    const pick = sessions.sessions.find((c) => c.id === saved) ?? sessions.sessions[0]
    if (pick) { navigate(path(pick.id), { replace: true }); return }
    let cancelled = false
    ensureAssistantChannel()
      .then((out) => { if (!cancelled) navigate(path(out.channel_id), { replace: true }) })
      .catch((e: unknown) => { if (!cancelled) setError(apiErrorText(e, "Couldn't open your conversation with Espresso.")) })
    return () => { cancelled = true }
    // `path` is rebuilt each render; the inputs that matter are listed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId, sessions.loaded, sessions.sessions, userId])

  useEffect(() => {
    if (!conversationId || !userId) return
    try { localStorage.setItem(sessionKey(userId), conversationId) } catch { /* storage may be off */ }
  }, [conversationId, userId])

  const current = [...sessions.sessions, ...(sessions.archived ?? [])].find((c) => c.id === conversationId)
  const rail = (onClose?: () => void) => (
    <AssistantSessions sessions={sessions} activeId={conversationId ?? null} onSelect={(id) => open(id)} onClose={onClose} />
  )

  return (
    <div className="relative flex h-full min-h-0">
      <div className="hidden md:flex">{rail()}</div>
      {railOpen && (
        <div className="absolute inset-0 z-20 flex md:hidden">
          <div className="w-72 max-w-[85%] border-r border-w-line shadow-xl">{rail(() => setRailOpen(false))}</div>
          <button type="button" aria-label="Close sessions" className="flex-1 bg-black/40" onClick={() => setRailOpen(false)} />
        </div>
      )}
      <div className="min-w-0 flex-1">
        {error ? (
          <p role="alert" className="p-6 text-sm text-red-400">{error}</p>
        ) : conversationId ? (
          <Conversation
            key={conversationId}
            channelId={conversationId}
            draft={conversationId === draftFor ? draft : null}
            title={current ? `${current.title}${current.archived ? ' (archived)' : ''}` : undefined}
            onShowSessions={() => setRailOpen(true)}
          />
        ) : (
          <div className="flex h-full items-center justify-center"><Loader2 className="animate-spin text-w-dim" /></div>
        )}
      </div>
    </div>
  )
}

/** The person's main conversation with Espresso, as the panel that slides in
 *  on Home when they ask from there. Asks always go to the main session; the
 *  panel's expand button opens it on the full page. */
export function AssistantConversation({ ask, draft, onClose }: {
  ask?: AssistantAsk | null
  draft?: AssistantAsk | null
  onClose?: () => void
} = {}) {
  const [channelId, setChannelId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    ensureAssistantChannel()
      .then((out) => { if (!cancelled) setChannelId(out.channel_id) })
      .catch((e: unknown) => {
        if (!cancelled) setError(apiErrorText(e, "Couldn't open your conversation with Espresso."))
      })
    return () => { cancelled = true }
  }, [])

  if (error) return <p role="alert" className="p-6 text-sm text-red-400">{error}</p>
  if (!channelId) {
    return <div className="flex h-full items-center justify-center"><Loader2 className="animate-spin text-w-dim" /></div>
  }
  return <Conversation channelId={channelId} ask={ask} draft={draft} onClose={onClose} />
}
