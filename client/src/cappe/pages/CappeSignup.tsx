import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Loader2, Store, User, Sparkles, MailCheck, Gift, Newspaper } from 'lucide-react'
import { CappeApiError, cappePublicGet, cappePublicPost, setCappeTokens } from '../api'
import { invalidateCappeMeCache } from '../hooks/useCappeMe'
import { creatorPaths } from '../creators/creatorPaths'
import { writerPaths } from '../magazine/writers/writerPaths'
import { readerNext, readerPaths } from '../magazine/shelf/readerPaths'
import { postAuthHome } from '../utils/postAuthHome'
import ResendVerification from '../components/ResendVerification'
import { billingStartPath } from './CappeBilling/paths'
import type { CappeAccountType, CappeSignupGrantInfo, CappeSignupResponse } from '../types'

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
    blurb: 'A shop, studio, restaurant or online store — sell products and take orders.',
  },
  {
    value: 'personal',
    icon: User,
    title: 'Just me',
    blurb: 'A solo pro — get booked, sell sessions, services and downloads.',
  },
  {
    value: 'creator',
    icon: Sparkles,
    title: 'A creator',
    blurb: 'Influencer or content creator — get discovered, get brand deals, get paid.',
  },
  {
    value: 'writer',
    icon: Newspaper,
    title: 'A writer',
    blurb: 'Publish your own photo magazine — stories, issues and paid readers.',
  },
]

// Cappe account signup — the functional entry at /cappe/website-setup.
export default function CappeSignup({ creatorOnly = false, brandOnly = false, writerOnly = false, readerOnly = false }: {
  creatorOnly?: boolean; brandOnly?: boolean
  /** Gummfit Magazines: a writer account, whose next step is naming their magazine. */
  writerOnly?: boolean
  /** A reader account: subscribes to magazines, sells nothing, has no plan. */
  readerOnly?: boolean
}) {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [accountType, setAccountType] = useState<CappeAccountType>(
    readerOnly ? 'reader' : writerOnly || params.get('type') === 'writer' ? 'writer' : creatorOnly || params.get('type') === 'creator' ? 'creator' : 'business',
  )
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [sentTo, setSentTo] = useState<string | null>(null)
  // A writer picked on the general page goes where the writer page sends them.
  const writer = writerOnly || accountType === 'writer'
  // A paid plan picked on the pricing cards. The server keeps it across the
  // email-confirmation hop; creators and brands have their own signup pages.
  // A grant link (/signup?grant=…) gives a paid plan free for a while, so it
  // replaces any plan picked on the pricing cards: there is nothing to pay.
  // The pattern mirrors the server's GRANT_TOKEN_PATTERN (models/auth.py).
  const grantToken = !creatorOnly && !brandOnly && !readerOnly && /^[A-Za-z0-9_-]{16,64}$/.test(params.get('grant') ?? '') ? params.get('grant') : null
  const [grant, setGrant] = useState<CappeSignupGrantInfo | null>(null)
  // Set only when the SERVER says the link can't be used. Until then the token
  // is sent with the signup even if the lookup hasn't answered (or failed for
  // a passing reason), and the server decides: a promised plan is never
  // dropped because the page was quick or the network slow.
  const [grantDead, setGrantDead] = useState<string | null>(null)
  // A writer names their magazine first and picks a plan when it goes live;
  // a reader has no plan.
  const plan = !grantToken && !creatorOnly && !brandOnly && !writer && !readerOnly && /^[a-z0-9_]{1,40}$/.test(params.get('plan') ?? '') ? params.get('plan') : null
  const interval = params.get('interval') === 'year' ? 'year' : 'month'
  // A reader sent here from a magazine keeps where they were going.
  const signInPath = params.get('next') ? `${readerPaths.login}?next=${encodeURIComponent(params.get('next') ?? '')}` : readerPaths.login

  useEffect(() => {
    if (!grantToken) return
    cappePublicGet<CappeSignupGrantInfo>(`/auth/signup-grants/${grantToken}`)
      .then(setGrant)
      .catch((err) => {
        if (err instanceof CappeApiError && err.code === 'grant_invalid') setGrantDead(err.message)
      })
  }, [grantToken])

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }
    setSubmitting(true)
    try {
      const res = await cappePublicPost<CappeSignupResponse>('/auth/signup', {
        name: name || null,
        email,
        password,
        account_type: accountType,
        ...(plan ? { intended_plan: plan, intended_interval: interval } : {}),
        ...(grantToken && !grantDead ? { grant_token: grantToken } : {}),
      })
      if (res.verification_required) {
        // No tokens yet — account is live only after the email link is clicked.
        setSentTo(res.email)
        return
      }
      // Reserved test-domain (dev) signups auto-verify and come back with tokens.
      if (res.access_token && res.refresh_token) {
        setCappeTokens(res.access_token, res.refresh_token)
        invalidateCappeMeCache()
        navigate(
          creatorOnly ? creatorPaths.home
            : brandOnly ? creatorPaths.brandHome
            : writer ? writerPaths.home
            : readerOnly ? readerNext(params.get('next'))
              : res.intended_plan && res.account?.account_type !== 'creator'
                ? billingStartPath(res.intended_plan, res.intended_interval)
                : postAuthHome(res.account?.account_type),
          { replace: true },
        )
      }
    } catch (err) {
      if (err instanceof CappeApiError && err.code === 'grant_invalid') {
        // The link stopped working while the form was open (used up, revoked).
        // Say so, and let the next press sign up without it.
        setGrant(null)
        setGrantDead(err.message)
        setError('Press “Create account” again to sign up without the invite.')
      } else {
        setError(err instanceof Error ? err.message : 'Something went wrong.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (sentTo) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950 bg-[radial-gradient(60rem_40rem_at_50%_-10%,rgba(198,241,107,0.08),transparent)] px-4">
        <div className="w-full max-w-sm text-center">
          <span className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-lime-300/15 text-lime-300">
            <MailCheck className="h-6 w-6" />
          </span>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">Confirm your email</h1>
          <p className="mt-2 text-sm leading-relaxed text-zinc-400">
            We sent a confirmation link to <span className="text-zinc-200">{sentTo}</span>. Click it to
            activate your account and start {readerOnly ? 'reading' : 'building'}. The link works for 24 hours.
          </p>
          <div className="mt-6 space-y-3 rounded-xl border border-zinc-800 bg-zinc-900 p-4 text-left text-xs leading-relaxed text-zinc-500">
            <p>
              Didn't get it? Check spam first. If you already have an account with this address, the
              email will tell you to sign in instead.
            </p>
            <ResendVerification email={sentTo} label="Resend the email" />
            <button
              type="button"
              onClick={() => setSentTo(null)}
              className="text-sm font-medium text-zinc-400 hover:text-zinc-200"
            >
              Wrong address? Go back and fix it
            </button>
          </div>
          <Link to={creatorOnly ? creatorPaths.login : brandOnly ? creatorPaths.brandLogin : writer ? writerPaths.login : readerOnly ? readerPaths.login : '/cappe/login'} className="mt-6 inline-block text-sm font-medium text-lime-400 hover:text-lime-300">
            Back to sign in
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 bg-[radial-gradient(60rem_40rem_at_50%_-10%,rgba(16,185,129,0.08),transparent)] px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <span className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-lime-300 to-lime-500 text-lg font-bold text-zinc-950 shadow-lg shadow-lime-500/20">
            G
          </span>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">
            Create your {creatorOnly ? 'Gummfit Creators' : brandOnly ? 'brand collab' : writerOnly ? 'Gummfit Magazines' : readerOnly ? 'Gummfit reader' : 'Gummfit'} account
          </h1>
          <p className="mt-1 text-sm text-zinc-400">
            {creatorOnly ? 'Build your creator profile and connect with brands.' : brandOnly ? 'Find Gummfit Creators and manage collaborations.' : writerOnly ? 'Publish your own photo magazine, at your own address.' : readerOnly ? 'Subscribe to magazines and read them all in one place.' : 'Build and launch your website in minutes.'}
          </p>
        </div>

        <form onSubmit={onSubmit} className="space-y-4 rounded-2xl border border-zinc-800 bg-zinc-900 p-6 shadow-xl shadow-black/40">
          {!creatorOnly && !brandOnly && !writerOnly && !readerOnly && <div>
            <label className="mb-2 block text-sm font-medium text-zinc-300">I'm building a site for…</label>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {ACCOUNT_TYPES.map(({ value, icon: Icon, title, blurb }) => {
                const active = accountType === value
                return (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setAccountType(value)}
                    aria-pressed={active}
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
          </div>}
          <div>
            <label htmlFor="cappe-signup-name" className="mb-1 block text-sm font-medium text-zinc-300">Your name</label>
            <input
              id="cappe-signup-name"
              type="text"
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
              placeholder="Your name"
            />
          </div>
          <div>
            <label htmlFor="cappe-signup-email" className="mb-1 block text-sm font-medium text-zinc-300">Email</label>
            <input
              id="cappe-signup-email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label htmlFor="cappe-signup-password" className="mb-1 block text-sm font-medium text-zinc-300">Password</label>
            <input
              id="cappe-signup-password"
              type="password"
              autoComplete="new-password"
              minLength={8}
              aria-describedby="cappe-signup-password-hint"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
            />
            <p id="cappe-signup-password-hint" className="mt-1 text-xs text-zinc-500">At least 8 characters.</p>
          </div>

          {grant && !grantDead && (
            <p className="flex gap-2 rounded-lg border border-lime-400/20 bg-lime-300/[0.06] px-3 py-2 text-xs leading-relaxed text-zinc-300">
              <Gift className="mt-0.5 h-3.5 w-3.5 shrink-0 text-lime-300" />
              <span>
                You've been given <span className="font-semibold text-lime-300">{grant.plan_name}</span> free for{' '}
                {grant.days} days. No card needed: it starts when you confirm your email. After that, pick a plan to keep it.
                {grant.email_locked && ' Sign up with the email address the invite was sent to.'}
              </span>
            </p>
          )}
          {grantDead && (
            <p className="rounded-lg border border-amber-500/30 bg-amber-500/[0.06] px-3 py-2 text-xs leading-relaxed text-amber-300">
              {grantDead} You can still create a free account.
            </p>
          )}

          {plan && (
            <p className="rounded-lg border border-lime-400/20 bg-lime-300/[0.06] px-3 py-2 text-xs leading-relaxed text-zinc-300">
              You picked the <span className="font-semibold capitalize text-lime-300">{plan.replace(/_/g, ' ')}</span> plan,
              billed {interval === 'year' ? 'yearly' : 'monthly'}. Nothing is charged now: you'll review and pay right
              after confirming your email.
            </p>
          )}

          {error && <p role="alert" className="text-sm text-red-400">{error}</p>}

          <button
            type="submit"
            disabled={submitting}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 transition-colors hover:bg-emerald-400 disabled:opacity-60"
          >
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            {creatorOnly ? 'Create creator profile' : brandOnly ? 'Create brand profile' : 'Create account'}
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-zinc-500">
          Already have an account?{' '}
          <Link to={creatorOnly ? creatorPaths.login : brandOnly ? creatorPaths.brandLogin : readerOnly ? signInPath : '/cappe/login'} className="font-medium text-emerald-400 hover:text-emerald-300">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}
