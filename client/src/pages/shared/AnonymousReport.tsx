import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, CheckCircle2, XCircle, AlertTriangle, ShieldCheck } from 'lucide-react'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

type Stage = 'validating' | 'invalid' | 'used' | 'form' | 'submitting' | 'submitted' | 'error'

export default function AnonymousReport() {
  const { token } = useParams<{ token: string }>()
  const [stage, setStage] = useState<Stage>('validating')
  const [error, setError] = useState<string | null>(null)
  const [description, setDescription] = useState('')
  const [occurredAt, setOccurredAt] = useState('')
  const [location, setLocation] = useState('')
  const [involvedParties, setInvolvedParties] = useState('')
  const [contactInfo, setContactInfo] = useState('')
  const [honeypot, setHoneypot] = useState('')

  useEffect(() => {
    if (!token) {
      setStage('invalid')
      return
    }
    fetch(`${BASE}/report/${token}`)
      .then(async (res) => {
        if (res.ok) {
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
    if (description.trim().length < 10) return
    setStage('submitting')
    setError(null)
    try {
      const res = await fetch(`${BASE}/report/${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          description: description.trim(),
          occurred_at: occurredAt.trim() || null,
          location: location.trim() || null,
          involved_parties: involvedParties.trim() || null,
          contact_info: contactInfo.trim() || null,
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

  return (
    <Shell wide>
      <h1 className="text-lg font-semibold text-zinc-100 mb-1 text-center">File an anonymous incident report</h1>
      <p className="text-sm text-zinc-400 mb-4 text-center">Your identity is not collected. HR will review your submission.</p>

      <div className="flex items-start gap-2 bg-zinc-900/60 border border-zinc-800 rounded p-3 mb-5 text-left">
        <ShieldCheck className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
        <p className="text-xs text-zinc-400">
          Fields marked <span className="text-zinc-300">optional</span> can be left blank to preserve anonymity. Including more detail
          helps HR investigate effectively.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4 text-left">
        <Field label="Description">
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={6}
            maxLength={10000}
            placeholder="Describe what happened…"
            className="mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700"
          />
        </Field>

        <Field label="Date and time" optional hint='When did this happen? Free text — e.g. "yesterday at 3pm", "May 1 around noon".'>
          <input
            type="text"
            value={occurredAt}
            onChange={(e) => setOccurredAt(e.target.value)}
            maxLength={255}
            placeholder="yesterday around 4pm"
            className="mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700"
          />
        </Field>

        <Field label="Location" optional hint="Building, area, or address. Skip if it would identify you.">
          <input
            type="text"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            maxLength={255}
            className="mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700"
          />
        </Field>

        <Field label="Names of all involved" optional hint="Skip if it would identify you. HR may have limited ability to resolve without this.">
          <textarea
            value={involvedParties}
            onChange={(e) => setInvolvedParties(e.target.value)}
            rows={2}
            maxLength={2000}
            className="mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700"
          />
        </Field>

        <Field label="Contact for follow-up" optional hint="Email or phone. Provide only if you'd like HR to follow up; leave blank for full anonymity.">
          <input
            type="text"
            value={contactInfo}
            onChange={(e) => setContactInfo(e.target.value)}
            maxLength={255}
            className="mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700"
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
          disabled={stage === 'submitting' || description.trim().length < 10}
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
