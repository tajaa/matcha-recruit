import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Logo } from '../components/ui'
import { AsciiHalftone } from '../components/AsciiHalftone'
import { PricingContactModal } from '../components/PricingContactModal'
import { api } from '../api/client'

type LoginResponse = {
  access_token: string
  refresh_token: string
  user: { role: string }
}

const roleRoutes: Record<string, string> = {
  admin: '/admin',
  client: '/app',
  employee: '/portal',
  candidate: '/candidate',
  broker: '/broker',
}

function GrayInput({ label, id, ...props }: React.ComponentProps<'input'> & { label: string }) {
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-zinc-400 mb-1.5 uppercase">
        {label}
      </label>
      <input
        id={id}
        className="w-full rounded-lg border border-zinc-700 bg-zinc-900/80 px-3.5 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-zinc-500 focus:ring-1 focus:ring-zinc-500 transition-colors"
        {...props}
      />
    </div>
  )
}

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [ssoMode, setSsoMode] = useState(false)
  const [ssoLoading, setSsoLoading] = useState(false)
  const [contactOpen, setContactOpen] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await api.post<LoginResponse>('/auth/login', { email, password })
      localStorage.setItem('matcha_access_token', res.access_token)
      localStorage.setItem('matcha_refresh_token', res.refresh_token)
      navigate(roleRoutes[res.user.role] ?? '/app')
    } catch {
      setError('Invalid email or password')
    } finally {
      setLoading(false)
    }
  }

  function handleSSOLogin(e: React.FormEvent) {
    e.preventDefault()
    if (!email) { setError('Enter your email to sign in with SSO'); return }
    setSsoLoading(true)
    setError('')
    // Redirect to the SAML login endpoint — backend handles the IdP redirect
    const baseUrl = import.meta.env.VITE_API_URL || '/api'
    window.location.href = `${baseUrl}/sso/login?email=${encodeURIComponent(email)}`
  }

  return (
    <div className="relative min-h-screen bg-zinc-900 flex items-center justify-center px-4 overflow-x-hidden overflow-y-auto">
      <AsciiHalftone />
      <div className="relative z-10 w-full max-w-sm">
        <Logo className="justify-center mb-10 grayscale" />

        {ssoMode ? (
          <form onSubmit={handleSSOLogin} className="space-y-5">
            <GrayInput
              id="sso-email"
              label="Work Email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
            />
            {error && <p className="text-sm text-red-400">{error}</p>}
            <Button
              type="submit"
              variant="secondary"
              className="w-full uppercase border border-zinc-600"
              disabled={ssoLoading}
            >
              {ssoLoading ? 'Redirecting...' : 'Continue with SSO'}
            </Button>
            <button
              type="button"
              onClick={() => { setSsoMode(false); setError('') }}
              className="w-full text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              Sign in with password instead
            </button>
          </form>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-5">
            <GrayInput
              id="email"
              label="Email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
            />
            <GrayInput
              id="password"
              label="Password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
            {error && <p className="text-sm text-red-400">{error}</p>}
            <Button
              type="submit"
              variant="secondary"
              className="w-full uppercase border border-zinc-600"
              disabled={loading}
            >
              {loading ? 'Signing in...' : 'Sign in'}
            </Button>
            <button
              type="button"
              onClick={() => { setSsoMode(true); setError('') }}
              className="w-full text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              Sign in with SSO
            </button>
          </form>
        )}

        <p className="mt-6 text-center text-sm text-zinc-500">
          Don&apos;t have an account?{' '}
          <button
            type="button"
            onClick={() => setContactOpen(true)}
            className="text-zinc-300 hover:text-zinc-100 transition-colors"
          >
            Contact sales
          </button>
        </p>
      </div>
      <PricingContactModal isOpen={contactOpen} onClose={() => setContactOpen(false)} />
    </div>
  )
}
