import { useState } from 'react'
import { CheckCircle2, FileCheck2, Loader2, MessageSquareWarning } from 'lucide-react'
import type { HrCase } from '../../../types'

interface Props {
  hrCase: HrCase
  onOpenSigned: () => Promise<void>
  onUploadSigned: (file: File) => Promise<void>
  onAcknowledge: () => Promise<void>
  onRecheck: () => Promise<void>
}

export default function HrCaseSignedSection({ hrCase, onOpenSigned, onUploadSigned, onAcknowledge, onRecheck }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const v = hrCase.verification
  const canUpload = hrCase.allowed_events.includes('signed_uploaded')
  const comment = v?.reading?.employee_comments_text

  if (!hrCase.signed_file_id && !canUpload) return null

  async function run(action: () => Promise<void>) {
    setBusy(true)
    setError(null)
    try {
      await action()
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : 'That didn’t work — try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="space-y-2">
      <h3 className="text-xs font-medium uppercase tracking-wide text-w-faint">Signed copy</h3>
      {hrCase.stage === 'verifying' && (
        <p className="flex items-center gap-1.5 text-xs text-w-dim"><Loader2 size={12} className="animate-spin" /> Checking the signed copy…</p>
      )}
      {v?.outcome === 'verified' && (
        <p className="flex items-center gap-1.5 text-xs text-emerald-300"><CheckCircle2 size={13} /> Signed, readable and filed.</p>
      )}
      {v?.outcome === 'needs_attention' && hrCase.stage === 'needs_attention' && (
        <ul className="space-y-1 rounded-lg border border-amber-500/30 bg-amber-500/10 p-2.5 text-xs text-amber-100">
          {v.reason_text.map((r) => <li key={r}>{r}</li>)}
        </ul>
      )}
      {comment && (
        <div className="rounded-lg bg-w-surface2/60 p-2.5 text-xs">
          <p className="mb-1 flex items-center gap-1.5 font-medium text-w-dim"><MessageSquareWarning size={13} /> Employee’s comments</p>
          <p className="whitespace-pre-wrap text-w-text">{comment}</p>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {hrCase.signed_file_id && (
          <button type="button" onClick={() => void run(onOpenSigned)} className="inline-flex items-center gap-1.5 text-sm text-w-accent hover:underline">
            <FileCheck2 size={13} /> Open the signed copy
          </button>
        )}
        {hrCase.stage === 'needs_attention' && (
          <button type="button" disabled={busy} onClick={() => void run(onAcknowledge)} className="rounded-lg bg-w-accent px-3 py-1 text-sm font-medium text-w-on-accent hover:bg-w-accent-hi disabled:opacity-50">
            Handled — close case
          </button>
        )}
        {hrCase.stage === 'needs_attention' && v?.reasons.includes('check_unavailable') && (
          <button type="button" disabled={busy} onClick={() => void run(onRecheck)} className="rounded-lg border border-w-line px-3 py-1 text-sm text-w-dim hover:text-w-text disabled:opacity-50">
            Check again
          </button>
        )}
      </div>
      {canUpload && (
        <label className="block text-xs text-w-dim">
          {hrCase.signed_file_id ? 'Upload a new signed copy' : 'Upload the signed copy'}
          <input
            type="file"
            accept=".pdf,.png,.jpg,.jpeg"
            aria-label="Signed copy"
            disabled={busy}
            onChange={(e) => {
              const file = e.target.files?.[0]
              e.target.value = ''
              if (file) void run(() => onUploadSigned(file))
            }}
            className="mt-1 block text-sm"
          />
        </label>
      )}
      {error && <p role="alert" className="text-xs text-red-400">{error}</p>}
    </section>
  )
}
