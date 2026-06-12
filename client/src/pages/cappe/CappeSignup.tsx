import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Loader2, Store, User } from 'lucide-react'
import { cappePublicPost, setCappeTokens } from '../../api/cappeClient'
import { invalidateCappeMeCache } from '../../hooks/useCappeMe'
import type { CappeAccountType, CappeTokenResponse } from '../../types/cappe'

const ACCOUNT_TYPES: {
  value: CappeAccountType
  icon: typeof Store
  title: string
  blurb: string
}[] = [
  {
    value: 'business',
    icon: Store,
    title: 'A business',
    blurb: 'A shop, studio or restaurant — sell products and take orders.',
  },
  {
    value: 'personal',
    icon: User,
    title: 'Just me',
    blurb: 'A solo pro — get booked, sell sessions, services and downloads.',
  },
]

// Cappe account signup — the functional entry at /cappe/website-setup.
export default function CappeSignup() {
  const navigate = useNavigate()
  const [accountType, setAccountType] = useState<CappeAccountType>('business')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }
    setSubmitting(true)
    try {
      const res = await cappePublicPost<CappeTokenResponse>('/auth/signup', {
        name: name || null,
        email,
        password,
        account_type: accountType,
      })
      setCappeTokens(res.access_token, res.refresh_token)
      invalidateCappeMeCache()
      navigate('/cappe/sites', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 bg-[radial-gradient(60rem_40rem_at_50%_-10%,rgba(16,185,129,0.08),transparent)] px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <span className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-400 to-emerald-600 text-lg font-bold text-zinc-950 shadow-lg shadow-emerald-500/20">
            C
          </span>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">Create your Cappe account</h1>
          <p className="mt-1 text-sm text-zinc-400">Build and launch your website in minutes.</p>
        </div>

        <form onSubmit={onSubmit} className="space-y-4 rounded-2xl border border-zinc-800 bg-zinc-900 p-6 shadow-xl shadow-black/40">
          <div>
            <label className="mb-2 block text-sm font-medium text-zinc-300">I'm building a site for…</label>
            <div className="grid grid-cols-2 gap-2">
              {ACCOUNT_TYPES.map(({ value, icon: Icon, title, blurb }) => {
                const active = accountType === value
                return (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setAccountType(value)}
                    className={`rounded-xl border p-3 text-left transition-colors ${
                      active
                        ? 'border-emerald-500 bg-emerald-500/10'
                        : 'border-zinc-700 bg-zinc-950 hover:border-zinc-500'
                    }`}
                  >
                    <Icon className={`mb-1.5 h-4 w-4 ${active ? 'text-emerald-400' : 'text-zinc-500'}`} />
                    <p className={`text-sm font-medium ${active ? 'text-emerald-300' : 'text-zinc-200'}`}>{title}</p>
                    <p className="mt-0.5 text-[11px] leading-snug text-zinc-500">{blurb}</p>
                  </button>
                )
              })}
            </div>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-300">Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
              placeholder="Your name"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-300">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-300">Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
              placeholder="At least 8 characters"
            />
          </div>

          {error && <p className="text-sm text-red-400">{error}</p>}

          <button
            type="submit"
            disabled={submitting}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 transition-colors hover:bg-emerald-400 disabled:opacity-60"
          >
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            Create account
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-zinc-500">
          Already have an account?{' '}
          <Link to="/cappe/login" className="font-medium text-emerald-400 hover:text-emerald-300">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}
