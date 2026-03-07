import { useEffect, useRef } from 'preact/hooks'
import type { MessageItem } from '../hooks/useChat'
import { EmailCard } from './EmailCard'
import { renderMarkdown } from '../lib/markdown'

interface Props {
  messages: MessageItem[]
  loading: boolean
  onDraft: (emailId: string, instructions: string) => void
  onSchedule: (emailId: string) => void
  onQuickAction: (action: string) => void
}

export function ChatArea({
  messages,
  loading,
  onDraft,
  onSchedule,
  onQuickAction,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  if (messages.length === 0 && !loading) {
    return (
      <div class="chat-area">
        <div class="welcome">
          <div class="welcome-icon">&#x2618;</div>
          <h2>matcha-agent</h2>
          <p>
            Sandboxed assistant with Gmail, Calendar, and RSS. Type a message or
            use the toolbar above.
          </p>
          <div class="welcome-shortcuts">
            <button
              class="welcome-shortcut"
              onClick={() => onQuickAction('emails')}
            >
              check emails
            </button>
            <button
              class="welcome-shortcut"
              onClick={() => onQuickAction('briefing')}
            >
              briefing
            </button>
            <button
              class="welcome-shortcut"
              onClick={() => onQuickAction('help')}
            >
              what can you do?
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div class="chat-area">
      {messages.map((msg, i) => {
        switch (msg.type) {
          case 'user':
            return (
              <div key={i} class="msg user">
                {msg.content}
              </div>
            )
          case 'agent':
            return (
              <div
                key={i}
                class="msg agent"
                dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }}
              />
            )
          case 'system':
            return (
              <div key={i} class="msg system">
                {msg.content}
              </div>
            )
          case 'emails':
            return (
              <div key={i} class="email-list">
                <div class="msg system">
                  {msg.emails.length} unread email
                  {msg.emails.length > 1 ? 's' : ''}:
                </div>
                {msg.emails.map((email) => (
                  <EmailCard
                    key={email.id}
                    email={email}
                    onDraft={onDraft}
                    onSchedule={onSchedule}
                  />
                ))}
              </div>
            )
          case 'event': {
            const ev = msg.event as Record<string, string>
            return (
              <div
                key={i}
                class="msg agent"
                dangerouslySetInnerHTML={{
                  __html: renderMarkdown(
                    `**Event Created**\n\n- **${ev.summary}**\n- Start: ${ev.start}\n- End: ${ev.end}${ev.location ? `\n- Location: ${ev.location}` : ''}${msg.link ? `\n\n[Open in Calendar](${msg.link})` : ''}`
                  ),
                }}
              />
            )
          }
        }
      })}
      {loading && (
        <div class="typing">
          <span /><span /><span />
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  )
}
