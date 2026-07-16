import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, CheckCircle2, XCircle, AlertTriangle, MapPin, Paperclip, X } from 'lucide-react'
import { IRPersonMultiSelect } from '../../components/ir/IRPersonMultiSelect'
import { IRPublicDictate } from '../../components/ir/IRPublicDictate'
import { SubmissionDisclaimer } from '../../components/ir/SubmissionDisclaimer'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

const inputCls =
  'mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700'

// Mirrors the server caps in ir_incidents/_shared.py. Client-side checks are UX
// only — the server re-validates every one of these.
const MAX_FILES = 5
const MAX_FILE_BYTES = 10 * 1024 * 1024
const MAX_TOTAL_BYTES = 25 * 1024 * 1024
const ACCEPT = '.jpg,.jpeg,.png,.gif,.pdf,.txt,.doc,.docx'

type Stage = 'validating' | 'invalid' | 'used' | 'form' | 'submitting' | 'submitted' | 'error'

type IntakeInfo = {
  company_name: string | null
  voice_enabled?: boolean
  location: { id: string | null; name: string | null; label: string }
}

// Public, unauthenticated incident intake reached via a per-location magic
// link (/intake/:token). Unlike the anonymous /report form this is attributed
// (reporter name required) and the location is hard-coded from the token, so
// HR gets a full-quality incident (real location_id + AI categorization)
// without the reporter needing to log in.
export default function LocationIntake() {
  const { token } = useParams<{ token: string }>()
  const [stage, setStage] = useState<Stage>('validating')
  const [info, setInfo] = useState<IntakeInfo | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [reportedByName, setReportedByName] = useState('')
  const [occurredAt, setOccurredAt] = useState('')
  const [description, setDescription] = useState('')
  const [witnesses, setWitnesses] = useState<string[]>([])
  const [nextSteps, setNextSteps] = useState('')
  const [honeypot, setHoneypot] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [fileError, setFileError] = useState<string | null>(null)
  // Verbatim transcript from the last successful dictation — rides along to
  // the submission as evidence of what was spoken, regardless of edits made
  // to the (AI-prefilled) form fields afterward.
  const [voiceTranscript, setVoiceTranscript] = useState<string | null>(null)

  function addFiles(picked: FileList | null) {
    if (!picked?.length) return
    setFileError(null)
    const next = [...files]
    for (const f of Array.from(picked)) {
      if (next.length >= MAX_FILES) {
        setFileError(`You can attach at most ${MAX_FILES} files.`)
        break
      }
      if (f.size > MAX_FILE_BYTES) {
        setFileError(`"${f.name}" is over ${MAX_FILE_BYTES / (1024 * 1024)} MB.`)
        continue
      }
      if (next.some((n) => n.name === f.name && n.size === f.size)) continue
      next.push(f)
    }
    if (next.reduce((sum, f) => sum + f.size, 0) > MAX_TOTAL_BYTES) {
      setFileError(`Attachments total over ${MAX_TOTAL_BYTES / (1024 * 1024)} MB.`)
      return
    }
    setFiles(next)
  }

  useEffect(() => {
    if (!token) {
      setStage('invalid')
      return
    }
    fetch(`${BASE}/intake/${token}`)
      .then(async (res) => {
        if (res.ok) {
          const data = (await res.json().catch(() => null)) as IntakeInfo | null
          setInfo(data)
          setStage('form')
          return
        }
        if (res.status === 410) {
          const data = (await res.json().catch(() => null)) as { detail?: string } | null
          setError(data?.detail ?? null)
          setStage('used')
        } else setStage('invalid')
      })
      .catch(() => setStage('invalid'))
  }, [token])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!reportedByName.trim() || description.trim().length < 10) return
    setStage('submitting')
    setError(null)
    try {
      // Multipart: the report itself rides as a JSON `payload` field so the
      // server-side model keeps its shape, with attachments alongside it. One
      // request — the incident and its files land together or not at all.
      const fd = new FormData()
      fd.append(
        'payload',
        JSON.stringify({
          description: description.trim(),
          reported_by_name: reportedByName.trim(),
          occurred_at: occurredAt.trim() || null,
          witnesses,
          corrective_actions: nextSteps.trim() || null,
          internal_ref: honeypot,
          ...(voiceTranscript ? { voice_transcript: voiceTranscript } : {}),
        }),
      )
      for (const f of files) fd.append('files', f)
      // No Content-Type header — the browser must set the multipart boundary.
      const res = await fetch(`${BASE}/intake/${token}`, { method: 'POST', body: fd })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setError(data.detail ?? 'Submission failed. Please try again.')
        setStage('error')
        return
      }
      setStage('submitted')
    } catch {
      setError('Network error. Please try again.')
      setStage('error')
    }
  }

  if (stage === 'validating') {
    return (
      <Shell>
        <Loader2 className="w-6 h-6 text-zinc-500 animate-spin mx-auto" />
      </Shell>
    )
  }

  if (stage === 'invalid') {
    return (
      <Shell>
        <XCircle className="w-10 h-10 text-red-400 mx-auto mb-3" />
        <h1 className="text-lg font-semibold text-zinc-100 mb-2">Invalid link</h1>
        <p className="text-sm text-zinc-400">This reporting link is not valid. Contact your HR team for a new one.</p>
      </Shell>
    )
  }

  if (stage === 'used') {
    return (
      <Shell>
        <AlertTriangle className="w-10 h-10 text-amber-400 mx-auto mb-3" />
        <h1 className="text-lg font-semibold text-zinc-100 mb-2">Link unavailable</h1>
        <p className="text-sm text-zinc-400">{error ?? 'This reporting link is no longer active. Contact your HR team for a new one.'}</p>
      </Shell>
    )
  }

  if (stage === 'submitted') {
    return (
      <Shell>
        <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto mb-3" />
        <h1 className="text-lg font-semibold text-zinc-100 mb-2">Report submitted</h1>
        <p className="text-sm text-zinc-400">Your report has been received. Thank you.</p>
      </Shell>
    )
  }

  const canSubmit = reportedByName.trim().length > 0 && description.trim().length >= 10

  return (
    <Shell wide>
      <h1 className="text-lg font-semibold text-zinc-100 mb-1 text-center">Report an incident</h1>
      <p className="text-sm text-zinc-400 mb-4 text-center">
        {info?.company_name ? `${info.company_name} — ` : ''}HR will review your submission.
      </p>

      <div className="flex items-center gap-2 bg-zinc-900/60 border border-zinc-800 rounded p-3 mb-5">
        <MapPin className="w-4 h-4 text-emerald-500 shrink-0" />
        <div className="text-left">
          <span className="block text-[10px] text-zinc-500 uppercase tracking-widest">Location</span>
          <span className="text-sm text-zinc-100">{info?.location?.label ?? 'This site'}</span>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4 text-left">
        {info?.voice_enabled && (
          <IRPublicDictate
            parseUrl={`${BASE}/intake/${token}/voice/parse`}
            onPrefill={(p) => {
              if (p.description) setDescription(p.description)
              if (p.reported_by_name) setReportedByName(p.reported_by_name)
              if (p.occurred_at_text) setOccurredAt(p.occurred_at_text)
              if (p.witnesses?.length) {
                setWitnesses((w) => Array.from(new Set([...w, ...p.witnesses.map((x) => x.name)])))
              }
              setVoiceTranscript(p.transcript ?? null)
            }}
          />
        )}

        <Field label="Your name">
          <input
            type="text"
            value={reportedByName}
            onChange={(e) => setReportedByName(e.target.value)}
            maxLength={255}
            placeholder="Who is reporting?"
            className={inputCls}
          />
        </Field>

        <Field label="Date and time of incident" optional hint='Free text — e.g. "yesterday around 3pm", "May 1 at 9am".'>
          <input
            type="text"
            value={occurredAt}
            onChange={(e) => setOccurredAt(e.target.value)}
            maxLength={255}
            placeholder="e.g. yesterday around 3pm"
            className={inputCls}
          />
        </Field>

        <Field label="Description">
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={6}
            maxLength={10000}
            placeholder="What happened? Include relevant details — Intelligent Theme Analysis will categorize from this."
            className={inputCls}
          />
        </Field>

        <IRPersonMultiSelect
          label="Witnesses / others involved"
          value={witnesses}
          onChange={setWitnesses}
          placeholder="Type a name, Enter to add"
          disableSuggestions
        />

        <Field label="Recommended next steps" optional hint="Anything you'd like the team to do?">
          <textarea
            value={nextSteps}
            onChange={(e) => setNextSteps(e.target.value)}
            rows={2}
            maxLength={10000}
            className={inputCls}
          />
        </Field>

        <div>
          <span className="text-xs text-zinc-400 uppercase tracking-wide">
            Photos or documents
            <span className="ml-1 normal-case tracking-normal text-zinc-600">(optional)</span>
          </span>
          <span className="block text-[11px] text-zinc-500 mt-0.5">
            Up to {MAX_FILES} files, {MAX_FILE_BYTES / (1024 * 1024)} MB each.
          </span>

          {files.length < MAX_FILES && (
            <label className="mt-2 flex items-center justify-center gap-2 border border-dashed border-zinc-800 hover:border-zinc-700 rounded px-3 py-3 cursor-pointer transition-colors">
              <Paperclip className="w-4 h-4 text-zinc-500" />
              <span className="text-sm text-zinc-400">Add photos or documents</span>
              <input
                type="file"
                multiple
                accept={ACCEPT}
                className="hidden"
                onChange={(e) => {
                  addFiles(e.target.files)
                  e.target.value = ''
                }}
              />
            </label>
          )}

          {files.length > 0 && (
            <ul className="mt-2 border border-zinc-800 rounded divide-y divide-zinc-800/60">
              {files.map((f) => (
                <li key={`${f.name}-${f.size}`} className="flex items-center justify-between px-3 py-2 gap-3">
                  <span className="text-sm text-zinc-300 truncate">{f.name}</span>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-[11px] text-zinc-600">{Math.max(1, Math.round(f.size / 1024))} KB</span>
                    <button
                      type="button"
                      aria-label={`Remove ${f.name}`}
                      onClick={() => {
                        setFileError(null)
                        setFiles((prev) => prev.filter((p) => p !== f))
                      }}
                      className="text-zinc-600 hover:text-red-400 transition-colors"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}

          {fileError && <p className="text-sm text-red-400 mt-2">{fileError}</p>}
        </div>

        {/* Honeypot — hidden from real users; bots fill this. Implausible name
            (not company_name/email) so browser autofill won't populate it for a
            real reporter and silently drop their report. */}
        <input
          type="text"
          name="internal_ref"
          tabIndex={-1}
          autoComplete="off"
          value={honeypot}
          onChange={(e) => setHoneypot(e.target.value)}
          className="hidden"
          aria-hidden="true"
        />

        <SubmissionDisclaimer />

        {error && <p className="text-sm text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={stage === 'submitting' || !canSubmit}
          className="w-full bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white font-medium py-2.5 rounded transition-colors flex items-center justify-center"
        >
          {stage === 'submitting' ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Submit report'}
        </button>
      </form>
    </Shell>
  )
}

function Field({
  label,
  optional,
  hint,
  children,
}: {
  label: string
  optional?: boolean
  hint?: string
  children: React.ReactNode
}) {
  return (
    <label className="block">
      <span className="text-xs text-zinc-400 uppercase tracking-wide">
        {label}
        {optional && <span className="ml-1 normal-case tracking-normal text-zinc-600">(optional)</span>}
      </span>
      {hint && <span className="block text-[11px] text-zinc-500 mt-0.5">{hint}</span>}
      {children}
    </label>
  )
}

function Shell({ children, wide }: { children: React.ReactNode; wide?: boolean }) {
  return (
    <div className="min-h-screen bg-[#0c0c0e] flex items-center justify-center px-4 py-10">
      <div className={`${wide ? 'max-w-xl' : 'max-w-md'} w-full text-center`}>{children}</div>
    </div>
  )
}
