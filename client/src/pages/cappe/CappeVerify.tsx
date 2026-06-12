import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Loader2, CheckCircle2, XCircle } from 'lucide-react'
import { cappePublicPost, setCappeTokens } from '../../api/cappeClient'
import { invalidateCappeMeCache } from '../../hooks/useCappeMe'
import type { CappeTokenResponse } from '../../types/cappe'

// Landing for the emailed confirmation link (/cappe/verify?token=…). Exchanges
// the token for a session and drops the user straight into their dashboard.
export default function CappeVerify() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [state, setState] = useState<'verifying' | 'ok' | 'error'>('verifying')
  const [message, setMessage] = useState('')
  const ran = useRef(false)

  useEffect(() => {
    if (ran.current) return // StrictMode double-invoke guard — token is single-use.
    ran.current = true
    const token = params.get('token')
    if (!token) {
      setState('error')
      setMessage('This confirmation link is missing its token.')
      return
    }
    cappePublicPost<CappeTokenResponse>('/auth/verify', { token })
      .then((res) => {
        setCappeTokens(res.access_token, res.refresh_token)
        invalidateCappeMeCache()
        setState('ok')
        setTimeout(() => navigate('/cappe/sites', { replace: true }), 900)
      })
      .catch((err) => {
        setState('error')
        setMessage(err instanceof Error ? err.message : 'We couldn’t confirm this link.')
      })
  }, [params, navigate])

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 bg-[radial-gradient(60rem_40rem_at_50%_-10%,rgba(198,241,107,0.08),transparent)] px-4">
      <div className="w-full max-w-sm text-center">
        {state === 'verifying' && (
          <>
            <Loader2 className="mx-auto h-8 w-8 animate-spin text-lime-400" />
            <p className="mt-4 text-sm text-zinc-400">Confirming your email…</p>
          </>
        )}
        {state === 'ok' && (
          <>
            <CheckCircle2 className="mx-auto h-10 w-10 text-lime-400" />
            <h1 className="mt-4 text-2xl font-semibold tracking-tight text-zinc-50">You're in</h1>
            <p className="mt-1 text-sm text-zinc-400">Taking you to your dashboard…</p>
          </>
        )}
        {state === 'error' && (
          <>
            <XCircle className="mx-auto h-10 w-10 text-red-400" />
            <h1 className="mt-4 text-2xl font-semibold tracking-tight text-zinc-50">Link didn't work</h1>
            <p className="mt-2 text-sm leading-relaxed text-zinc-400">{message}</p>
            <Link
              to="/cappe/login"
              className="mt-6 inline-block rounded-lg bg-lime-400 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-lime-300"
            >
              Go to sign in
            </Link>
          </>
        )}
      </div>
    </div>
  )
}
