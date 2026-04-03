import { useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { Loader2, CheckCircle } from 'lucide-react'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

export default function ResetPassword() {
  const [params] = useSearchParams()
  const token = params.get('token')

  // Forgot mode (no token) — enter email
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [sending, setSending] = useState(false)

  // Reset mode (has token) — enter new password
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [resetting, setResetting] = useState(false)
  const [resetDone, setResetDone] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleForgot(e: React.FormEvent) {
    e.preventDefault()
    if (!email.trim()) return
    setSending(true)
    try {
      await fetch(`${BASE}/auth/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim() }),
      })
      setSent(true)
    } catch {}
    setSending(false)
  }

  async function handleReset(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (password.length < 8) { setError('Password must be at least 8 characters'); return }
    if (password !== confirm) { setError('Passwords do not match'); return }
    setResetting(true)
    try {
      const res = await fetch(`${BASE}/auth/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, new_password: password }),
      })
      if (!res.ok) {
        const data = await res.json()
        setError(data.detail ?? 'Reset failed')
      } else {
        setResetDone(true)
      }
    } catch {
      setError('Something went wrong')
    }
    setResetting(false)
  }

  return (
    <div className="min-h-screen bg-[#0c0c0e] flex items-center justify-center px-4">
      <div className="max-w-sm w-full">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-semibold text-zinc-100">
            {token ? 'Reset Password' : 'Forgot Password'}
          </h1>
        </div>

        {/* Forgot mode — no token */}
        {!token && !sent && (
          <form onSubmit={handleForgot} className="space-y-4">
            <p className="text-sm text-zinc-500">Enter your email and we'll send you a reset link.</p>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="you@example.com"
              className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-zinc-500 transition-colors"
            />
            <button
              type="submit"
              disabled={sending}
              className="w-full rounded-lg bg-emerald-600 py-2.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-40 transition-colors flex items-center justify-center gap-2"
            >
              {sending && <Loader2 className="w-4 h-4 animate-spin" />}
              {sending ? 'Sending...' : 'Send Reset Link'}
            </button>
            <Link to="/login" className="block text-center text-xs text-zinc-500 hover:text-zinc-300 transition-colors">
              Back to login
            </Link>
          </form>
        )}

        {/* Email sent confirmation */}
        {!token && sent && (
          <div className="text-center space-y-3">
            <CheckCircle className="w-10 h-10 text-emerald-500 mx-auto" />
            <p className="text-sm text-zinc-300">If an account exists for that email, you'll receive a reset link shortly.</p>
            <Link to="/login" className="block text-xs text-zinc-500 hover:text-zinc-300 transition-colors">
              Back to login
            </Link>
          </div>
        )}

        {/* Reset mode — has token */}
        {token && !resetDone && (
          <form onSubmit={handleReset} className="space-y-4">
            <div>
              <label className="block text-xs text-zinc-400 mb-1">New Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                placeholder="At least 8 characters"
                className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-zinc-500 transition-colors"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-400 mb-1">Confirm Password</label>
              <input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
                placeholder="Confirm password"
                className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-zinc-500 transition-colors"
              />
            </div>
            {error && <p className="text-sm text-red-400">{error}</p>}
            <button
              type="submit"
              disabled={resetting}
              className="w-full rounded-lg bg-emerald-600 py-2.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-40 transition-colors flex items-center justify-center gap-2"
            >
              {resetting && <Loader2 className="w-4 h-4 animate-spin" />}
              {resetting ? 'Resetting...' : 'Reset Password'}
            </button>
          </form>
        )}

        {/* Reset success */}
        {token && resetDone && (
          <div className="text-center space-y-3">
            <CheckCircle className="w-10 h-10 text-emerald-500 mx-auto" />
            <p className="text-sm text-zinc-300">Password reset successfully.</p>
            <Link to="/login" className="block text-sm text-emerald-400 hover:text-emerald-300 transition-colors">
              Sign in with your new password
            </Link>
          </div>
        )}
      </div>
    </div>
  )
}
