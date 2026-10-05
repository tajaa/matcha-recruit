import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Loader2, CheckCircle2, XCircle } from 'lucide-react'
import { CappeApiError, cappePublicPost, setCappeTokens } from '../api'
import { invalidateCappeMeCache } from '../hooks/useCappeMe'
import { creatorPaths } from '../creators/creatorPaths'
import ResendVerification from '../components/ResendVerification'
import { billingStartPath } from './CappeBilling/paths'
import type { CappeVerifyResponse } from '../types'

const postAuthHome = (t?: string) => (t === 'creator' ? creatorPaths.home : '/cappe/sites')

// Landing for the emailed confirmation link (/cappe/verify?token=…). Exchanges
// the token for a session and drops the user straight into their dashboard.
export default function CappeVerify() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const token = params.get('token')
  const [state, setState] = useState<'verifying' | 'ok' | 'expired' | 'error'>(token ? 'verifying' : 'error')
  const [message, setMessage] = useState(token ? '' : 'This confirmation link is missing its token.')
  const ran = useRef(false)

  useEffect(() => {
    if (ran.current) return // StrictMode double-invoke guard — token is single-use.
    ran.current = true
    if (!token) return
    cappePublicPost<CappeVerifyResponse>('/auth/verify', { token })
      .then((res) => {
        setCappeTokens(res.access_token, res.refresh_token)
        invalidateCappeMeCache()
        setState('ok')
        // A plan picked on the pricing page continues into checkout.
        const next = res.intended_plan && res.account?.account_type !== 'creator'
          ? billingStartPath(res.intended_plan, res.intended_interval)
          : postAuthHome(res.account?.account_type)
        setTimeout(() => navigate(next, { replace: true }), 900)
      })
      .catch((err) => {
        // An expired link belongs to a real, still-unconfirmed account, so the
        // useful next step is a new link, not the sign-in page (which would
        // refuse them).
        setState(err instanceof CappeApiError && err.code === 'verification_expired' ? 'expired' : 'error')
        setMessage(err instanceof Error ? err.message : 'We couldn’t confirm this link.')
      })
  }, [token, navigate])

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
        {state === 'expired' && (
          <>
            <XCircle className="mx-auto h-10 w-10 text-amber-400" />
            <h1 className="mt-4 text-2xl font-semibold tracking-tight text-zinc-50">This link has expired</h1>
            <p className="mt-2 text-sm leading-relaxed text-zinc-400">
              Confirmation links work for 24 hours. Enter your email and we'll send a new one.
            </p>
            <div className="mt-6 rounded-xl border border-zinc-800 bg-zinc-900 p-4">
              <ResendVerification label="Send a new link" />
            </div>
            <Link to="/cappe/login" className="mt-6 inline-block text-sm font-medium text-lime-400 hover:text-lime-300">
              Back to sign in
            </Link>
          </>
        )}
        {state === 'error' && (
          <>
            <XCircle className="mx-auto h-10 w-10 text-red-400" />
            <h1 className="mt-4 text-2xl font-semibold tracking-tight text-zinc-50">Link didn't work</h1>
            <p className="mt-2 text-sm leading-relaxed text-zinc-400">
              {message} If you already confirmed your email, just sign in.
            </p>
            <Link
              to="/cappe/login"
              className="mt-6 inline-block rounded-lg bg-lime-400 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-lime-300"
            >
              Go to sign in
            </Link>
            <div className="mt-6 rounded-xl border border-zinc-800 bg-zinc-900 p-4">
              <p className="mb-3 text-left text-xs text-zinc-500">Still need to confirm? Get a new link:</p>
              <ResendVerification label="Send a new link" />
            </div>
          </>
        )}
      </div>
    </div>
  )
}
