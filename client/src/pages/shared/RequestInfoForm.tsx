import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, CheckCircle2, XCircle, AlertTriangle } from 'lucide-react'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

const textareaCls =
  'mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700'

type Stage = 'validating' | 'invalid' | 'used' | 'form' | 'submitting' | 'submitted' | 'error'

type InfoRequestInfo = {
  company_name: string | null
  incident_number: string | null
  questions: string[]
}

// Public, unauthenticated form reached via an IR Copilot "Request More Info"
// email (/request-info/:token). Single-use, scoped to one incident: answers
// land back in that incident's Copilot transcript for the admin to review —
// they never write directly into the incident record.
export default function RequestInfoForm() {
  const { token } = useParams<{ token: string }>()
  const [stage, setStage] = useState<Stage>('validating')
  const [info, setInfo] = useState<InfoRequestInfo | null>(null)
  const [answers, setAnswers] = useState<string[]>([])
  const [honeypot, setHoneypot] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!token) {
      setStage('invalid')
      return
    }
    fetch(`${BASE}/request-info/${token}`)
      .then(async (res) => {
        if (res.ok) {
          const data = (await res.json().catch(() => null)) as InfoRequestInfo | null
          setInfo(data)
          setAnswers(new Array(data?.questions.length ?? 0).fill(''))
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
    if (answers.some((a) => a.trim().length === 0)) return
    setStage('submitting')
    setError(null)
    try {
      const res = await fetch(`${BASE}/request-info/${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          answers: answers.map((a) => a.trim()),
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
        <p className="text-sm text-zinc-400">This link is not valid. Contact the sender for a new one.</p>
      </Shell>
    )
  }

  if (stage === 'used') {
    return (
      <Shell>
        <AlertTriangle className="w-10 h-10 text-amber-400 mx-auto mb-3" />
        <h1 className="text-lg font-semibold text-zinc-100 mb-2">Link unavailable</h1>
        <p className="text-sm text-zinc-400">{error ?? 'This link is no longer active. Contact the sender for a new one.'}</p>
      </Shell>
    )
  }

  if (stage === 'submitted') {
    return (
      <Shell>
        <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto mb-3" />
        <h1 className="text-lg font-semibold text-zinc-100 mb-2">Thanks — answers received</h1>
        <p className="text-sm text-zinc-400">Your response has been sent. Thank you.</p>
      </Shell>
    )
  }

  const canSubmit = answers.length > 0 && answers.every((a) => a.trim().length > 0)

  return (
    <Shell wide>
      <h1 className="text-lg font-semibold text-zinc-100 mb-1 text-center">
        {info?.company_name ? `${info.company_name} needs` : 'A request for'} more information
      </h1>
      <p className="text-sm text-zinc-400 mb-5 text-center">
        {info?.incident_number ? `Regarding incident ${info.incident_number}.` : ''} Your answers go
        directly to their HR team.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4 text-left">
        {(info?.questions || []).map((q, i) => (
          <label key={i} className="block">
            <span className="text-xs text-zinc-400 uppercase tracking-wide">{q}</span>
            <textarea
              value={answers[i] ?? ''}
              onChange={(e) => setAnswers((prev) => prev.map((a, idx) => (idx === i ? e.target.value : a)))}
              rows={3}
              maxLength={4000}
              className={textareaCls}
            />
          </label>
        ))}

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
          {stage === 'submitting' ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Submit answers'}
        </button>
      </form>
    </Shell>
  )
}

function Shell({ children, wide }: { children: React.ReactNode; wide?: boolean }) {
  return (
    <div className="min-h-screen bg-[#0c0c0e] flex items-center justify-center px-4 py-10">
      <div className={`${wide ? 'max-w-xl' : 'max-w-md'} w-full text-center`}>{children}</div>
    </div>
  )
}
