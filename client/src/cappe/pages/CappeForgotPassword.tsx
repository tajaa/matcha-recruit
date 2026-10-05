import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2, MailCheck } from 'lucide-react'
import { CappeApiError, cappePublicPost } from '../api'
import { ui } from '../components/ui'

const SHELL = 'flex min-h-screen items-center justify-center bg-zinc-950 bg-[radial-gradient(60rem_40rem_at_50%_-10%,rgba(198,241,107,0.08),transparent)] px-4'

// Request a password-reset link (/cappe/forgot-password). The endpoint answers
// the same whether or not the address has an account, so the confirmation is
// worded conditionally.
export default function CappeForgotPassword() {
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sentTo, setSentTo] = useState<string | null>(null)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await cappePublicPost('/auth/forgot-password', { email: email.trim() })
      setSentTo(email.trim())
    } catch (err) {
      setError(
        err instanceof CappeApiError && err.status === 429
          ? 'Too many requests just now. Wait a minute, then try again.'
          : err instanceof Error ? err.message : 'Something went wrong.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  if (sentTo) {
    return (
      <div className={SHELL}>
        <div className="w-full max-w-sm text-center">
          <span className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-lime-300/15 text-lime-300">
            <MailCheck className="h-6 w-6" />
          </span>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">Check your email</h1>
          <p className="mt-2 text-sm leading-relaxed text-zinc-400">
            If <span className="text-zinc-200">{sentTo}</span> has a Gummfit account, a reset link is on its
            way. It works once and expires in 60 minutes.
          </p>
          <p className="mt-4 text-xs leading-relaxed text-zinc-500">
            Nothing after a few minutes? Check spam, or{' '}
            <button type="button" onClick={() => setSentTo(null)} className="font-medium text-lime-400 hover:text-lime-300">
              try a different address
            </button>
            .
          </p>
          <Link to="/cappe/login" className="mt-6 inline-block text-sm font-medium text-lime-400 hover:text-lime-300">
            Back to sign in
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className={SHELL}>
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">Reset your password</h1>
          <p className="mt-1 text-sm text-zinc-400">Enter the email you signed up with and we'll send you a link.</p>
        </div>
        <form onSubmit={onSubmit} className="space-y-4 rounded-2xl border border-zinc-800 bg-zinc-900 p-6 shadow-xl shadow-black/40">
          <div>
            <label htmlFor="cappe-forgot-email" className={ui.label}>Email</label>
            <input
              id="cappe-forgot-email"
              type="email"
              required
              autoFocus
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={ui.input}
              placeholder="you@example.com"
            />
          </div>
          {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
          <button
            type="submit"
            disabled={submitting}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-lime-400 px-4 py-2 text-sm font-semibold text-zinc-950 transition-colors hover:bg-lime-300 disabled:opacity-60"
          >
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            Send reset link
          </button>
        </form>
        <p className="mt-4 text-center text-sm text-zinc-500">
          Remembered it?{' '}
          <Link to="/cappe/login" className="font-medium text-lime-400 hover:text-lime-300">Sign in</Link>
        </p>
      </div>
    </div>
  )
}
