import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Video, CheckCircle2, XCircle, AlertTriangle } from 'lucide-react'
import { Logo } from '../../components/ui'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

type PageState = 'loading' | 'ready' | 'in_progress' | 'starting' | 'active' | 'completed' | 'not_found' | 'expired' | 'error'

interface InviteInfo {
  candidate_name: string
  position_title: string
  company_name: string
  status: string
}

export default function CandidateInterview() {
  const { token } = useParams<{ token: string }>()
  const [state, setState] = useState<PageState>('loading')
  const [info, setInfo] = useState<InviteInfo | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!token) { setState('not_found'); return }
    fetch(`${BASE}/candidate-interview/${token}`)
      .then(async (res) => {
        if (res.status === 404) { setState('not_found'); return }
        if (res.status === 410) { setState('expired'); return }
        if (!res.ok) { setState('error'); setError(`Unexpected error (${res.status})`); return }
        const data = await res.json()
        setInfo(data)
        if (data.status === 'completed' || data.status === 'analyzed') setState('completed')
        else if (data.status === 'in_progress') setState('in_progress')
        else setState('ready')
      })
      .catch(() => { setState('error'); setError('Network error. Please check your connection.') })
  }, [token])

  async function handleStart() {
    if (!token) return
    setState('starting')
    try {
      const res = await fetch(`${BASE}/candidate-interview/${token}/start`, { method: 'POST' })
      if (!res.ok) {
        const body = await res.json().catch(() => null)
        setError(body?.detail || `Failed to start (${res.status})`)
        setState('error')
        return
      }
      const data = await res.json()
      if (data.status === 'completed') { setState('completed'); return }
      setState('active')
    } catch {
      setError('Network error. Please try again.')
      setState('error')
    }
  }

  return (
    <div className="min-h-screen bg-zinc-900 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <Logo className="justify-center mb-8 grayscale" />

        <div className="border border-zinc-800 rounded-xl p-6">
          {state === 'loading' && (
            <div className="flex flex-col items-center py-6 gap-3">
              <Loader2 size={24} className="animate-spin text-zinc-500" />
              <p className="text-sm text-zinc-500">Loading interview details...</p>
            </div>
          )}

          {(state === 'ready' || state === 'in_progress') && info && (
            <>
              <div className="flex items-center gap-2 mb-4">
                <Video size={18} className="text-emerald-400" />
                <h1 className="text-lg font-semibold text-zinc-100">
                  Screening Interview
                </h1>
              </div>
              <div className="space-y-2 mb-5">
                <p className="text-sm text-zinc-300">
                  Hi <span className="font-medium text-zinc-100">{info.candidate_name}</span>,
                </p>
                <p className="text-sm text-zinc-400">
                  You've been invited to a screening interview for{' '}
                  <span className="text-zinc-200 font-medium">{info.position_title}</span> at{' '}
                  <span className="text-zinc-200 font-medium">{info.company_name}</span>.
                </p>
                <p className="text-sm text-zinc-500">
                  This is an AI-powered voice interview that takes about 10-15 minutes. No account or download required.
                </p>
              </div>
              <button
                onClick={handleStart}
                className="w-full py-2.5 text-sm font-medium rounded-lg transition-colors bg-emerald-600 hover:bg-emerald-500 text-white"
              >
                {state === 'in_progress' ? 'Rejoin Interview' : 'Begin Interview'}
              </button>
            </>
          )}

          {state === 'starting' && (
            <div className="flex flex-col items-center py-6 gap-3">
              <Loader2 size={24} className="animate-spin text-emerald-400" />
              <p className="text-sm text-zinc-400">Starting your interview...</p>
            </div>
          )}

          {state === 'active' && info && (
            <div className="text-center py-4">
              <div className="w-12 h-12 rounded-full bg-emerald-900/40 border border-emerald-700/40 flex items-center justify-center mx-auto mb-4">
                <Video size={20} className="text-emerald-400" />
              </div>
              <h2 className="text-lg font-semibold text-zinc-100 mb-2">Interview Started</h2>
              <p className="text-sm text-zinc-400 mb-1">
                Your interview session for <span className="text-zinc-200">{info.position_title}</span> is now active.
              </p>
              <p className="text-xs text-zinc-500 mt-3">
                The voice interview experience is coming soon. Your session has been recorded as started.
              </p>
            </div>
          )}

          {state === 'completed' && (
            <div className="text-center py-4">
              <CheckCircle2 size={32} className="text-emerald-400 mx-auto mb-3" />
              <h2 className="text-lg font-semibold text-zinc-100 mb-2">Interview Complete</h2>
              <p className="text-sm text-zinc-400">
                Thank you for completing your interview. The hiring team will review your responses and follow up.
              </p>
            </div>
          )}

          {state === 'not_found' && (
            <div className="text-center py-4">
              <XCircle size={32} className="text-red-400 mx-auto mb-3" />
              <h2 className="text-lg font-semibold text-zinc-100 mb-2">Invalid Link</h2>
              <p className="text-sm text-zinc-400">
                This interview link is invalid or has expired. Please contact the hiring team for a new link.
              </p>
            </div>
          )}

          {state === 'expired' && (
            <div className="text-center py-4">
              <AlertTriangle size={32} className="text-amber-400 mx-auto mb-3" />
              <h2 className="text-lg font-semibold text-zinc-100 mb-2">Interview Cancelled</h2>
              <p className="text-sm text-zinc-400">
                This interview has been cancelled. Please contact the hiring team if you believe this is an error.
              </p>
            </div>
          )}

          {state === 'error' && (
            <div className="text-center py-4">
              <XCircle size={32} className="text-red-400 mx-auto mb-3" />
              <h2 className="text-lg font-semibold text-zinc-100 mb-2">Something Went Wrong</h2>
              <p className="text-sm text-red-400 mb-4">{error}</p>
              <button
                onClick={() => window.location.reload()}
                className="text-sm text-zinc-400 underline hover:text-zinc-200"
              >
                Try again
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
