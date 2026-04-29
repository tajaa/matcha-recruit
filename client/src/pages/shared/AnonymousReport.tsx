import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, CheckCircle2, XCircle, AlertTriangle } from 'lucide-react'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

type Stage = 'validating' | 'invalid' | 'used' | 'form' | 'submitting' | 'submitted' | 'error'

export default function AnonymousReport() {
  const { token } = useParams<{ token: string }>()
  const [stage, setStage] = useState<Stage>('validating')
  const [error, setError] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
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
    if (title.trim().length < 3 || description.trim().length < 10) return
    setStage('submitting')
    setError(null)
    try {
      const res = await fetch(`${BASE}/report/${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: title.trim(),
          description: description.trim(),
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
    <Shell>
      <h1 className="text-lg font-semibold text-zinc-100 mb-1">File an anonymous incident report</h1>
      <p className="text-sm text-zinc-400 mb-5">Your identity is not collected. HR will review your submission.</p>
      <form onSubmit={handleSubmit} className="space-y-4 text-left">
        <label className="block">
          <span className="text-xs text-zinc-400 uppercase tracking-wide">Title</span>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={255}
            className="mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700"
          />
        </label>
        <label className="block">
          <span className="text-xs text-zinc-400 uppercase tracking-wide">Description</span>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={6}
            maxLength={10000}
            className="mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700"
          />
        </label>

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
          disabled={stage === 'submitting' || title.trim().length < 3 || description.trim().length < 10}
          className="w-full bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white font-medium py-2.5 rounded transition-colors flex items-center justify-center"
        >
          {stage === 'submitting' ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Submit report'}
        </button>
      </form>
    </Shell>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-[#0c0c0e] flex items-center justify-center px-4 py-10">
      <div className="max-w-md w-full text-center">{children}</div>
    </div>
  )
}
