import { useEffect, useState } from 'react'
import { Loader2, Plus, X } from 'lucide-react'
import { Badge, Button, Input, Modal, Textarea } from '../ui'
import { api } from '../../api/client'

type Question = {
  text: string
  source: 'copilot' | 'admin'
}

interface Props {
  open: boolean
  onClose: () => void
  incidentId: string
  openQuestions: string[]
  defaultRecipientName?: string | null
  defaultRecipientEmail?: string | null
  onSent: () => void
}

export function IRRequestInfoModal({
  open,
  onClose,
  incidentId,
  openQuestions,
  defaultRecipientName,
  defaultRecipientEmail,
  onSent,
}: Props) {
  const [recipientName, setRecipientName] = useState('')
  const [recipientEmail, setRecipientEmail] = useState('')
  const [questions, setQuestions] = useState<Question[]>([])
  const [newQuestion, setNewQuestion] = useState('')
  const [customMessage, setCustomMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sendFailedLink, setSendFailedLink] = useState<string | null>(null)

  // Reset + seed from the incident's known reporter and the Copilot's
  // current open_questions each time the modal opens.
  useEffect(() => {
    if (!open) return
    setRecipientName(defaultRecipientName || '')
    setRecipientEmail(defaultRecipientEmail || '')
    setQuestions(openQuestions.map((text) => ({ text, source: 'copilot' as const })))
    setNewQuestion('')
    setCustomMessage('')
    setError(null)
    setSendFailedLink(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  function addQuestion() {
    const text = newQuestion.trim()
    if (!text) return
    setQuestions((qs) => [...qs, { text, source: 'admin' }])
    setNewQuestion('')
  }

  function removeQuestion(index: number) {
    setQuestions((qs) => qs.filter((_, i) => i !== index))
  }

  const canSend =
    recipientName.trim().length > 0 &&
    /\S+@\S+\.\S+/.test(recipientEmail.trim()) &&
    questions.length > 0 &&
    !sending

  async function handleSend() {
    if (!canSend) return
    setSending(true)
    setError(null)
    setSendFailedLink(null)
    try {
      const resp = await api.post<{ email_sent: boolean; link: string }>(
        `/ir/incidents/${incidentId}/info-requests`,
        {
          recipient_name: recipientName.trim(),
          recipient_email: recipientEmail.trim(),
          questions: questions.map((q) => ({ text: q.text, source: q.source })),
          custom_message: customMessage.trim() || null,
        },
      )
      onSent()
      if (resp.email_sent) {
        onClose()
      } else {
        // Keep the modal open — the admin needs the link since the invite
        // email didn't actually go out (Gmail/MailerSend both unavailable).
        setSendFailedLink(resp.link)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to send request')
    } finally {
      setSending(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Request More Info" width="lg">
      <div className="space-y-5">
        <p className="text-sm text-zinc-400">
          Email an outside party (the reporter, a witness) a one-time link to answer
          questions about this incident. Their answers land back in this Copilot thread —
          they never change the incident record directly.
        </p>

        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Recipient name"
            value={recipientName}
            onChange={(e) => setRecipientName(e.target.value)}
            placeholder="Jane Doe"
            maxLength={255}
          />
          <Input
            label="Recipient email"
            type="email"
            value={recipientEmail}
            onChange={(e) => setRecipientEmail(e.target.value)}
            placeholder="jane@example.com"
            maxLength={255}
          />
        </div>

        <div>
          <div className="text-sm font-medium text-zinc-300 mb-1.5">Questions</div>
          <div className="space-y-2">
            {questions.map((q, i) => (
              <div
                key={i}
                className="flex items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2"
              >
                <Badge variant={q.source === 'copilot' ? 'warning' : 'neutral'}>
                  {q.source === 'copilot' ? 'Copilot' : 'You'}
                </Badge>
                <span className="flex-1 text-sm text-zinc-200">{q.text}</span>
                <button
                  type="button"
                  onClick={() => removeQuestion(i)}
                  className="text-zinc-500 hover:text-zinc-300"
                  aria-label="Remove question"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
            {questions.length === 0 && (
              <div className="text-xs text-zinc-500">No questions yet — add at least one below.</div>
            )}
          </div>
          <div className="flex items-center gap-2 mt-2">
            <input
              type="text"
              value={newQuestion}
              onChange={(e) => setNewQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  addQuestion()
                }
              }}
              placeholder="Add a question…"
              maxLength={1000}
              className="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-3.5 py-2 text-sm text-zinc-100 placeholder-zinc-500 outline-none focus:border-zinc-500 focus:ring-1 focus:ring-zinc-500"
            />
            <Button variant="ghost" size="sm" onClick={addQuestion} disabled={!newQuestion.trim()}>
              <Plus className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>

        <Textarea
          label="Message (optional)"
          value={customMessage}
          onChange={(e) => setCustomMessage(e.target.value)}
          rows={3}
          maxLength={2000}
          placeholder="Add any context for the recipient…"
        />

        {error && (
          <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        {sendFailedLink && (
          <div className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 space-y-1.5">
            <div>Request created, but the invite email failed to send. Share this link with the recipient directly, or use Resend later.</div>
            <div className="select-all text-zinc-300 break-all">{sendFailedLink}</div>
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onClose} disabled={sending}>
            {sendFailedLink ? 'Done' : 'Cancel'}
          </Button>
          {!sendFailedLink && (
            <Button onClick={() => { void handleSend() }} disabled={!canSend}>
              {sending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
              <span className={sending ? 'ml-2' : ''}>{sending ? 'Sending…' : 'Send request'}</span>
            </Button>
          )}
        </div>
      </div>
    </Modal>
  )
}
