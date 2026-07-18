import { useState } from 'react'
import { X, Loader2, XCircle, Mail, MailX } from 'lucide-react'

interface Props {
  candidateName: string
  candidateEmail: string | null
  positionTitle?: string
  onConfirm: (opts: { reason?: string; customMessage?: string; sendEmail: boolean }) => Promise<void>
  onClose: () => void
}

// Match RecruitingPipeline / InterviewReviewModal palette
const c = {
  bg: '#1e1e1e',
  cardBg: '#252526',
  border: '#333',
  text: '#d4d4d4',
  heading: '#e8e8e8',
  muted: '#6a737d',
  subMuted: '#a1a1a1',
  accent: '#ce9178',
  green: '#22c55e',
  red: '#ef4444',
}

export default function RejectCandidateModal({
  candidateName,
  candidateEmail,
  positionTitle,
  onConfirm,
  onClose,
}: Props) {
  const hasEmail = !!candidateEmail
  const [sendEmail, setSendEmail] = useState<boolean>(hasEmail)
  const [customMessage, setCustomMessage] = useState('')
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleConfirm() {
    setSubmitting(true)
    setError(null)
    try {
      await onConfirm({
        reason: reason.trim() || undefined,
        customMessage: customMessage.trim() || undefined,
        sendEmail: hasEmail && sendEmail,
      })
      // parent closes on success
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Something went wrong')
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.6)' }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg shadow-2xl"
        style={{ background: c.bg, border: `1px solid ${c.border}` }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-5 py-4"
          style={{ borderBottom: `1px solid ${c.border}` }}
        >
          <div className="flex items-center gap-2.5">
            <XCircle size={18} style={{ color: c.red }} />
            <div>
              <h2 className="text-[15px] font-semibold" style={{ color: c.heading }}>
                Reject candidate
              </h2>
              <p className="text-[11px]" style={{ color: c.muted }}>
                {candidateName}
                {positionTitle ? ` · ${positionTitle}` : ''}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 transition-colors hover:bg-white/5"
            style={{ color: c.muted }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-5 space-y-4">
          {/* Send-email toggle */}
          <div>
            <label
              className={`flex items-start gap-3 rounded-md p-3 transition-colors ${hasEmail ? 'cursor-pointer hover:bg-white/[0.02]' : 'opacity-60'}`}
              style={{ border: `1px solid ${c.border}`, background: c.cardBg }}
            >
              <input
                type="checkbox"
                checked={sendEmail && hasEmail}
                onChange={(e) => setSendEmail(e.target.checked)}
                disabled={!hasEmail}
                className="mt-0.5 h-4 w-4 shrink-0 rounded accent-emerald-500"
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 text-[13px] font-medium" style={{ color: c.heading }}>
                  {hasEmail ? <Mail size={13} /> : <MailX size={13} />}
                  Send a polite rejection email
                </div>
                <p className="mt-0.5 text-[11px]" style={{ color: c.subMuted }}>
                  {hasEmail
                    ? `Closes the loop with ${candidateEmail} using our matcha template.`
                    : 'No email on file — the candidate will be silently removed from the list.'}
                </p>
              </div>
            </label>
          </div>

          {/* Custom message (only when send-email) */}
          {hasEmail && sendEmail && (
            <div>
              <label className="mb-1.5 block text-[11px] font-medium" style={{ color: c.muted }}>
                Custom message (optional)
              </label>
              <textarea
                value={customMessage}
                onChange={(e) => setCustomMessage(e.target.value)}
                placeholder="Appears above the standard template. Keep it brief."
                rows={3}
                className="w-full rounded-md border px-3 py-2 text-[12px] focus:outline-none focus:ring-1"
                style={{
                  background: c.bg,
                  color: c.text,
                  borderColor: c.border,
                }}
              />
            </div>
          )}

          {/* Internal note */}
          <div>
            <label className="mb-1.5 block text-[11px] font-medium" style={{ color: c.muted }}>
              Internal note (optional, never sent)
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Not enough experience with Kubernetes"
              rows={2}
              className="w-full rounded-md border px-3 py-2 text-[12px] focus:outline-none focus:ring-1"
              style={{
                background: c.bg,
                color: c.text,
                borderColor: c.border,
              }}
            />
          </div>

          {error && (
            <p className="text-[11px]" style={{ color: c.red }}>
              {error}
            </p>
          )}
        </div>

        {/* Footer */}
        <div
          className="flex items-center justify-end gap-2 px-5 py-3"
          style={{ borderTop: `1px solid ${c.border}` }}
        >
          <button
            onClick={onClose}
            disabled={submitting}
            className="rounded-md px-3 py-1.5 text-[12px] font-medium transition-colors disabled:opacity-40 hover:bg-white/5"
            style={{ color: c.subMuted }}
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={submitting}
            className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] font-semibold transition-colors disabled:opacity-50"
            style={{ background: c.red, color: '#fff' }}
          >
            {submitting ? <Loader2 size={12} className="animate-spin" /> : <XCircle size={12} />}
            {submitting ? 'Rejecting…' : hasEmail && sendEmail ? 'Reject & send email' : 'Reject'}
          </button>
        </div>
      </div>
    </div>
  )
}
