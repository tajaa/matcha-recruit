import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { Hash, Loader2 } from 'lucide-react'
import {
  getChannelInviteInfo,
  acceptChannelInvite,
  type ChannelInviteInfo,
} from '../../api/channels'
import { useMe, invalidateMeCache } from '../../hooks/useMe'

/**
 * Public landing for a channel invite (`/join-channel/:code`).
 *
 * Thin gate around the two existing paths:
 *  - Already signed in → bounce into the in-surface join page
 *    (`/werk` or `/work` → `channels/join/:code`), which redeems the invite
 *    and routes into the channel. Reuses ChannelJoinByInvite untouched.
 *  - Signed out → create a free personal account bound to the invite, then
 *    drop straight into the channel on the personal (/werk) surface.
 */
export default function ChannelInviteLanding() {
  const { code } = useParams<{ code: string }>()
  const navigate = useNavigate()
  const { me, loading: meLoading, isPersonal } = useMe()

  const [info, setInfo] = useState<ChannelInviteInfo | null>(null)
  const [infoLoading, setInfoLoading] = useState(true)

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [existingAccount, setExistingAccount] = useState(false)

  // Already signed in → hand off to the in-surface join flow.
  useEffect(() => {
    if (!meLoading && me && code) {
      const base = isPersonal ? '/werk' : '/work'
      navigate(`${base}/channels/join/${code}`, { replace: true })
    }
  }, [meLoading, me, isPersonal, code, navigate])

  // Load invite context for the signup form (only matters when signed out).
  useEffect(() => {
    if (!code) {
      setInfo({ channel_name: '', is_paid: false, valid: false })
      setInfoLoading(false)
      return
    }
    getChannelInviteInfo(code)
      .then((data) => {
        setInfo(data)
        if (data.email) setEmail(data.email)
      })
      .catch(() => setInfo({ channel_name: '', is_paid: false, valid: false }))
      .finally(() => setInfoLoading(false))
  }, [code])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!code || !name.trim() || !password) return
    setSubmitting(true)
    setError(null)
    setExistingAccount(false)
    try {
      const emailBound = !!info?.email
      const res = await acceptChannelInvite(code, {
        name: name.trim(),
        password,
        ...(emailBound ? {} : { email: email.trim() }),
      })
      localStorage.setItem('matcha_access_token', res.access_token)
      localStorage.setItem('matcha_refresh_token', res.refresh_token)
      invalidateMeCache()
      navigate(`/werk/channels/${res.channel_id}`, { replace: true })
    } catch (err) {
      const status = (err as { status?: number })?.status
      if (status === 409) {
        setExistingAccount(true)
        setError('You already have an account with this email.')
      } else {
        setError((err as Error)?.message ?? 'Could not join the channel')
      }
    } finally {
      setSubmitting(false)
    }
  }

  // While we resolve session / invite, show a spinner. A signed-in user is
  // mid-redirect here, so the spinner covers that hop too.
  if (meLoading || (me && code) || infoLoading) {
    return (
      <div className="min-h-screen bg-[#0c0c0e] flex items-center justify-center">
        <Loader2 className="w-6 h-6 text-w-dim animate-spin" />
      </div>
    )
  }

  if (!info?.valid) {
    return (
      <div className="min-h-screen bg-[#0c0c0e] flex items-center justify-center px-4">
        <div className="max-w-sm w-full text-center space-y-2">
          <h1 className="text-xl font-semibold text-w-text">Invite unavailable</h1>
          <p className="text-sm text-w-dim">
            This invite link is invalid, expired, or has already been used.
          </p>
          <Link to="/login" className="inline-block text-sm text-w-accent hover:text-w-accent">
            Go to sign in
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#0c0c0e] flex items-center justify-center px-4">
      <div className="max-w-sm w-full">
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-1.5 text-w-accent text-sm font-medium">
            <Hash className="w-4 h-4" />
            {info.channel_name}
          </div>
          <h1 className="text-2xl font-semibold text-w-text mt-3">
            {info.inviter_name ? `${info.inviter_name} invited you` : "You're invited"}
          </h1>
          <p className="text-sm text-w-dim mt-1">
            Create a free account to join the conversation.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-w-dim mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={!!info.email}
              required
              placeholder="you@example.com"
              className="w-full rounded-lg border border-w-line bg-w-surface px-3 py-2.5 text-sm text-w-text placeholder-w-faint outline-none focus:border-w-line transition-colors disabled:bg-w-surface/50 disabled:text-w-dim"
            />
          </div>

          <div>
            <label className="block text-xs text-w-dim mb-1">Full Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              autoFocus
              placeholder="Jane Smith"
              className="w-full rounded-lg border border-w-line bg-w-surface px-3 py-2.5 text-sm text-w-text placeholder-w-faint outline-none focus:border-w-line transition-colors"
            />
          </div>

          <div>
            <label className="block text-xs text-w-dim mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              placeholder="At least 8 characters"
              className="w-full rounded-lg border border-w-line bg-w-surface px-3 py-2.5 text-sm text-w-text placeholder-w-faint outline-none focus:border-w-line transition-colors"
            />
          </div>

          {error && (
            <p className="text-sm text-red-400">
              {error}
              {existingAccount && (
                <>
                  {' '}
                  <Link to="/login" className="text-w-accent hover:text-w-accent underline">
                    Sign in
                  </Link>{' '}
                  to join.
                </>
              )}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting || !name.trim() || !password || (!info.email && !email.trim())}
            className="w-full rounded-lg bg-w-accent py-2.5 text-sm font-medium text-white hover:bg-w-accent-hi disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
          >
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
            {submitting ? 'Joining…' : `Join #${info.channel_name}`}
          </button>
        </form>

        <p className="text-center text-[11px] text-w-faint mt-6">
          Already have an account?{' '}
          <Link to="/login" className="text-w-dim hover:text-w-text">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}
