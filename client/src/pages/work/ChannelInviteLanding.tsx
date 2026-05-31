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
        <Loader2 className="w-6 h-6 text-zinc-500 animate-spin" />
      </div>
    )
  }

  if (!info?.valid) {
    return (
      <div className="min-h-screen bg-[#0c0c0e] flex items-center justify-center px-4">
        <div className="max-w-sm w-full text-center space-y-2">
          <h1 className="text-xl font-semibold text-zinc-100">Invite unavailable</h1>
          <p className="text-sm text-zinc-500">
            This invite link is invalid, expired, or has already been used.
          </p>
          <Link to="/login" className="inline-block text-sm text-emerald-400 hover:text-emerald-300">
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
          <div className="inline-flex items-center gap-1.5 text-emerald-400 text-sm font-medium">
            <Hash className="w-4 h-4" />
            {info.channel_name}
          </div>
          <h1 className="text-2xl font-semibold text-zinc-100 mt-3">
            {info.inviter_name ? `${info.inviter_name} invited you` : "You're invited"}
          </h1>
          <p className="text-sm text-zinc-500 mt-1">
            Create a free account to join the conversation.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-zinc-400 mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={!!info.email}
              required
              placeholder="you@example.com"
              className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-zinc-500 transition-colors disabled:bg-zinc-900/50 disabled:text-zinc-400"
            />
          </div>

          <div>
            <label className="block text-xs text-zinc-400 mb-1">Full Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              autoFocus
              placeholder="Jane Smith"
              className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-zinc-500 transition-colors"
            />
          </div>

          <div>
            <label className="block text-xs text-zinc-400 mb-1">Password</label>
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

          {error && (
            <p className="text-sm text-red-400">
              {error}
              {existingAccount && (
                <>
                  {' '}
                  <Link to="/login" className="text-emerald-400 hover:text-emerald-300 underline">
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
            className="w-full rounded-lg bg-emerald-600 py-2.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
          >
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
            {submitting ? 'Joining…' : `Join #${info.channel_name}`}
          </button>
        </form>

        <p className="text-center text-[11px] text-zinc-600 mt-6">
          Already have an account?{' '}
          <Link to="/login" className="text-zinc-400 hover:text-zinc-300">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}
