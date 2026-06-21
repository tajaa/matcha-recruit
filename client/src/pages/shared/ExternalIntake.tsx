import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, CheckCircle2, XCircle, ShieldCheck } from 'lucide-react'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

type Stage = 'validating' | 'invalid' | 'closed' | 'form' | 'submitting' | 'submitted'
type Factor = { key: string; label: string }

const OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'unknown', label: 'Not sure' },
  { value: 'in_place', label: 'Yes, in place' },
  { value: 'partial', label: 'Partially' },
  { value: 'gap', label: 'No / not yet' },
]

// Public, unauthenticated EPL questionnaire reached via a broker's shareable link
// (/intake/external/:token). The prospect self-rates each employment-practices
// control; answers feed the broker's off-platform EPL score without onboarding.
export default function ExternalIntake() {
  const { token } = useParams<{ token: string }>()
  const [stage, setStage] = useState<Stage>('validating')
  const [clientName, setClientName] = useState<string | null>(null)
  const [factors, setFactors] = useState<Factor[]>([])
  const [answers, setAnswers] = useState<Record<string, string>>({})

  useEffect(() => {
    if (!token) { setStage('invalid'); return }
    fetch(`${BASE}/external-intake/${token}`)
      .then(async (res) => {
        if (!res.ok) { setStage('invalid'); return }
        const data = await res.json()
        if (data.state !== 'open') { setClientName(data.client_name); setStage('closed'); return }
        setClientName(data.client_name)
        setFactors(data.factors ?? [])
        setAnswers(Object.fromEntries((data.factors ?? []).map((f: Factor) => [f.key, 'unknown'])))
        setStage('form')
      })
      .catch(() => setStage('invalid'))
  }, [token])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setStage('submitting')
    try {
      const res = await fetch(`${BASE}/external-intake/${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ epl: answers }),
      })
      setStage(res.ok ? 'submitted' : 'invalid')
    } catch { setStage('invalid') }
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center p-4">
      <div className="w-full max-w-xl">
        {stage === 'validating' && (
          <div className="flex items-center justify-center h-40"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>
        )}

        {stage === 'invalid' && (
          <div className="text-center py-16">
            <XCircle className="h-10 w-10 text-red-400 mx-auto mb-3" />
            <h1 className="text-lg font-semibold">Link not valid</h1>
            <p className="text-sm text-zinc-500 mt-1">This intake link is invalid or could not be loaded.</p>
          </div>
        )}

        {stage === 'closed' && (
          <div className="text-center py-16">
            <CheckCircle2 className="h-10 w-10 text-emerald-400 mx-auto mb-3" />
            <h1 className="text-lg font-semibold">This link is already complete</h1>
            <p className="text-sm text-zinc-500 mt-1">Thanks — your responses have been recorded, or the link has expired.</p>
          </div>
        )}

        {stage === 'submitted' && (
          <div className="text-center py-16">
            <CheckCircle2 className="h-10 w-10 text-emerald-400 mx-auto mb-3" />
            <h1 className="text-lg font-semibold">Thank you</h1>
            <p className="text-sm text-zinc-500 mt-1">Your responses have been sent to your broker.</p>
          </div>
        )}

        {(stage === 'form' || stage === 'submitting') && (
          <form onSubmit={submit} className="space-y-5">
            <div>
              <div className="flex items-center gap-2 text-emerald-400 mb-1"><ShieldCheck className="h-5 w-5" /><span className="text-[11px] uppercase tracking-widest font-bold">Risk questionnaire</span></div>
              <h1 className="text-2xl font-semibold tracking-tight">{clientName ?? 'Your company'}</h1>
              <p className="text-sm text-zinc-500 mt-1">Your broker is preparing your employment-practices-liability (EPL) profile. Tell us where each control stands — it helps them present your business well to insurers. Takes ~2 minutes.</p>
            </div>

            <div className="space-y-2">
              {factors.map((f) => (
                <div key={f.key} className="flex items-center gap-3 py-2 border-b border-zinc-800/40">
                  <span className="text-sm text-zinc-200 flex-1">{f.label}</span>
                  <select
                    value={answers[f.key] ?? 'unknown'}
                    onChange={(e) => setAnswers((a) => ({ ...a, [f.key]: e.target.value }))}
                    className="bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 focus:outline-none focus:border-zinc-500"
                  >
                    {OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
              ))}
            </div>

            <button type="submit" disabled={stage === 'submitting'} className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-medium rounded-lg px-4 py-2.5 disabled:opacity-50">
              {stage === 'submitting' ? 'Sending…' : 'Submit responses'}
            </button>
            <p className="text-[11px] text-zinc-600 text-center">Shared securely with your broker. No account needed.</p>
          </form>
        )}
      </div>
    </div>
  )
}
