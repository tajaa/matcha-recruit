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
    return <main className="mx-auto max-w-4xl px-6 py-8">{error ? <p className="text-sm text-red-700">{error}</p> : <p className="text-sm text-slate-500">Loading…</p>}</main>
  }

  const open = detail.status === 'pending' || detail.status === 'in_progress' || detail.status === 'expired'
  const submission = detail.submission
  const fieldRows = detail.spec.fields.map((f) => ({ f, value: (submission?.fields ?? detail.known_fields)[f.key] }))

  return (
    <main className="mx-auto max-w-4xl px-6 py-8">
      <Link to="/app/symlink" className="mb-4 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"><ArrowLeft size={14} /> All sym-links</Link>
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div>
          <h1 className="text-2xl font-semibold text-slate-950">{detail.title}</h1>
          <p className="mt-1 text-sm text-slate-500">{detail.recipient_name} · {detail.recipient_email} · <span className="capitalize">{detail.status.replace('_', ' ')}</span></p>
          {detail.instructions && <p className="mt-2 max-w-xl text-sm text-slate-600">{detail.instructions}</p>}
        </div>
        {open && (
          <div className="flex gap-2">
            <button disabled={busy} onClick={() => void run(() => resendSymlink(linkId))} className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"><RefreshCw size={14} /> Resend</button>
            <button disabled={busy} onClick={() => { if (window.confirm('Revoke this link? The recipient will no longer be able to open it.')) void run(() => revokeSymlink(linkId)) }} className="inline-flex items-center gap-1 rounded-lg border border-red-200 px-3 py-2 text-sm text-red-700 hover:bg-red-50 disabled:opacity-50"><X size={14} /> Revoke</button>
          </div>
        )}
      </div>

      {error && <p className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}

      <div className="mt-6 grid gap-4 text-sm sm:grid-cols-3">
        <Stat label="Sent" value={detail.sent_at ? dateFormat.format(new Date(detail.sent_at)) : 'Not emailed'} />
        <Stat label="First opened" value={detail.first_unlocked_at ? dateFormat.format(new Date(detail.first_unlocked_at)) : '—'} />
        <Stat label="Expires" value={detail.expires_at ? dateFormat.format(new Date(detail.expires_at)) : '—'} />
      </div>

      {open && (
        <div className="mt-4 flex items-center gap-2">
          <code className="flex-1 truncate rounded-lg bg-slate-100 px-3 py-2 text-xs text-slate-700">{detail.link}</code>
          <button className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50" onClick={() => { void navigator.clipboard?.writeText(detail.link); setCopied(true); setTimeout(() => setCopied(false), 1500) }}>
            <Copy size={14} /> {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      )}

      {submission && (
        <section className={`mt-8 rounded-2xl border p-5 ${submission.status === 'pending' ? 'border-amber-200 bg-amber-50' : 'border-slate-200 bg-white'}`}>
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="font-semibold text-slate-900">{submission.status === 'pending' ? 'Submission awaiting your review' : `Submission ${submission.status}`}</h2>
              <p className="mt-1 text-sm text-slate-600">{APPLY_COPY[detail.kind]}</p>
              {submission.review_note && <p className="mt-2 text-sm text-slate-600">Note: {submission.review_note}</p>}
            </div>
            {submission.status === 'pending' && (
              <div className="flex shrink-0 flex-col gap-2">
                <button disabled={busy} onClick={() => void run(() => applySubmission(submission.id))} className="inline-flex items-center gap-1 rounded-lg bg-emerald-700 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-50">{busy ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Apply</button>
                <button disabled={busy} onClick={() => void run(() => rejectSubmission(submission.id, note))} className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-white disabled:opacity-50"><X size={14} /> Reject</button>
              </div>
            )}
          </div>
          {submission.status === 'pending' && (
            <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} placeholder="Optional note if rejecting" className="mt-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          )}
        </section>
      )}

      <section className="mt-8 rounded-2xl border border-slate-200 bg-white p-5">
        <h2 className="font-semibold text-slate-900">Collected so far</h2>
        <dl className="mt-3 divide-y divide-slate-100">
          {fieldRows.map(({ f, value }) => (
            <div key={f.key} className="grid gap-1 py-2 sm:grid-cols-3">
              <dt className="text-sm text-slate-500">{f.label}{f.required && <span className="text-red-500"> *</span>}</dt>
              <dd className="whitespace-pre-wrap text-sm text-slate-900 sm:col-span-2">{fmt(value)}</dd>
            </div>
          ))}
        </dl>
        {detail.spec.attachments.length > 0 && (
          <div className="mt-4">
            <h3 className="text-sm font-medium text-slate-700">Files</h3>
            <ul className="mt-2 space-y-1">
              {detail.spec.attachments.map((slot) => {
                const file = detail.attachments.find((a) => a.slot === slot.slot)
                return (
                  <li key={slot.slot} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-sm">
                    <span>{slot.label}{slot.required && <span className="text-red-500"> *</span>}: {file ? file.file_name : <span className="text-slate-400">not uploaded</span>}</span>
                    {file && <button onClick={() => void download(file.id)} className="inline-flex items-center gap-1 text-emerald-700 hover:underline"><Download size={14} /> Open</button>}
                  </li>
                )
              })}
            </ul>
          </div>
        )}
      </section>

      <section className="mt-8 rounded-2xl border border-slate-200 bg-white p-5">
        <h2 className="font-semibold text-slate-900">Conversation</h2>
        <p className="mt-1 text-xs text-slate-500">{detail.turn_count} turn{detail.turn_count === 1 ? '' : 's'}. This is what the recipient and the guide said to each other.</p>
        <div className="mt-3 max-h-[50vh] space-y-2 overflow-y-auto">
          {detail.transcript.map((m, i) => (
            <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${m.role === 'user' ? 'bg-emerald-50 text-emerald-950' : 'bg-slate-100 text-slate-800'}`}>{m.content}</div>
            </div>
          ))}
        </div>
      </section>
    </main>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 font-medium text-slate-900">{value}</p>
    </div>
  )
}
