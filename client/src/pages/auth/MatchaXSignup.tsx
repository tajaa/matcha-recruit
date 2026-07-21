import { externalRedirect } from '../../utils/externalRedirect'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { invalidateMeCache } from '../../hooks/useMe'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

// TODO: set the real Matcha-X price. Mirrors Lite's stub for now — keep in
// sync with matcha_x_price_cents() in server/app/core/services/stripe_service.py.
function matchaXPriceDollars(headcount: number): number {
  return Math.ceil(headcount / 10) * 100
}

export default function MatchaXSignup() {
  const [searchParams] = useSearchParams()
  const brokerRef = searchParams.get('ref')
  const inviteToken = searchParams.get('invite_token')
  const [companyName, setCompanyName] = useState('')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [headcount, setHeadcount] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [inviteInfo, setInviteInfo] = useState<
    { valid: boolean; company_name: string; seat_count: number | null; broker_name: string } | null
  >(null)

  // Broker seat invites pin the company name + seats; prefill + lock them.
  useEffect(() => {
    if (!brokerRef) return
    fetch(`${BASE}/auth/client-invite-info?ref=${encodeURIComponent(brokerRef)}`)
      .then((r) => r.json())
      .then((info) => {
        if (info?.valid) {
          setInviteInfo(info)
          setCompanyName(info.company_name ?? '')
          if (info.seat_count) setHeadcount(String(info.seat_count))
        }
      })
      .catch(() => {})
  }, [brokerRef])

  const seatInvite = inviteInfo?.valid === true
  const comped = !!inviteToken || seatInvite
  const hc = parseInt(headcount, 10)
  const headcountValid = !isNaN(hc) && hc >= 1
  const overLimit = headcountValid && !comped && hc > 300
  const price = headcountValid && !overLimit && !comped ? matchaXPriceDollars(hc) : null

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
          tier: 'matcha_x',
          company_name: companyName.trim(),
          name: name.trim(),
          email: email.trim().toLowerCase(),
          password,
          headcount: hc,
          ...(brokerRef ? { lite_broker_token: brokerRef } : {}),
          ...(inviteToken ? { lite_invite_token: inviteToken } : {}),
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

      // Broker-pays or admin invite: account is already active, skip Stripe
      if (regData.lite_broker_pays || regData.lite_invite_activated) {
        window.location.href = '/matcha-x/onboarding?x=1'
        return
      }

      // Step 2: open Stripe checkout
      const checkoutRes = await fetch(`${BASE}/resources/checkout/x`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          headcount: hc,
          success_url: `${window.location.origin}/matcha-x/onboarding?x=1`,
          cancel_url: window.location.href,
        }),
      })
      const checkoutData = await checkoutRes.json()
      if (!checkoutRes.ok) {
        setError(checkoutData.detail ?? 'Failed to start checkout')
        return
      }
      externalRedirect(checkoutData.checkout_url)
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
          <h1 className="text-2xl font-semibold text-zinc-100 mb-2">Matcha-X</h1>
          <p className="text-sm text-zinc-400">
            Incident reporting &amp; HR resources.
          </p>
        </div>

        {seatInvite && (
          <div className="mb-5 p-3 rounded-lg bg-emerald-950/40 border border-emerald-900/50 text-xs text-emerald-200 text-center">
            Invited by <span className="font-medium">{inviteInfo?.broker_name}</span> · {inviteInfo?.seat_count} seats included
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <Field label="Company name" value={companyName} onChange={setCompanyName} readOnly={seatInvite} />
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
                readOnly={seatInvite}
                placeholder="e.g. 25"
                className={`mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700 ${seatInvite ? 'opacity-60 cursor-not-allowed' : ''}`}
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
            ) : (brokerRef || inviteToken) ? (
              'Create account'
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
  readOnly = false,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  type?: string
  hint?: string
  readOnly?: boolean
}) {
  return (
    <label className="block">
      <span className="text-xs text-zinc-400 uppercase tracking-wide">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        readOnly={readOnly}
        className={`mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700 ${readOnly ? 'opacity-60 cursor-not-allowed' : ''}`}
      />
      {hint && <span className="block mt-1 text-xs text-zinc-500">{hint}</span>}
    </label>
  )
}
