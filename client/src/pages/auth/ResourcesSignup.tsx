import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { invalidateMeCache } from '../../hooks/useMe'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

const DEFAULT_NEXT = '/app/resources'

/**
 * Free business-tier signup gating the HR resources hub.
 * POSTs `/auth/register/business` with tier='resources_free' — auto-approves
 * the company, creates a `client` user, no paid features. Honors `?next=`
 * for post-signup redirect.
 */
export default function ResourcesSignup() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = params.get('next') || DEFAULT_NEXT

  const [companyName, setCompanyName] = useState('')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!companyName.trim() || !name.trim() || !email.trim() || password.length < 8) return
    setSubmitting(true)
    setError(null)
    try {
      const res = await fetch(`${BASE}/auth/register/business`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tier: 'resources_free',
          company_name: companyName.trim(),
          name: name.trim(),
          email: email.trim().toLowerCase(),
          password,
          headcount: 1,
        }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail ?? 'Registration failed')
        return
      }
      localStorage.setItem('matcha_access_token', data.access_token)
      localStorage.setItem('matcha_refresh_token', data.refresh_token)
      invalidateMeCache()
      navigate(next)
    } catch {
      setError('Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const loginHref = `/login?next=${encodeURIComponent(next)}`

  return (
    <div
      className="min-h-screen flex items-center justify-center px-4 py-12"
      style={{ backgroundColor: BG, color: INK }}
    >
      <div className="w-full max-w-md">
        <Link to="/" className="block text-center mb-10">
          <span
            className="text-3xl tracking-tight"
            style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK }}
          >
            Matcha
          </span>
        </Link>

        <div
          className="rounded-2xl p-8"
          style={{ backgroundColor: 'rgba(255,255,255,0.5)', border: `1px solid ${LINE}` }}
        >
          <h1
            className="tracking-tight mb-2"
            style={{ fontFamily: DISPLAY, fontWeight: 500, fontSize: '1.75rem', color: INK }}
          >
            Free account.
          </h1>
          <p className="text-sm mb-6" style={{ color: MUTED }}>
            Unlocks 14 HR templates, the compliance audit, calculators, and the
            job descriptions library. No card, no trial — sign up your company once.
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <Field label="Company name" value={companyName} onChange={setCompanyName} />
            <Field label="Your name" value={name} onChange={setName} />
            <Field label="Work email" type="email" value={email} onChange={setEmail} />
            <Field label="Password" type="password" value={password} onChange={setPassword} hint="8 characters minimum" />

            {error && (
              <div
                className="text-sm px-3 py-2 rounded-md"
                style={{
                  color: '#8a4a3a',
                  backgroundColor: 'rgba(206,145,120,0.1)',
                  border: '1px solid rgba(206,145,120,0.3)',
                }}
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting || !companyName.trim() || !name.trim() || !email.trim() || password.length < 8}
              className="w-full h-12 rounded-full text-[14px] font-medium transition-opacity hover:opacity-90 disabled:opacity-50 flex items-center justify-center"
              style={{ backgroundColor: INK, color: BG }}
            >
              {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Create account'}
            </button>
          </form>

          <p className="mt-6 text-xs text-center" style={{ color: MUTED }}>
            Already have an account?{' '}
            <Link to={loginHref} className="underline" style={{ color: INK }}>
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}

function Field({
  label,
  value,
  onChange,
  type = 'text',
  hint,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  type?: string
  hint?: string
}) {
  return (
    <label className="block">
      <span
        className="block text-[10.5px] uppercase tracking-[0.2em] font-mono mb-2"
        style={{ color: MUTED }}
      >
        {label}
      </span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg px-4 py-3 text-[15px] outline-none"
        style={{
          backgroundColor: 'rgba(31,29,26,0.02)',
          border: `1px solid ${LINE}`,
          color: INK,
        }}
      />
      {hint && (
        <span className="block mt-1 text-xs" style={{ color: MUTED }}>
          {hint}
        </span>
      )}
    </label>
  )
}
