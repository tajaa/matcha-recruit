import { useEffect, useState } from 'react'
import { Loader2, SlidersHorizontal, Sparkles } from 'lucide-react'
import { ensureAssistantChannel } from '../api/matchaWork/assistant'
import AssistantAbilities from '../components/assistant/AssistantAbilities'
import { useEntitlements } from '../hooks/useEntitlements'
import { useMe } from '../../hooks/useMe'
import { apiErrorText } from '../utils/apiErrorText'
import MessageComposer from './ChannelView/MessageComposer'
import MessageList from './ChannelView/MessageList'
import { useChannelView } from './ChannelView/useChannelView'

/**
 * A person's private conversation with Espresso. It is a channel underneath,
 * so messages, cards and quick replies are the chat's own; what is left out
 * is everything about other people (members, invites, calls), because there
 * are none here. Every message is addressed to Espresso: no mention needed.
 */

function Conversation({ channelId }: { channelId: string }) {
  const [showAbilities, setShowAbilities] = useState(false)
  const { quotas } = useEntitlements()
  const view = useChannelView(channelId, true)
  const runs = quotas?.assistant_runs

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
          <Sparkles size={16} className="text-w-accent" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-w-text">Espresso</p>
            <p className="truncate text-[11px] text-w-dim">
              Private to you. Ask it to look something up, or to do something for you.
              {runs ? ` ${runs.remaining} of ${runs.limit} requests left today.` : ''}
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowAbilities((v) => !v)}
            aria-pressed={showAbilities}
            className="inline-flex items-center gap-1.5 rounded-lg border border-w-line px-2.5 py-1.5 text-xs font-semibold text-w-text hover:bg-w-surface2"
          >
            <SlidersHorizontal size={13} /> What it can do
          </button>
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
      {showAbilities && <AssistantAbilities onClose={() => setShowAbilities(false)} />}
    </div>
  )
}

export default function Assistant() {
  const { isPersonal } = useMe()
  if (!isPersonal) {
    return (
      <p className="p-6 text-sm text-w-dim">
        The Espresso assistant comes with a personal Espresso account.
      </p>
    )
  }
  return <PersonalAssistant />
}

function PersonalAssistant() {
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
  return <Conversation channelId={channelId} />
}
