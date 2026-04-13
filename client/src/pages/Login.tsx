import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { PricingContactModal } from '../components/PricingContactModal'
import { api } from '../api/client'
import { invalidateMeCache } from '../hooks/useMe'

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

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

function IvoryInput({ label, id, ...props }: React.ComponentProps<'input'> & { label: string }) {
  return (
    <label htmlFor={id} className="block">
      <span
        className="block text-[10.5px] uppercase tracking-[0.2em] font-mono mb-2"
        style={{ color: MUTED }}
      >
        {label}
      </span>
      <input
        id={id}
        className="w-full rounded-lg px-4 py-3 text-[15px] outline-none transition-all focus:ring-2"
        style={{
          backgroundColor: 'rgba(31,29,26,0.02)',
          border: `1px solid ${LINE}`,
          color: INK,
          // @ts-expect-error: custom focus ring color via inline style
          '--tw-ring-color': 'rgba(31,29,26,0.15)',
        }}
        {...props}
      />
    </label>
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
      invalidateMeCache()
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
    const baseUrl = import.meta.env.VITE_API_URL || '/api'
    window.location.href = `${baseUrl}/sso/login?email=${encodeURIComponent(email)}`
  }

  return (
    <div
      className="relative min-h-screen flex items-center justify-center px-4 overflow-hidden"
      style={{ backgroundColor: BG, color: INK }}
    >
      {/* Soft radial glow */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            'radial-gradient(ellipse 60% 50% at 50% 30%, rgba(31,29,26,0.05) 0%, rgba(31,29,26,0) 60%)',
        }}
      />

      <div className="relative z-10 w-full max-w-md">
        {/* Wordmark */}
        <Link to="/" className="block text-center mb-12">
          <span
            className="text-4xl tracking-tight"
            style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK }}
          >
            Matcha
          </span>
        </Link>

        {/* Card */}
        <div
          className="rounded-2xl p-8 sm:p-10"
          style={{
            backgroundColor: 'rgba(255,255,255,0.5)',
            border: `1px solid ${LINE}`,
            boxShadow: '0 40px 80px -20px rgba(31,29,26,0.1)',
          }}
        >
          <div className="mb-8">
            <h1
              className="tracking-tight"
              style={{
                fontFamily: DISPLAY,
                fontWeight: 400,
                color: INK,
                fontSize: '2rem',
                lineHeight: 1.1,
              }}
            >
              {ssoMode ? 'Sign in with SSO' : 'Sign in.'}
            </h1>
            <p className="mt-2 text-sm" style={{ color: MUTED }}>
              {ssoMode
                ? 'Enter your work email to continue via your identity provider.'
                : 'Welcome back. Access your consulting workspace.'}
            </p>
          </div>

          {ssoMode ? (
            <form onSubmit={handleSSOLogin} className="space-y-5">
              <IvoryInput
                id="sso-email"
                label="Work email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
              />
              {error && <ErrorText text={error} />}
              <button
                type="submit"
                disabled={ssoLoading}
                className="w-full h-12 rounded-full text-[14px] font-medium transition-opacity hover:opacity-90 disabled:opacity-50"
                style={{ backgroundColor: INK, color: BG }}
              >
                {ssoLoading ? 'Redirecting…' : 'Continue with SSO'}
              </button>
              <button
                type="button"
                onClick={() => { setSsoMode(false); setError('') }}
                className="w-full text-sm transition-opacity hover:opacity-60"
                style={{ color: MUTED }}
              >
                Sign in with password instead
              </button>
            </form>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-5">
              <IvoryInput
                id="email"
                label="Email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
              />
              <IvoryInput
                id="password"
                label="Password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
              />
              {error && <ErrorText text={error} />}
              <button
                type="submit"
                disabled={loading}
                className="w-full h-12 rounded-full text-[14px] font-medium transition-opacity hover:opacity-90 disabled:opacity-50"
                style={{ backgroundColor: INK, color: BG }}
              >
                {loading ? 'Signing in…' : 'Sign in'}
              </button>
              <div className="flex items-center justify-between text-sm">
                <button
                  type="button"
                  onClick={() => { setSsoMode(true); setError('') }}
                  className="transition-opacity hover:opacity-60"
                  style={{ color: MUTED }}
                >
                  Sign in with SSO
                </button>
                <Link
                  to="/reset-password"
                  className="transition-opacity hover:opacity-60"
                  style={{ color: MUTED }}
                >
                  Forgot password?
                </Link>
              </div>
            </form>
          )}
        </div>

        {/* Contact sales */}
        <p className="mt-8 text-center text-sm" style={{ color: MUTED }}>
          Don&apos;t have an account?{' '}
          <button
            type="button"
            onClick={() => setContactOpen(true)}
            className="underline transition-opacity hover:opacity-60"
            style={{ color: INK, textDecorationColor: LINE, textUnderlineOffset: '4px' }}
          >
            Book a consultation
          </button>
        </p>
      </div>

      <PricingContactModal isOpen={contactOpen} onClose={() => setContactOpen(false)} />
    </div>
  )
}

function ErrorText({ text }: { text: string }) {
  return (
    <div
      className="text-sm px-3 py-2 rounded-md"
      style={{
        color: '#8a4a3a',
        backgroundColor: 'rgba(206,145,120,0.1)',
        border: '1px solid rgba(206,145,120,0.3)',
      }}
    >
      {text}
    </div>
  )
}
