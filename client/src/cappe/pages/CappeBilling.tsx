import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Check, CircleAlert, CreditCard, Loader2 } from 'lucide-react'
import { cappeApi } from '../api'
import { ui } from '../components/ui'
import { useCappeMe } from '../hooks/useCappeMe'
import { formatCents } from './landing/shared'
import { BILLING_PATH } from './CappeBilling/paths'
import type { CappeBillingInterval, CappeBillingPlan, CappeCatalog, CappeSubscription } from '../types'

// After checkout Stripe sends the browser back before its webhook has reached
// us, so the plan can still read "free" for a few seconds. Ask again until the
// subscription shows up, rather than telling someone who just paid they didn't.
export const POLL_MS = 2000
export const POLL_TRIES = 15

const LIVE = new Set(['trialing', 'active'])

type Notice = { tone: 'ok' | 'info' | 'warn'; text: string }

const NOTICE_TONE: Record<Notice['tone'], string> = {
  ok: 'border-emerald-500/30 bg-emerald-500/[0.06] text-emerald-300',
  info: 'border-zinc-700 bg-zinc-900 text-zinc-300',
  warn: 'border-amber-500/30 bg-amber-500/[0.06] text-amber-300',
}

function billingUrl(query = ''): string {
  return `${window.location.origin}${BILLING_PATH}${query}`
}

function day(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })
}

function priceFor(plan: CappeBillingPlan, interval: CappeBillingInterval) {
  return plan.prices.find((p) => p.interval === interval && p.purchasable)
}

/** The interval a plan can actually be bought at: the one on show, else monthly. */
function buyable(plan: CappeBillingPlan, interval: CappeBillingInterval): CappeBillingInterval | null {
  if (priceFor(plan, interval)) return interval
  return priceFor(plan, 'month') ? 'month' : null
}

function planPoints(plan: CappeBillingPlan): string[] {
  const points = [plan.site_limit === null ? 'Unlimited sites' : `${plan.site_limit} site${plan.site_limit === 1 ? '' : 's'}`]
  if (plan.can_sell) {
    points.push(plan.platform_fee_bps > 0 ? `${plan.platform_fee_bps / 100}% platform fee on sales` : 'No platform fee on sales')
  }
  if (plan.mailbox_quota_included > 0) {
    points.push(`${plan.mailbox_quota_included} mailbox${plan.mailbox_quota_included === 1 ? '' : 'es'} included`)
  }
  return points
}

function statusLine(sub: CappeSubscription | null): string {
  if (!sub) return 'No paid subscription. Pick a plan below when you’re ready.'
  if (sub.source !== 'stripe') {
    return sub.comped_until ? `Provided by Gummfit until ${day(sub.comped_until)}.` : 'Provided by Gummfit.'
  }
  if (sub.cancel_at_period_end) return `Cancels on ${day(sub.current_period_end)}. You keep the plan until then.`
  if (sub.status === 'trialing') return `Intro period until ${day(sub.trial_end ?? sub.current_period_end)}, then billed ${sub.interval}ly.`
  if (sub.status === 'active') return `Billed ${sub.interval}ly. Renews on ${day(sub.current_period_end)}.`
  return 'There’s a problem with your last payment. Update your card under “Manage billing”.'
}

// Plan & billing (/cappe/billing). Checkout, plan changes and the Stripe portal
// all go through the existing /billing endpoints; the plan an account is on is
// only ever set from Stripe state, so this page reads it back rather than
// assuming a click succeeded.
export default function CappeBilling() {
  const [params, setParams] = useSearchParams()
  const { account, refresh } = useCappeMe()
  // What the URL asked for on arrival. Read once: the query is cleared straight
  // away so a reload does not start checkout, or re-announce a payment, twice.
  const [arrival] = useState(() => ({ start: params.get('start'), checkout: params.get('checkout') }))
  const [catalog, setCatalog] = useState<CappeCatalog | null>(null)
  // undefined = not loaded yet; null = loaded, no subscription.
  const [sub, setSub] = useState<CappeSubscription | null | undefined>(undefined)
  const [interval, setBillingInterval] = useState<CappeBillingInterval>(params.get('interval') === 'year' ? 'year' : 'month')
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<Notice | null>(
    arrival.checkout === 'cancelled' ? { tone: 'info', text: 'Checkout cancelled. Nothing was charged.' } : null,
  )
  const paidReturn = arrival.checkout === 'success' || arrival.checkout === 'return'
  const [confirming, setConfirming] = useState<'polling' | 'slow' | null>(paidReturn ? 'polling' : null)
  const [attempt, setAttempt] = useState(0)
  // Whether we KNOW a payment happened (Stripe's own success return).
  const [definite, setDefinite] = useState(arrival.checkout === 'success')

  const beginCheckout = useCallback(async (plan: CappeBillingPlan, at: CappeBillingInterval) => {
    setBusy(plan.code)
    setError(null)
    try {
      const res = await cappeApi.post<{ checkout_url: string }>('/billing/checkout', {
        plan_code: plan.code,
        interval: at,
        success_url: billingUrl('?checkout=success'),
        cancel_url: billingUrl('?checkout=cancelled'),
      })
      // Same tab: the session lives in this tab's storage.
      window.location.assign(res.checkout_url)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start checkout.')
      setBusy(null)
    }
  }, [])

  // The payment poll, driven by `confirming === 'polling'` (the page starts
  // there on a paid return; "Check again" puts it back). One request per tick.
  useEffect(() => {
    if (confirming !== 'polling') return
    let alive = true
    const timer = setTimeout(async () => {
      let fresh: CappeSubscription | null = null
      try {
        fresh = await cappeApi.get<CappeSubscription | null>('/billing/subscription')
      } catch { /* a blip mid-poll: treat as "not yet" */ }
      if (!alive) return
      if (fresh && LIVE.has(fresh.status)) {
        setSub(fresh)
        setConfirming(null)
        setNotice({ tone: 'ok', text: `You’re on the ${fresh.plan_name ?? fresh.plan_code} plan. Thanks for subscribing.` })
        void refresh()
      } else if (attempt + 1 < POLL_TRIES) {
        setAttempt(attempt + 1)
      } else if (definite) {
        setConfirming('slow')
      } else {
        // `checkout=return` is also where a cancelled checkout can land, so no
        // subscription here is not evidence of a payment.
        setConfirming(null)
        setNotice({ tone: 'info', text: 'If you completed checkout, your plan will update here shortly.' })
      }
    }, attempt === 0 ? 0 : POLL_MS)
    return () => { alive = false; clearTimeout(timer) }
  }, [confirming, attempt, definite, refresh])

  useEffect(() => {
    let alive = true
    if (arrival.start || arrival.checkout) setParams({}, { replace: true })
    Promise.all([
      cappeApi.get<CappeCatalog>('/billing/catalog'),
      cappeApi.get<CappeSubscription | null>('/billing/subscription'),
    ])
      .then(([c, s]) => {
        if (!alive) return
        setCatalog(c)
        // The payment poll owns `sub` while it runs; don't race it backwards.
        if (!paidReturn) setSub(s)
        else setSub((current) => current ?? s)
        if (!arrival.start) return
        // Arriving from signup with a plan already picked: go straight to
        // checkout. Anything that makes that impossible leaves the person on
        // this page with the reason, never on a blank redirect.
        const plan = c.plans.find((p) => p.code === arrival.start)
        const at = plan ? buyable(plan, interval) : null
        if (s?.source === 'stripe') {
          setNotice({ tone: 'info', text: 'You already have a subscription. You can switch plans below.' })
        } else if (!plan || !at) {
          setNotice({ tone: 'warn', text: 'That plan isn’t available right now. Choose one below.' })
        } else {
          void beginCheckout(plan, at)
        }
      })
      .catch((e) => { if (alive) setError(e instanceof Error ? e.message : 'Could not load billing.') })
    return () => { alive = false }
    // Runs once, for the URL the page was opened with.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function changePlan(plan: CappeBillingPlan, at: CappeBillingInterval) {
    const price = priceFor(plan, at)
    const label = price ? `${formatCents(price.unit_amount_cents, price.currency)}/${at}` : plan.name
    if (!window.confirm(`Switch to ${plan.name} at ${label}? The difference is charged or credited to you now.`)) return
    setBusy(plan.code)
    setError(null)
    try {
      const fresh = await cappeApi.post<CappeSubscription>('/billing/change-plan', { plan_code: plan.code, interval: at })
      setSub(fresh)
      setNotice({ tone: 'ok', text: `You’re now on ${fresh.plan_name ?? plan.name}.` })
      void refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not change your plan.')
    } finally {
      setBusy(null)
    }
  }

  async function openPortal() {
    setBusy('portal')
    setError(null)
    try {
      const res = await cappeApi.post<{ portal_url: string }>('/billing/portal', { return_url: billingUrl() })
      window.location.assign(res.portal_url)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not open billing.')
      setBusy(null)
    }
  }

  const loaded = catalog !== null && sub !== undefined
  const subscribed = sub?.source === 'stripe'
  const currentCode = sub?.plan_code ?? account?.plan ?? 'free'
  const currentName = sub?.plan_name ?? catalog?.plans.find((p) => p.code === currentCode)?.name ?? currentCode
  const hasYearly = catalog?.plans.some((p) => priceFor(p, 'year')) ?? false

  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-8">
      <div className="mb-8">
        <h1 className={ui.heading}>Plan &amp; billing</h1>
        <p className={`mt-1 ${ui.subtitle}`}>Change your plan, update your card, or download invoices.</p>
      </div>

      {error && <p role="alert" className="mb-4 text-sm text-red-400">{error}</p>}

      {confirming === 'polling' && (
        <p role="status" className={`mb-4 flex items-center gap-2 rounded-xl border px-4 py-3 text-sm ${NOTICE_TONE.info}`}>
          <Loader2 className="h-4 w-4 animate-spin" /> Confirming your payment…
        </p>
      )}
      {confirming === 'slow' && (
        <div role="status" className={`mb-4 flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3 text-sm ${NOTICE_TONE.warn}`}>
          <CircleAlert className="h-4 w-4 shrink-0" />
          <span className="flex-1">
            Your payment went through, but your plan hasn’t updated yet. This usually takes under a minute.
          </span>
          <button type="button" onClick={() => { setAttempt(0); setDefinite(true); setConfirming('polling') }} className={ui.btnGhost}>Check again</button>
        </div>
      )}
      {notice && !confirming && (
        <p role="status" className={`mb-4 rounded-xl border px-4 py-3 text-sm ${NOTICE_TONE[notice.tone]}`}>{notice.text}</p>
      )}

      {!loaded ? (
        !error && (
          <div className="flex justify-center py-20">
            <Loader2 className="h-6 w-6 animate-spin text-zinc-600" />
          </div>
        )
      ) : (
        <>
          <section className={`mb-8 flex flex-wrap items-center gap-4 p-5 ${ui.card}`}>
            <CreditCard className="h-5 w-5 text-lime-300" />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold text-zinc-100">
                Current plan: <span className="capitalize">{currentName}</span>
              </div>
              <div className="mt-0.5 text-xs text-zinc-400">{statusLine(sub ?? null)}</div>
            </div>
            {subscribed && (
              <button type="button" onClick={openPortal} disabled={busy !== null} className={ui.btnGhost}>
                {busy === 'portal' && <Loader2 className="h-4 w-4 animate-spin" />}
                Manage billing
              </button>
            )}
          </section>
          {subscribed && (
            <p className="-mt-5 mb-8 text-xs text-zinc-500">
              “Manage billing” opens Stripe, where you can update your card, download invoices, or cancel.
            </p>
          )}

          {hasYearly && (
            <div className="mb-4 inline-flex rounded-lg border border-zinc-800 bg-zinc-900 p-1" role="group" aria-label="Billing interval">
              {(['month', 'year'] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={interval === value}
                  onClick={() => setBillingInterval(value)}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium ${interval === value ? 'bg-zinc-800 text-zinc-50' : 'text-zinc-400 hover:text-zinc-200'}`}
                >
                  {value === 'month' ? 'Monthly' : 'Yearly'}
                </button>
              ))}
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {catalog.plans.map((plan) => {
              const at = buyable(plan, interval)
              const price = at ? priceFor(plan, at) : undefined
              const isCurrent = plan.code === currentCode && (!subscribed || !at || sub?.interval === at)
              const intro = !subscribed && catalog.intro_available && plan.intro_price_cents !== null && plan.intro_days
              return (
                <article
                  key={plan.code}
                  data-testid={`billing-plan-${plan.code}`}
                  className={`flex flex-col p-5 ${ui.card} ${plan.code === currentCode ? 'border-lime-400/40' : ''}`}
                >
                  <h2 className="text-base font-semibold text-zinc-50">{plan.name}</h2>
                  {plan.description && <p className="mt-1 text-xs leading-relaxed text-zinc-400">{plan.description}</p>}
                  <p className="mt-4 text-2xl font-semibold tracking-tight text-zinc-50">
                    {price ? formatCents(price.unit_amount_cents, price.currency) : 'Free'}
                    {price && <span className="text-sm font-normal text-zinc-500"> / {at}</span>}
                  </p>
                  {intro && (
                    <p className="mt-1 text-xs font-medium text-lime-300">
                      {formatCents(plan.intro_price_cents ?? 0)} for your first {plan.intro_days} days
                    </p>
                  )}
                  <ul className="mt-4 flex-1 space-y-1.5 text-xs text-zinc-300">
                    {planPoints(plan).map((point) => (
                      <li key={point} className="flex items-start gap-2"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-lime-300" /> {point}</li>
                    ))}
                  </ul>
                  <div className="mt-5">
                    {isCurrent ? (
                      <span className="inline-flex w-full items-center justify-center rounded-lg border border-zinc-700 px-4 py-2 text-sm font-medium text-zinc-400">
                        Current plan
                      </span>
                    ) : !at ? (
                      // The free tier is not something you check out for.
                      <p className="text-center text-xs text-zinc-500">
                        {subscribed ? 'To move to Free, cancel under “Manage billing”.' : 'Not available right now.'}
                      </p>
                    ) : (
                      <button
                        type="button"
                        disabled={busy !== null || confirming === 'polling'}
                        onClick={() => (subscribed ? changePlan(plan, at) : beginCheckout(plan, at))}
                        className={`w-full ${ui.btnPrimary}`}
                      >
                        {busy === plan.code && <Loader2 className="h-4 w-4 animate-spin" />}
                        {subscribed ? `Switch to ${plan.name}` : `Choose ${plan.name}`}
                      </button>
                    )}
                  </div>
                </article>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
