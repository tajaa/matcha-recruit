import { useState } from 'preact/hooks'
import type { Email } from '../lib/api'

interface Props {
  email: Email
  onDraft: (emailId: string, instructions: string) => void
  onSchedule: (emailId: string) => void
}

export function EmailCard({ email, onDraft, onSchedule }: Props) {
  const [showDraft, setShowDraft] = useState(false)
  const [instructions, setInstructions] = useState('')
  const [busy, setBusy] = useState(false)

  const preview = (email.body || '').slice(0, 150).replace(/\n/g, ' ')

  const handleDraft = async () => {
    setBusy(true)
    await onDraft(email.id, instructions)
    setBusy(false)
    setShowDraft(false)
    setInstructions('')
  }

  const handleSchedule = async () => {
    setBusy(true)
    await onSchedule(email.id)
    setBusy(false)
  }

  return (
    <div class="email-card">
      <div class="email-card-subject">{email.subject}</div>
      <div class="email-card-meta">
        {email.from} &middot; {email.date}
      </div>
      <div class="email-card-preview">{preview}...</div>

      {showDraft ? (
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
              onClick={() => setShowDraft(false)}
              disabled={busy}
            >
              cancel
            </button>
            <button class="btn-sm primary" onClick={handleDraft} disabled={busy}>
              {busy ? 'drafting...' : 'draft & save'}
            </button>
          </div>
        </div>
      ) : (
        <div class="email-card-actions">
          <button
            class="email-action-btn"
            onClick={() => setShowDraft(true)}
            disabled={busy}
          >
            &#9997; draft reply
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
