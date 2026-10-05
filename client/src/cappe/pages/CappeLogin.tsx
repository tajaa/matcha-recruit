import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { CappeApiError, cappePublicPost, clearCappeTokens, setCappeTokens } from '../api'
import { invalidateCappeMeCache } from '../hooks/useCappeMe'
import { creatorPaths } from '../creators/creatorPaths'
import ResendVerification from '../components/ResendVerification'
import type { CappeTokenResponse } from '../types'

const postAuthHome = (t?: string) => (t === 'creator' ? creatorPaths.home : '/cappe/sites')

export default function CappeLogin({ creatorOnly = false, brandOnly = false }: { creatorOnly?: boolean; brandOnly?: boolean }) {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [needsVerify, setNeedsVerify] = useState(false)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setNeedsVerify(false)
    setSubmitting(true)
    try {
      const res = await cappePublicPost<CappeTokenResponse>('/auth/login', { email, password })
      setCappeTokens(res.access_token, res.refresh_token)
      invalidateCappeMeCache()
      if (creatorOnly && res.account?.account_type !== 'creator') {
        clearCappeTokens()
        setError('This sign-in is for Gummfit Creator accounts. Use your creator account, or create a creator profile first.')
        return
      }
      if (brandOnly && res.account?.account_type !== 'business') {
        clearCappeTokens()
        setError('This sign-in is for brand accounts that collaborate with Gummfit Creators.')
        return
      }
      navigate(creatorOnly ? creatorPaths.home : brandOnly ? creatorPaths.brandHome : postAuthHome(res.account?.account_type), { replace: true })
    } catch (err) {
      if (err instanceof CappeApiError && err.code === 'email_unverified') setNeedsVerify(true)
      setError(err instanceof Error ? err.message : 'Something went wrong.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 bg-[radial-gradient(60rem_40rem_at_50%_-10%,rgba(198,241,107,0.08),transparent)] px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <span className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-lime-300 to-lime-500 text-lg font-bold text-zinc-950 shadow-lg shadow-lime-500/20">
            G
          </span>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">
            Sign in to {creatorOnly ? 'Gummfit Creators' : brandOnly ? 'Gummfit for Brands' : 'Gummfit'}
          </h1>
        </div>

        <form onSubmit={onSubmit} className="space-y-4 rounded-2xl border border-zinc-800 bg-zinc-900 p-6 shadow-xl shadow-black/40">
          <div>
            <label htmlFor="cappe-login-email" className="mb-1 block text-sm font-medium text-zinc-300">Email</label>
            <input
              id="cappe-login-email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label htmlFor="cappe-login-password" className="mb-1 block text-sm font-medium text-zinc-300">Password</label>
            <input
              id="cappe-login-password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
            />
          </div>

          {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
          {needsVerify && <ResendVerification email={email} />}

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
          {creatorOnly ? 'New to Gummfit Creators?' : brandOnly ? 'New to Gummfit for Brands?' : 'New to Gummfit?'}{' '}
          <Link to={creatorOnly ? creatorPaths.signup : brandOnly ? creatorPaths.brandSignup : '/cappe/website-setup'} className="font-medium text-lime-400 hover:text-lime-300">
            {creatorOnly ? 'Create your creator profile' : brandOnly ? 'Create a brand profile' : 'Create an account'}
          </Link>
        </p>
        {(creatorOnly || brandOnly) && (
          <p className="mt-3 text-center text-sm text-zinc-500">
            {creatorOnly ? 'Are you a brand?' : 'Are you a creator?'}{' '}
            <Link to={creatorOnly ? creatorPaths.brandLogin : creatorPaths.login} className="font-medium text-lime-400 hover:text-lime-300">
              {creatorOnly ? 'Brand sign in' : 'Creator sign in'}
            </Link>
          </p>
        )}
        {!creatorOnly && !brandOnly && (
          <div className="mt-5 flex items-center justify-center gap-3 text-xs text-zinc-500">
            <Link to={creatorPaths.login} className="font-medium text-lime-400 hover:text-lime-300">Creator sign in</Link>
            <span aria-hidden="true">·</span>
            <Link to={creatorPaths.brandLogin} className="font-medium text-lime-400 hover:text-lime-300">Brand sign in</Link>
          </div>
        )}
      </div>
    </div>
  )
}
