import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import ClientSidebar from './ClientSidebar'
import IrSidebar from '../tier-sidebars/IrSidebar'
import MatchaXSidebar from '../tier-sidebars/MatchaXSidebar'
import ComplianceSidebar from '../tier-sidebars/ComplianceSidebar'
import { useMe } from '../../hooks/useMe'
import { isIrOnlyTier, isMatchaLitePending, isMatchaX, isMatchaXPending, isMatchaCompliance, isMatchaCompliancePending } from '../../utils/tier'
import { useMatchaLitePricing, computeLitePriceDollars } from '../../api/matchaLitePricing'
import { api, ApiError } from '../../api/client'

/**
 * Routes the tenant to the right sidebar based on signup tier:
 *  - ir_only_self_serve / matcha_lite (paid) → slim IR nav
 *  - matcha_lite (pending payment) → complete-subscription prompt
 *  - else → full ClientSidebar (bespoke, personal, etc.)
 *
 * Defaults to ClientSidebar while /auth/me is in flight to avoid a flash
 * of the wrong layout for the dominant case.
 */
// TODO: set the real Matcha-X price. Mirrors Lite's stub for now — keep in
// sync with matcha_x_price_cents() in server/app/core/services/stripe_service.py.
function matchaXPriceDollars(headcount: number): number {
  return Math.ceil(headcount / 10) * 100
}


export default function TenantSidebar() {
  const { me, loading } = useMe()
  if (loading) return <ClientSidebar />
  if (isMatchaXPending(me?.profile)) return <MatchaXPendingSidebar headcount={me?.profile?.headcount ?? 0} />
  if (isMatchaX(me?.profile)) return <MatchaXSidebar />
  if (isMatchaCompliancePending(me?.profile)) return <CompliancePendingSidebar headcount={me?.profile?.headcount ?? 0} jurisdictionCount={me?.profile?.jurisdiction_count ?? 0} />
  if (isMatchaCompliance(me?.profile)) return <ComplianceSidebar />
  if (isMatchaLitePending(me?.profile)) return (
    <MatchaLitePendingSidebar
      headcount={me?.profile?.headcount ?? 0}
      isEssentials={me?.profile?.signup_source === 'matcha_lite_essentials'}
    />
  )
  if (isIrOnlyTier(me?.profile)) return <IrSidebar />
  return <ClientSidebar />
}

function MatchaLitePendingSidebar({ headcount, isEssentials }: { headcount: number; isEssentials: boolean }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const pricing = useMatchaLitePricing(isEssentials ? 'matcha_lite_essentials' : 'matcha_lite')
  const maxHeadcount = pricing?.max_headcount ?? 300

  const validHeadcount = headcount >= 1 && headcount <= maxHeadcount
  const price = validHeadcount && pricing ? computeLitePriceDollars(headcount, pricing) : null

  async function handleSubscribe() {
    setLoading(true)
    setError(null)
    try {
      const { checkout_url } = await api.post<{ checkout_url: string }>('/resources/checkout/lite', {
        success_url: `${window.location.origin}/ir/onboarding?lite=1`,
        cancel_url: window.location.href,
      })
      window.location.href = checkout_url
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Something went wrong. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full bg-zinc-950 border-r border-zinc-800 p-5">
      <div className="mb-6">
        <h2 className="text-sm font-semibold text-zinc-100 mb-1">Complete your subscription</h2>
        <p className="text-xs text-zinc-400">
          {isEssentials
            ? 'Activate Matcha Lite Essentials to access incident reporting and HR resources.'
            : 'Activate Matcha Lite to access incident reporting, employee management, and HR resources.'}
        </p>
      </div>

      <div className="space-y-4">
        {price !== null ? (
          <p className="text-xs text-zinc-400">
            <span className="text-zinc-100 font-medium">${price}/month</span> for {headcount} employee{headcount !== 1 ? 's' : ''}
          </p>
        ) : headcount > maxHeadcount ? (
          <p className="text-xs text-red-400">
            Over {maxHeadcount} employees —{' '}
            <a href="mailto:hello@matcha.work" className="underline">contact us</a>
          </p>
        ) : null}

        {error && <p className="text-xs text-red-400">{error}</p>}

        <button
          onClick={handleSubscribe}
          disabled={!validHeadcount || loading}
          className="w-full bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white text-sm font-medium py-2 rounded transition-colors flex items-center justify-center gap-2"
        >
          {loading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
          Subscribe
        </button>
      </div>
    </div>
  )
}

// Pending sidebar for the standalone Matcha Compliance product: posts to the
// /resources/checkout/compliance endpoint and returns to /compliance/onboarding
// on success. jurisdictionCount is shown for context only — no longer part of price.
function CompliancePendingSidebar({ headcount, jurisdictionCount }: { headcount: number; jurisdictionCount: number }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const pricing = useMatchaLitePricing('matcha_compliance')
  const maxHeadcount = pricing?.max_headcount ?? 300

  const validHeadcount = headcount >= 1 && headcount <= maxHeadcount
  const price = validHeadcount && pricing ? computeLitePriceDollars(headcount, pricing) : null

  async function handleSubscribe() {
    setLoading(true)
    setError(null)
    try {
      const { checkout_url } = await api.post<{ checkout_url: string }>('/resources/checkout/compliance', {
        success_url: `${window.location.origin}/compliance/onboarding?compliance=1`,
        cancel_url: window.location.href,
      })
      window.location.href = checkout_url
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Something went wrong. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full bg-zinc-950 border-r border-zinc-800 p-5">
      <div className="mb-6">
        <h2 className="text-sm font-semibold text-zinc-100 mb-1">Complete your subscription</h2>
        <p className="text-xs text-zinc-400">
          Activate Matcha Compliance to access jurisdiction-aware compliance tracking, alerts, and action plans.
        </p>
      </div>

      <div className="space-y-4">
        {price !== null ? (
          <>
            <p className="text-xs text-zinc-400">
              <span className="text-zinc-100 font-medium">${price}/month</span> for {headcount} employee{headcount !== 1 ? 's' : ''}
            </p>
            {jurisdictionCount > 0 && (
              <p className="text-xs text-zinc-500">Tracking {jurisdictionCount} jurisdiction{jurisdictionCount !== 1 ? 's' : ''}</p>
            )}
          </>
        ) : headcount > maxHeadcount ? (
          <p className="text-xs text-red-400">
            Over {maxHeadcount} employees —{' '}
            <a href="mailto:hello@matcha.work" className="underline">contact us</a>
          </p>
        ) : null}

        {error && <p className="text-xs text-red-400">{error}</p>}

        <button
          onClick={handleSubscribe}
          disabled={!validHeadcount || loading}
          className="w-full bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white text-sm font-medium py-2 rounded transition-colors flex items-center justify-center gap-2"
        >
          {loading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
          Subscribe
        </button>
      </div>
    </div>
  )
}

// Clone of MatchaLitePendingSidebar for the Matcha-X mid tier: posts to the
// /resources/checkout/x endpoint and returns to /matcha-x/onboarding on success.
function MatchaXPendingSidebar({ headcount }: { headcount: number }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const validHeadcount = headcount >= 1 && headcount <= 300
  const price = validHeadcount ? matchaXPriceDollars(headcount) : null

  async function handleSubscribe() {
    setLoading(true)
    setError(null)
    try {
      const { checkout_url } = await api.post<{ checkout_url: string }>('/resources/checkout/x', {
        success_url: `${window.location.origin}/matcha-x/onboarding?x=1`,
        cancel_url: window.location.href,
      })
      window.location.href = checkout_url
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Something went wrong. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full bg-zinc-950 border-r border-zinc-800 p-5">
      <div className="mb-6">
        <h2 className="text-sm font-semibold text-zinc-100 mb-1">Complete your subscription</h2>
        <p className="text-xs text-zinc-400">
          Activate Matcha-X to access incident reporting, employee management, and HR resources.
        </p>
      </div>

      <div className="space-y-4">
        {price !== null ? (
          <p className="text-xs text-zinc-400">
            <span className="text-zinc-100 font-medium">${price}/month</span> for {headcount} employee{headcount !== 1 ? 's' : ''}
          </p>
        ) : headcount > 300 ? (
          <p className="text-xs text-red-400">
            Over 300 employees —{' '}
            <a href="mailto:hello@matcha.work" className="underline">contact us</a>
          </p>
        ) : null}

        {error && <p className="text-xs text-red-400">{error}</p>}

        <button
          onClick={handleSubscribe}
          disabled={!validHeadcount || loading}
          className="w-full bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white text-sm font-medium py-2 rounded transition-colors flex items-center justify-center gap-2"
        >
          {loading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
          Subscribe
        </button>
      </div>
    </div>
  )
}
