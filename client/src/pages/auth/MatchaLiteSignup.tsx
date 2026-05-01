import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { invalidateMeCache } from '../../hooks/useMe'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

function litePriceDollars(headcount: number): number {
  return Math.ceil(headcount / 10) * 100
}

export default function MatchaLiteSignup() {
  const [companyName, setCompanyName] = useState('')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [headcount, setHeadcount] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const hc = parseInt(headcount, 10)
  const headcountValid = !isNaN(hc) && hc >= 1
  const overLimit = headcountValid && hc > 300
  const price = headcountValid && !overLimit ? litePriceDollars(hc) : null

  const canSubmit =
    companyName.trim() &&
    name.trim() &&
    email.trim() &&
    password.length >= 8 &&
    headcountValid &&
    !overLimit

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!canSubmit) return
    setSubmitting(true)
    setError(null)
    try {
      // Step 1: register account (features all off until Stripe completes)
      const regRes = await fetch(`${BASE}/auth/register/business`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tier: 'matcha_lite',
          company_name: companyName.trim(),
          name: name.trim(),
          email: email.trim().toLowerCase(),
          password,
          headcount: hc,
        }),
      })
      const regData = await regRes.json()
      if (!regRes.ok) {
        setError(regData.detail ?? 'Registration failed')
        return
      }

      const accessToken: string = regData.access_token
      const refreshToken: string = regData.refresh_token
      localStorage.setItem('matcha_access_token', accessToken)
      localStorage.setItem('matcha_refresh_token', refreshToken)
      invalidateMeCache()

      // Step 2: open Stripe checkout
      const checkoutRes = await fetch(`${BASE}/resources/checkout/lite`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          headcount: hc,
          success_url: `${window.location.origin}/ir/onboarding?lite=1`,
          cancel_url: window.location.href,
        }),
      })
      const checkoutData = await checkoutRes.json()
      if (!checkoutRes.ok) {
        setError(checkoutData.detail ?? 'Failed to start checkout')
        return
      }
      window.location.href = checkoutData.checkout_url
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
          <h1 className="text-2xl font-semibold text-zinc-100 mb-2">Matcha Lite</h1>
          <p className="text-sm text-zinc-400">
            Incident reporting, employee management &amp; HR resources.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Field label="Company name" value={companyName} onChange={setCompanyName} />
          <Field label="Your name" value={name} onChange={setName} />
          <Field label="Work email" type="email" value={email} onChange={setEmail} />
          <Field
            label="Password"
            type="password"
            value={password}
            onChange={setPassword}
            hint="8 characters minimum"
          />

          <div>
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
            {overLimit ? (
              <p className="mt-1 text-xs text-red-400">
                Over 300 employees —{' '}
                <a href="mailto:hello@matcha.work" className="underline">
                  contact us for pricing
                </a>
              </p>
            ) : price !== null ? (
              <p className="mt-1 text-xs text-zinc-400">
                <span className="text-zinc-100 font-medium">${price}/month</span> · billed monthly
              </p>
            ) : null}
          </div>

          {error && <p className="text-sm text-red-400">{error}</p>}

          <button
            type="submit"
            disabled={submitting || !canSubmit}
            className="w-full bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white font-medium py-2.5 rounded transition-colors flex items-center justify-center gap-2"
          >
            {submitting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Setting up…
              </>
            ) : (
              'Create account & subscribe'
            )}
          </button>

          <p className="text-center text-xs text-zinc-500">
            Already have an account?{' '}
            <a href="/auth/login" className="text-zinc-300 hover:text-white underline">
              Sign in
            </a>
          </p>
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
