import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { invalidateMeCache } from '../../hooks/useMe'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

/**
 * Free-beta signup for Matcha IR. Not linked from main nav — reached
 * by direct URL (/ir/signup) only during private beta. Posts to the
 * existing /auth/register/business with tier='ir_only', which auto-
 * approves the company, sets signup_source='ir_only_self_serve', and
 * enables only the `incidents` feature flag.
 */
export default function IrSignup() {
  const navigate = useNavigate()
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
          tier: 'ir_only',
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
      navigate(data.next ?? '/ir/onboarding')
    } catch {
      setError('Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#0c0c0e] flex items-center justify-center px-4 py-12">
      <div className="max-w-sm w-full">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-semibold text-zinc-100 mb-2">Matcha IR</h1>
          <p className="text-sm text-zinc-400">Incident reporting for HR teams. Free during beta.</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <Field label="Company name" value={companyName} onChange={setCompanyName} />
          <Field label="Your name" value={name} onChange={setName} />
          <Field label="Work email" type="email" value={email} onChange={setEmail} />
          <Field label="Password" type="password" value={password} onChange={setPassword} hint="8 characters minimum" />

          {error && <p className="text-sm text-red-400">{error}</p>}

          <button
            type="submit"
            disabled={submitting || !companyName.trim() || !name.trim() || !email.trim() || password.length < 8}
            className="w-full bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white font-medium py-2.5 rounded transition-colors flex items-center justify-center"
          >
            {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Create account'}
          </button>
        </form>
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
      <span className="text-xs text-zinc-400 uppercase tracking-wide">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700"
      />
      {hint && <span className="block mt-1 text-xs text-zinc-500">{hint}</span>}
    </label>
  )
}
