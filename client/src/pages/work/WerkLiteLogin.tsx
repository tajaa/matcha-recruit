import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { Hash, Loader2 } from 'lucide-react'
import { api } from '../../api/client'
import { invalidateMeCache, useMe } from '../../hooks/useMe'

type LoginResponse = {
  access_token: string
  refresh_token: string
  user: { role: string }
}

// Dedicated Werk Lite login. Unlike the main Matcha login (which role-routes
// admins→/app, employees→/portal), this is the whole-company entry point: every
// company member — business admins (role='client') AND employees (role=
// 'employee') — signs in here and lands on /werk-lite. Access to the surface
// itself is still gated by the `werk_lite` company feature flag (FeatureGate),
// so a user whose company lacks it sees the upsell. Same /api/auth/login +
// shared matcha tokens — no separate identity.
export default function WerkLiteLogin() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const nextParam = searchParams.get('next')
  const { me, loading: meLoading } = useMe()

  const safeNext = nextParam && nextParam.startsWith('/werk-lite') && !nextParam.startsWith('//')
    ? nextParam
    : '/werk-lite'

  // Already signed in → straight into the app.
  useEffect(() => {
    if (!meLoading && me) navigate(safeNext, { replace: true })
  }, [meLoading, me, navigate, safeNext])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await api.post<LoginResponse>('/auth/login', { email, password })
      localStorage.setItem('matcha_access_token', res.access_token)
      localStorage.setItem('matcha_refresh_token', res.refresh_token)
      invalidateMeCache()
      navigate(safeNext, { replace: true })
    } catch {
      setError('Invalid email or password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 bg-w-bg text-w-text">
      <div className="w-full max-w-sm">
        {/* Wordmark */}
        <div className="flex items-center justify-center gap-2 mb-8">
          <span className="flex items-center justify-center w-9 h-9 rounded-lg bg-w-accent text-white">
            <Hash size={18} />
          </span>
          <span className="text-2xl font-semibold tracking-tight">Werk Lite</span>
        </div>

        <div className="rounded-2xl border border-w-line bg-w-surface/60 p-7">
          <h1 className="text-xl font-semibold mb-1">Sign in</h1>
          <p className="text-sm text-w-dim mb-6">Your team's chat, calls, and boards.</p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-[11px] uppercase tracking-wider text-w-dim mb-1.5">Email</label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                className="w-full px-3 py-2.5 rounded-lg bg-w-surface2 border border-w-line text-sm text-white placeholder:text-w-dim outline-none focus:border-w-accent"
              />
            </div>
            <div>
              <label htmlFor="password" className="block text-[11px] uppercase tracking-wider text-w-dim mb-1.5">Password</label>
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full px-3 py-2.5 rounded-lg bg-w-surface2 border border-w-line text-sm text-white placeholder:text-w-dim outline-none focus:border-w-accent"
              />
            </div>
            {error && (
              <div className="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-md px-3 py-2">
                {error}
              </div>
            )}
            <button
              type="submit"
              disabled={loading}
              className="w-full h-11 rounded-lg bg-w-accent hover:bg-w-accent-hi text-white text-sm font-medium transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading ? <><Loader2 size={15} className="animate-spin" /> Signing in…</> : 'Sign in'}
            </button>
            <div className="text-center">
              <Link to="/reset-password" className="text-xs text-w-dim hover:text-w-text transition-colors">
                Forgot password?
              </Link>
            </div>
          </form>
        </div>

        <p className="mt-6 text-center text-xs text-w-faint">
          Part of a Matcha company. Ask your admin for an invite if you don't have an account.
        </p>
      </div>
    </div>
  )
}
