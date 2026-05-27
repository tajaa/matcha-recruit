import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, CheckCircle2, XCircle, AlertTriangle, MapPin } from 'lucide-react'
import { IRPersonMultiSelect } from '../../components/ir/IRPersonMultiSelect'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

const inputCls =
  'mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700'

type Stage = 'validating' | 'invalid' | 'used' | 'form' | 'submitting' | 'submitted' | 'error'

type IntakeInfo = {
  company_name: string | null
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
        if (res.status === 410) setStage('used')
        else setStage('invalid')
      })
      .catch(() => setStage('invalid'))
  }, [token])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!reportedByName.trim() || description.trim().length < 10) return
    setStage('submitting')
    setError(null)
    try {
      const res = await fetch(`${BASE}/intake/${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          description: description.trim(),
          reported_by_name: reportedByName.trim(),
          occurred_at: occurredAt.trim() || null,
          witnesses,
          corrective_actions: nextSteps.trim() || null,
          company_name: honeypot,
        }),
      })
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
        <h1 className="text-lg font-semibold text-zinc-100 mb-2">Link already used</h1>
        <p className="text-sm text-zinc-400">This reporting link has already been submitted. Contact your HR team for a new one.</p>
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

        {/* Honeypot — hidden from real users; bots fill this */}
        <input
          type="text"
          name="company_name"
          tabIndex={-1}
          autoComplete="off"
          value={honeypot}
          onChange={(e) => setHoneypot(e.target.value)}
          className="hidden"
          aria-hidden="true"
        />

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
