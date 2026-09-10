import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Check, Copy, Download, Loader2, RefreshCw, X } from 'lucide-react'
import {
  applySubmission,
  attachmentDownloadUrl,
  getSymlink,
  rejectSubmission,
  resendSymlink,
  revokeSymlink,
} from '../../../api/symlink/symlink'
import { Badge, Button, Input, LABEL } from '../../../components/ui'
import type { SymlinkDetail as Detail, SymlinkKind } from '../../../types/symlink'

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

const APPLY_COPY: Record<SymlinkKind, string> = {
  credential_upload: 'Applying files the uploaded document onto the linked employee\'s credential record and starts extraction.',
  info_update: 'Applying updates the linked employee\'s phone, address, and emergency contact from these answers.',
  manager_review: 'Applying marks this review as accepted. Nothing else is written.',
  custom: 'Applying marks this request as accepted. Nothing else is written.',
}

function fmt(value: unknown) {
  if (value === null || value === undefined || value === '') return '—'
  return typeof value === 'string' ? value : JSON.stringify(value)
}

export default function SymLinkDetail() {
  const { linkId = '' } = useParams()
  const [detail, setDetail] = useState<Detail | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const [copied, setCopied] = useState(false)

  const load = () => getSymlink(linkId).then(setDetail).catch((err) => setError(err instanceof Error ? err.message : 'Could not load this sym-link.'))
  useEffect(() => { void load() }, [linkId]) // eslint-disable-line react-hooks/exhaustive-deps

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setError('')
    try {
      await action()
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That action failed.')
    } finally {
      setBusy(false)
    }
  }

  async function download(attachmentId: string) {
    try {
      const { url } = await attachmentDownloadUrl(linkId, attachmentId)
      window.open(url, '_blank', 'noopener')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not open the file.')
    }
  }

  if (!detail) {
    return error
      ? <p className="text-sm text-red-300">{error}</p>
      : <p className="text-xs uppercase tracking-wider text-zinc-500">Loading sym-link...</p>
  }

  const open = detail.status === 'pending' || detail.status === 'in_progress' || detail.status === 'expired'
  const submission = detail.submission
  const fieldRows = detail.spec.fields.map((f) => ({ f, value: (submission?.fields ?? detail.known_fields)[f.key] }))

  return (
    <div className="space-y-6">
      <Link to="/app/symlink" className="inline-flex items-center gap-1 text-xs text-zinc-500 transition-colors hover:text-zinc-300">
        <ArrowLeft className="h-3.5 w-3.5" /> All sym-links
      </Link>

      <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-start sm:gap-0">
        <div className="min-w-0">
          <h1 className="text-lg font-semibold text-zinc-100">{detail.title}</h1>
          <p className="mt-0.5 text-xs text-zinc-500">
            {detail.recipient_name} · {detail.recipient_email} ·{' '}
            <span className="capitalize">{detail.status.replace('_', ' ')}</span>
          </p>
          {detail.instructions && <p className="mt-2 max-w-xl text-xs leading-relaxed text-zinc-400">{detail.instructions}</p>}
        </div>
        {open && (
          <div className="flex shrink-0 gap-2">
            <Button variant="secondary" size="sm" disabled={busy} onClick={() => void run(() => resendSymlink(linkId))}>
              <RefreshCw className="h-3.5 w-3.5" /> Resend
            </Button>
            <Button
              variant="danger"
              size="sm"
              disabled={busy}
              onClick={() => { if (window.confirm('Revoke this link? The recipient will no longer be able to open it.')) void run(() => revokeSymlink(linkId)) }}
            >
              <X className="h-3.5 w-3.5" /> Revoke
            </Button>
          </div>
        )}
      </div>

      {error && (
        <p className="rounded-lg border border-red-500/20 bg-red-500/[0.06] px-4 py-3 text-sm text-red-300">{error}</p>
      )}

      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="Sent" value={detail.sent_at ? dateFormat.format(new Date(detail.sent_at)) : 'Not emailed'} />
        <Stat label="First opened" value={detail.first_unlocked_at ? dateFormat.format(new Date(detail.first_unlocked_at)) : '—'} />
        <Stat label="Expires" value={detail.expires_at ? dateFormat.format(new Date(detail.expires_at)) : '—'} />
      </div>

      {open && (
        <div className="flex items-center gap-2">
          <code className="flex-1 truncate rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 font-mono text-[11px] text-zinc-300">{detail.link}</code>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => { void navigator.clipboard?.writeText(detail.link); setCopied(true); setTimeout(() => setCopied(false), 1500) }}
          >
            <Copy className="h-3.5 w-3.5" /> {copied ? 'Copied' : 'Copy'}
          </Button>
        </div>
      )}

      {submission && (
        <section
          className={`rounded-lg border p-5 ${
            submission.status === 'pending'
              ? 'border-amber-500/25 bg-amber-500/[0.05]'
              : 'border-zinc-800 bg-zinc-900/50'
          }`}
        >
          <div className="flex flex-col items-start justify-between gap-4 sm:flex-row">
            <div className="min-w-0">
              <h2 className="text-sm font-medium text-zinc-100">
                {submission.status === 'pending' ? 'Submission awaiting your review' : `Submission ${submission.status}`}
              </h2>
              <p className="mt-1 text-xs leading-relaxed text-zinc-400">{APPLY_COPY[detail.kind]}</p>
              {submission.review_note && <p className="mt-2 text-xs text-zinc-400">Note: {submission.review_note}</p>}
            </div>
            {submission.status === 'pending' && (
              <div className="flex shrink-0 gap-2">
                <Button variant="success" size="sm" disabled={busy} onClick={() => void run(() => applySubmission(submission.id))}>
                  {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Apply
                </Button>
                <Button variant="secondary" size="sm" disabled={busy} onClick={() => void run(() => rejectSubmission(submission.id, note))}>
                  <X className="h-3.5 w-3.5" /> Reject
                </Button>
              </div>
            )}
          </div>
          {submission.status === 'pending' && (
            <div className="mt-3">
              <Input value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} placeholder="Optional note if rejecting" />
            </div>
          )}
        </section>
      )}

      <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-5">
        <h2 className="text-sm font-medium text-zinc-100">Collected so far</h2>
        <dl className="mt-3 divide-y divide-zinc-800">
          {fieldRows.map(({ f, value }) => (
            <div key={f.key} className="grid gap-1 py-2.5 sm:grid-cols-3">
              <dt className="text-xs text-zinc-500">
                {f.label}{f.required && <span className="text-red-400"> *</span>}
              </dt>
              <dd className="whitespace-pre-wrap text-sm text-zinc-200 sm:col-span-2">{fmt(value)}</dd>
            </div>
          ))}
        </dl>
        {detail.spec.attachments.length > 0 && (
          <div className="mt-5">
            <span className={LABEL}>Files</span>
            <ul className="mt-2 space-y-1.5">
              {detail.spec.attachments.map((slot) => {
                const file = detail.attachments.find((a) => a.slot === slot.slot)
                return (
                  <li key={slot.slot} className="flex items-center justify-between gap-3 rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm">
                    <span className="min-w-0 truncate text-zinc-300">
                      {slot.label}{slot.required && <span className="text-red-400"> *</span>}:{' '}
                      {file ? file.file_name : <span className="text-zinc-600">not uploaded</span>}
                    </span>
                    {file && (
                      <button
                        onClick={() => void download(file.id)}
                        className="inline-flex shrink-0 items-center gap-1 text-xs text-emerald-400 transition-colors hover:text-emerald-300"
                      >
                        <Download className="h-3.5 w-3.5" /> Open
                      </button>
                    )}
                  </li>
                )
              })}
            </ul>
          </div>
        )}
      </section>

      <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-5">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-sm font-medium text-zinc-100">Conversation</h2>
          <Badge variant="neutral">{detail.turn_count} turn{detail.turn_count === 1 ? '' : 's'}</Badge>
        </div>
        <p className="mt-1 text-[11px] text-zinc-500">What the recipient and the guide said to each other.</p>
        <div className="mt-3 max-h-[50vh] space-y-2 overflow-y-auto">
          {detail.transcript.map((m, i) => (
            <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${
                  m.role === 'user'
                    ? 'border border-emerald-500/25 bg-emerald-500/[0.08] text-zinc-100'
                    : 'border border-zinc-800 bg-zinc-950 text-zinc-300'
                }`}
              >
                {m.content}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-4 py-3">
      <p className={LABEL}>{label}</p>
      <p className="mt-1 text-sm font-medium text-zinc-100">{value}</p>
    </div>
  )
}
