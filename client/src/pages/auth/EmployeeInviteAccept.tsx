import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { invalidateMeCache } from '../../hooks/useMe'
import { API_BASE } from '../../api/client'
import { setAuthTokens } from '../../api/authStorage'

// Redeems an employee-portal invite (server/app/matcha/routes/onboarding/invitations.py,
// table employee_invitations) — the link sent in the new-hire welcome email
// (core/services/email/employee.py builds it as `{app_base_url}/invite/{token}`).
// Distinct from BusinessInviteRegister.tsx, which redeems an admin-generated
// *company* invite against a different table/endpoint.
type InvitationDetails = {
  employee_id: string
  email: string
  first_name: string
  last_name: string
  company_name: string
  expires_at: string
  status: string
}

export default function EmployeeInviteAccept() {
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()

  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [invite, setInvite] = useState<InvitationDetails | null>(null)

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    if (!token) {
      setLoading(false)
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch(`${API_BASE}/invitations/${token}`)
        const data = await res.json()
        if (cancelled) return
        if (!res.ok) {
          setLoadError(data.detail ?? 'This invitation link is not valid.')
          return
        }
        setInvite(data)
      } catch {
        if (!cancelled) setLoadError('Something went wrong loading your invitation. Please try again.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [token])

  const passwordsMatch = password.length > 0 && password === confirmPassword
  const canSubmit = password.length >= 8 && passwordsMatch && !!token

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!canSubmit || !token) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      const res = await fetch(`${API_BASE}/invitations/${token}/accept`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      })
      const data = await res.json()
      if (!res.ok) {
        setSubmitError(data.detail ?? 'Could not create your account')
        return
      }
      setAuthTokens(data.access_token, data.refresh_token)
      invalidateMeCache()
      navigate('/portal')
    } catch {
      setSubmitError('Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (!token) {
    return (
      <Shell>
        <div className="text-center">
          <h1 className="text-xl font-semibold text-zinc-100 mb-2">Invalid Invitation</h1>
          <p className="text-sm text-zinc-500">This invitation link is missing its token.</p>
        </div>
      </Shell>
    )
  }

  if (loading) {
    return (
      <Shell>
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-6 h-6 animate-spin text-zinc-500" />
        </div>
      </Shell>
    )
  }

  if (loadError || !invite) {
    return (
      <Shell>
        <div className="text-center">
          <h1 className="text-xl font-semibold text-zinc-100 mb-2">Invitation Unavailable</h1>
          <p className="text-sm text-zinc-500">{loadError ?? 'This invitation could not be found.'}</p>
        </div>
      </Shell>
    )
  }

  return (
    <Shell>
      <div className="mb-8 text-center">
        <h1 className="text-2xl font-semibold text-zinc-100 mb-2">Welcome, {invite.first_name}</h1>
        <p className="text-sm text-zinc-400">
          Set a password to finish creating your account at <span className="text-zinc-300">{invite.company_name}</span>.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <label className="block">
          <span className="text-xs text-zinc-400 uppercase tracking-wide">Email</span>
          <input
            type="email"
            value={invite.email}
            disabled
            className="mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-500"
          />
        </label>

        <label className="block">
          <span className="text-xs text-zinc-400 uppercase tracking-wide">Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700"
          />
          <span className="block mt-1 text-xs text-zinc-500">8 characters minimum</span>
        </label>

        <label className="block">
          <span className="text-xs text-zinc-400 uppercase tracking-wide">Confirm password</span>
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className="mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700"
          />
          {confirmPassword.length > 0 && !passwordsMatch && (
            <span className="block mt-1 text-xs text-red-400">Passwords don't match</span>
          )}
        </label>

        {submitError && <p className="text-sm text-red-400">{submitError}</p>}

        <button
          type="submit"
          disabled={submitting || !canSubmit}
          className="w-full bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white font-medium py-2.5 rounded transition-colors flex items-center justify-center gap-2"
        >
          {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
          {submitting ? 'Creating account…' : 'Create my account'}
        </button>
      </form>
    </Shell>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-[#0c0c0e] flex items-center justify-center px-4 py-12">
      <div className="max-w-sm w-full">{children}</div>
    </div>
  )
}
