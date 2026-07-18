import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { cappePublicPost, setCappeTokens } from '../api'
import { invalidateCappeMeCache } from '../hooks/useCappeMe'
import type { CappeTokenResponse } from '../types'

export default function CappeLogin() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [needsVerify, setNeedsVerify] = useState(false)
  const [resent, setResent] = useState(false)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setNeedsVerify(false)
    setSubmitting(true)
    try {
      const res = await cappePublicPost<CappeTokenResponse>('/auth/login', { email, password })
      setCappeTokens(res.access_token, res.refresh_token)
      invalidateCappeMeCache()
      navigate('/cappe/sites', { replace: true })
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Something went wrong.'
      // Backend's unverified-account 403 carries "confirm your email".
      if (/confirm your email/i.test(msg)) setNeedsVerify(true)
      setError(msg)
    } finally {
      setSubmitting(false)
    }
  }

  async function resend() {
    setResent(true)
    try {
      await cappePublicPost('/auth/resend-verification', { email })
    } catch {
      // 202 regardless; ignore.
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 bg-[radial-gradient(60rem_40rem_at_50%_-10%,rgba(198,241,107,0.08),transparent)] px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <span className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-lime-300 to-lime-500 text-lg font-bold text-zinc-950 shadow-lg shadow-lime-500/20">
            G
          </span>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">Sign in to Gummfit</h1>
        </div>

        <form onSubmit={onSubmit} className="space-y-4 rounded-2xl border border-zinc-800 bg-zinc-900 p-6 shadow-xl shadow-black/40">
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-300">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-300">Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
            />
          </div>

          {error && <p className="text-sm text-red-400">{error}</p>}
          {needsVerify && (
            <button
              type="button"
              onClick={resend}
              disabled={resent}
              className="text-sm font-medium text-lime-400 hover:text-lime-300 disabled:opacity-60"
            >
              {resent ? 'Confirmation email sent ✓' : 'Resend confirmation email'}
            </button>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-lime-400 px-4 py-2 text-sm font-semibold text-zinc-950 transition-colors hover:bg-lime-300 disabled:opacity-60"
          >
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            Sign in
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-zinc-500">
          New to Gummfit?{' '}
          <Link to="/cappe/website-setup" className="font-medium text-lime-400 hover:text-lime-300">
            Create an account
          </Link>
        </p>
      </div>
    </div>
  )
}
