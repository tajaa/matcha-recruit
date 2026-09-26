import { useEffect, useRef, useState } from 'react'
import { Check, X } from 'lucide-react'
import type { PlanRequiredDetail } from '../../../api/client'
import { startPersonalCheckout } from '../../api/matchaWork/billing'

type CheckoutPlan = 'lite' | 'pro'

const copy: Record<string, string> = {
  projects_solo: 'Workspaces need Lite',
  projects_collab: 'Collab workspaces need Pro',
  journals_full: 'This journal type needs Lite',
  email_ai: 'Email AI drafting needs Lite',
  go_live: 'Going live needs Pro',
  paid_channels: 'Creator monetization needs Pro',
  ai_model_pro: 'The Pro AI model needs Pro',
  ai_quota: "You've used your free AI for now",
}

const plans: { plan: CheckoutPlan; price: string; features: string[] }[] = [
  {
    plan: 'lite',
    price: '$9/mo',
    features: [
      'Solo workspaces — docs, presentations, blogs',
      'All journal types — novel, screenplay, blog',
      'Email AI reply drafting',
      '4× the free AI quota',
    ],
  },
  {
    plan: 'pro',
    price: '$20/mo',
    features: [
      'Everything in Lite',
      'Pro AI model — deeper reasoning',
      'Collab workspaces — kanban, tickets, teams',
      'Go Live video & audio broadcasts',
      'Create paid channels & job postings',
      '20× the free AI quota',
    ],
  },
]

export default function PaywallModal({ detail, onClose }: { detail: PlanRequiredDetail; onClose: () => void }) {
  const [opening, setOpening] = useState<CheckoutPlan | null>(null)
  const [error, setError] = useState<string | null>(null)
  const closeButton = useRef<HTMLButtonElement>(null)
  const dialog = useRef<HTMLElement>(null)

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    closeButton.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      }
      if (event.key !== 'Tab') return
      const buttons = Array.from(dialog.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [])
      const first = buttons[0]
      const last = buttons[buttons.length - 1]
      if (!first || !last) return
      if (event.shiftKey && (document.activeElement === first || !dialog.current?.contains(document.activeElement))) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && (document.activeElement === last || !dialog.current?.contains(document.activeElement))) {
        event.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      if (previousFocus?.isConnected) previousFocus.focus()
    }
  }, [onClose])

  async function checkout(plan: CheckoutPlan) {
    if (opening) return
    setOpening(plan)
    setError(null)
    try {
      const { checkout_url } = await startPersonalCheckout(plan)
      window.location.assign(checkout_url)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not open checkout. Please try again.')
      setOpening(null)
    }
  }

  const currentPlan = detail.current_plan
  const headline = copy[detail.feature] ?? `Upgrade to ${detail.required_plan === 'lite' ? 'Lite' : 'Pro'}`

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 px-4 py-6"
      onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}
    >
      <section
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="paywall-title"
        className="max-h-[calc(100dvh-3rem)] w-full max-w-xl overflow-y-auto overscroll-contain rounded-xl border border-w-line bg-w-surface text-w-text shadow-2xl"
      >
        <div className="relative border-b border-w-line px-6 pb-5 pt-6 text-center">
          <button ref={closeButton} onClick={onClose} aria-label="Close upgrade options" className="absolute right-4 top-4 text-w-dim hover:text-w-text">
            <X size={18} />
          </button>
          <h2 id="paywall-title" className="text-xl font-bold">{headline}</h2>
          <p className="mt-2 text-sm text-w-dim">
            {detail.feature === 'ai_quota'
              ? currentPlan === 'free'
                ? 'Free includes a taste of the AI. Lite and Pro raise your limit substantially.'
                : 'Pro raises your AI limit substantially.'
              : 'Channels, messaging, and basic journals stay free forever.'}
          </p>
        </div>
        <div className="grid gap-3 p-5 sm:grid-cols-2">
          {plans.map(({ plan, price, features }) => {
            const isCurrent = currentPlan === plan
            const included = plan === 'lite' && currentPlan === 'pro'
            const insufficient = plan === 'lite' && detail.required_plan === 'pro'
            const disabled = isCurrent || included || insufficient || currentPlan === 'business' || opening !== null
            const buttonLabel = isCurrent ? 'Current plan'
              : included ? 'Included in Pro'
                : insufficient ? 'Pro required for this feature'
                : opening === plan ? 'Opening checkout…'
                  : plan === 'pro' && currentPlan === 'lite' ? 'Upgrade to Pro'
                    : `Get ${plan === 'lite' ? 'Lite' : 'Pro'}`
            return (
              <div key={plan} className={`flex flex-col rounded-xl border p-4 ${plan === 'pro' ? 'border-w-accent/50' : 'border-w-line'}`}>
                <div className="flex items-baseline gap-2">
                  <h3 className="font-semibold capitalize">{plan}</h3>
                  <span className="text-sm text-w-dim">{price}</span>
                </div>
                <ul className="my-4 flex-1 space-y-2">
                  {features.map((feature) => (
                    <li key={feature} className="flex gap-2 text-xs text-w-dim">
                      <Check size={14} className="shrink-0 text-w-accent" />
                      {feature}
                    </li>
                  ))}
                </ul>
                <button
                  onClick={() => void checkout(plan)}
                  disabled={disabled}
                  className="rounded-md bg-w-accent px-3 py-2 text-sm font-semibold text-black hover:bg-w-accent-hi disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {buttonLabel}
                </button>
              </div>
            )
          })}
        </div>
        {error && <p role="alert" className="px-5 pb-3 text-center text-sm text-red-400">{error}</p>}
        <p className="px-5 pb-5 text-center text-xs text-w-dim">
          Subscriptions are billed through Stripe and renew monthly. Cancel anytime.
        </p>
      </section>
    </div>
  )
}
