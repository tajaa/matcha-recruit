import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { CheckCircle2, Loader2, XCircle } from 'lucide-react'
import { CappeApiError, cappePublicPost, clearCappeTokens } from '../api'
import { invalidateCappeMeCache } from '../hooks/useCappeMe'
import { ui } from '../components/ui'

const SHELL = 'flex min-h-screen items-center justify-center bg-zinc-950 bg-[radial-gradient(60rem_40rem_at_50%_-10%,rgba(198,241,107,0.08),transparent)] px-4'
const PRIMARY = 'inline-block rounded-lg bg-lime-400 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-lime-300'

// The emailed link is /cappe/reset-password#token=…: the secret rides in the
// fragment so it is never sent to the server in a URL.
function tokenFromHash(hash: string): string {
  return new URLSearchParams(hash.replace(/^#/, '')).get('token') ?? ''
}

export default function CappeResetPassword() {
  const token = tokenFromHash(useLocation().hash)
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // 'dead' = the link itself is no good (missing, used, expired): a new one is
  // the only way forward, so the form is replaced rather than left to fail again.
  const [state, setState] = useState<'form' | 'done' | 'dead'>(token ? 'form' : 'dead')
  const [deadMessage, setDeadMessage] = useState('This reset link is incomplete. Request a new one.')

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (password.length < 8) { setError('Password must be at least 8 characters.'); return }
    if (password !== confirm) { setError('Those passwords don’t match.'); return }
    setSubmitting(true)
    try {
      await cappePublicPost('/auth/reset-password', { token, password })
      // Every session was revoked server-side; drop this tab's stale one too.
      clearCappeTokens()
      invalidateCappeMeCache()
      setState('done')
    } catch (err) {
      if (err instanceof CappeApiError && (err.code === 'reset_invalid' || err.code === 'reset_expired')) {
        setDeadMessage(err.message)
        setState('dead')
      } else {
        setError(err instanceof Error ? err.message : 'Something went wrong.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (state === 'done') {
    return (
      <div className={SHELL}>
        <div className="w-full max-w-sm text-center">
          <CheckCircle2 className="mx-auto h-10 w-10 text-lime-400" />
          <h1 className="mt-4 text-2xl font-semibold tracking-tight text-zinc-50">Password updated</h1>
          <p className="mt-2 text-sm leading-relaxed text-zinc-400">
            You've been signed out everywhere. Sign in with your new password.
          </p>
          <Link to="/cappe/login" className={`mt-6 ${PRIMARY}`}>Sign in</Link>
        </div>
      </div>
    )
  }

  if (state === 'dead') {
    return (
      <div className={SHELL}>
        <div className="w-full max-w-sm text-center">
          <XCircle className="mx-auto h-10 w-10 text-amber-400" />
          <h1 className="mt-4 text-2xl font-semibold tracking-tight text-zinc-50">This link won't work</h1>
          <p className="mt-2 text-sm leading-relaxed text-zinc-400">{deadMessage}</p>
          <Link to="/cappe/forgot-password" className={`mt-6 ${PRIMARY}`}>Get a new link</Link>
        </div>
      </div>
    )
  }

  return (
    <div className={SHELL}>
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">Choose a new password</h1>
        </div>
        <form onSubmit={onSubmit} className="space-y-4 rounded-2xl border border-zinc-800 bg-zinc-900 p-6 shadow-xl shadow-black/40">
          <div>
            <label htmlFor="cappe-reset-password" className={ui.label}>New password</label>
            <input
              id="cappe-reset-password"
              type="password"
              required
              autoFocus
              minLength={8}
              autoComplete="new-password"
              aria-describedby="cappe-reset-password-hint"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={ui.input}
            />
            <p id="cappe-reset-password-hint" className="mt-1 text-xs text-zinc-500">At least 8 characters.</p>
          </div>
          <div>
            <label htmlFor="cappe-reset-confirm" className={ui.label}>Type it again</label>
            <input
              id="cappe-reset-confirm"
              type="password"
              required
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className={ui.input}
            />
          </div>
          {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
          <button
            type="submit"
            disabled={submitting}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-lime-400 px-4 py-2 text-sm font-semibold text-zinc-950 transition-colors hover:bg-lime-300 disabled:opacity-60"
          >
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            Update password
          </button>
        </form>
      </div>
    </div>
  )
}
