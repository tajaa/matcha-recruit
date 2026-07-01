import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { invalidateMeCache } from '../../hooks/useMe'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

// Redeems an admin-generated business invite (server/app/core/routes/admin.py
// POST /admin/business-invites, table business_invitations) — the generic,
// tier-agnostic path for provisioning a full Pro/bespoke company with no
// Stripe checkout involved. Auto-approved immediately on submit; unlike
// Lite/X/Compliance there's no separate "comped" state to reach — an
// invite-redeemed bespoke signup IS the comped path.
export default function BusinessInviteRegister() {
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()
  const [companyName, setCompanyName] = useState('')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [headcount, setHeadcount] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const hc = parseInt(headcount, 10)
  const headcountValid = !isNaN(hc) && hc >= 1
  const canSubmit = companyName.trim() && name.trim() && email.trim() && password.length >= 8 && headcountValid && !!token

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!canSubmit) return
    setSubmitting(true)
    setError(null)
    try {
      const res = await fetch(`${BASE}/auth/register/business`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company_name: companyName.trim(),
          name: name.trim(),
          email: email.trim().toLowerCase(),
          password,
          headcount: hc,
          invite_token: token,
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
      navigate('/app')
    } catch {
      setError('Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (!token) {
    return (
      <div className="min-h-screen bg-[#0c0c0e] flex items-center justify-center px-4">
        <div className="max-w-sm w-full text-center">
          <h1 className="text-xl font-semibold text-zinc-100 mb-2">Invalid Invitation</h1>
          <p className="text-sm text-zinc-500">This invitation link is missing its token.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#0c0c0e] flex items-center justify-center px-4 py-12">
      <div className="max-w-sm w-full">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-semibold text-zinc-100 mb-2">Matcha</h1>
          <p className="text-sm text-zinc-400">You've been invited to set up your company account.</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Field label="Company name" value={companyName} onChange={setCompanyName} />
          <Field label="Your name" value={name} onChange={setName} />
          <Field label="Work email" type="email" value={email} onChange={setEmail} />
          <Field label="Password" type="password" value={password} onChange={setPassword} hint="8 characters minimum" />

          <label className="block">
            <span className="text-xs text-zinc-400 uppercase tracking-wide">Number of employees</span>
            <input
              type="number"
              min={1}
              value={headcount}
              onChange={(e) => setHeadcount(e.target.value)}
              placeholder="e.g. 25"
              className="mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700"
            />
          </label>

          {error && <p className="text-sm text-red-400">{error}</p>}

          <button
            type="submit"
            disabled={submitting || !canSubmit}
            className="w-full bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white font-medium py-2.5 rounded transition-colors flex items-center justify-center gap-2"
          >
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
            {submitting ? 'Creating account…' : 'Create account'}
          </button>
        </form>

        <p className="text-center text-[10px] text-zinc-600 mt-6">
          By creating an account you agree to our terms of service.
        </p>
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
