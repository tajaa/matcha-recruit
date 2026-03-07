import { useState } from 'preact/hooks'
import type { Email } from '../lib/api'

interface Props {
  email: Email
  onDraft: (emailId: string, instructions: string) => void
  onSend: (to: string, subject: string, body: string, replyToId?: string) => void
  onSchedule: (emailId: string) => void
}

export function EmailCard({ email, onDraft, onSend, onSchedule }: Props) {
  const [mode, setMode] = useState<'actions' | 'compose' | 'reply'>('actions')
  const [instructions, setInstructions] = useState('')
  const [to, setTo] = useState('')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)

  const preview = (email.body || '').slice(0, 150).replace(/\n/g, ' ')

  const handleDraft = async () => {
    setBusy(true)
    await onDraft(email.id, instructions)
    setBusy(false)
    setMode('actions')
    setInstructions('')
  }

  const handleSend = async () => {
    if (!to.trim() || !subject.trim()) return
    setBusy(true)
    await onSend(to, subject, body, email.id)
    setBusy(false)
    setMode('actions')
    setTo('')
    setSubject('')
    setBody('')
  }

  const handleSchedule = async () => {
    setBusy(true)
    await onSchedule(email.id)
    setBusy(false)
  }

  const startReply = () => {
    setTo(email.from)
    setSubject(`Re: ${email.subject}`)
    setBody('')
    setMode('reply')
  }

  return (
    <div class="email-card">
      <div class="email-card-subject">{email.subject}</div>
      <div class="email-card-meta">
        {email.from} &middot; {email.date}
      </div>
      <div class="email-card-preview">{preview}...</div>

      {mode === 'compose' && (
        <div class="email-draft-form">
          <textarea
            placeholder="Reply instructions (e.g. 'say thanks and confirm')..."
            value={instructions}
            onInput={(e) =>
              setInstructions((e.target as HTMLTextAreaElement).value)
            }
            autoFocus
          />
          <div class="email-draft-actions">
            <button
              class="btn-sm cancel"
              onClick={() => setMode('actions')}
              disabled={busy}
            >
              cancel
            </button>
            <button class="btn-sm primary" onClick={handleDraft} disabled={busy}>
              {busy ? 'drafting...' : 'draft & save'}
            </button>
          </div>
        </div>
      )}

      {mode === 'reply' && (
        <div class="email-draft-form">
          <input
            type="text"
            placeholder="To"
            value={to}
            onInput={(e) => setTo((e.target as HTMLInputElement).value)}
          />
          <input
            type="text"
            placeholder="Subject"
            value={subject}
            onInput={(e) => setSubject((e.target as HTMLInputElement).value)}
          />
          <textarea
            placeholder="Write your reply..."
            value={body}
            onInput={(e) =>
              setBody((e.target as HTMLTextAreaElement).value)
            }
            rows={4}
            autoFocus
          />
          <div class="email-draft-actions">
            <button
              class="btn-sm cancel"
              onClick={() => setMode('actions')}
              disabled={busy}
            >
              cancel
            </button>
            <button
              class="btn-sm primary"
              onClick={handleSend}
              disabled={busy || !to.trim() || !subject.trim()}
            >
              {busy ? 'sending...' : 'send'}
            </button>
          </div>
        </div>
      )}

      {mode === 'actions' && (
        <div class="email-card-actions">
          <button
            class="email-action-btn"
            onClick={() => setMode('compose')}
            disabled={busy}
          >
            &#9997; ai draft
          </button>
          <button
            class="email-action-btn"
            onClick={startReply}
            disabled={busy}
          >
            &#9993; reply
          </button>
          <button
            class="email-action-btn"
            onClick={handleSchedule}
            disabled={busy}
          >
            &#128197; schedule
          </button>
        </div>
      )}
    </div>
  )
}
