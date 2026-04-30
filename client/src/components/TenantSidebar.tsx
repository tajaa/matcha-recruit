import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import ClientSidebar from './ClientSidebar'
import IrSidebar from './ir-only/IrSidebar'
import ResourcesFreeSidebar from './resources-free/ResourcesFreeSidebar'
import { useMe } from '../hooks/useMe'
import { isIrOnlyTier, isResourcesFreeTier, isMatchaLitePending } from '../utils/tier'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

/**
 * Routes the tenant to the right sidebar based on signup tier:
 *  - resources_free → slim Resources nav + upgrade panel
 *  - ir_only_self_serve / matcha_lite (paid) → slim IR nav
 *  - matcha_lite (pending payment) → complete-subscription prompt
 *  - else → full ClientSidebar (bespoke, personal, etc.)
 *
 * Defaults to ClientSidebar while /auth/me is in flight to avoid a flash
 * of the wrong layout for the dominant case.
 */
function litePriceDollars(headcount: number): number {
  return Math.ceil(headcount / 10) * 100
}

export default function TenantSidebar() {
  const { me, loading } = useMe()
  if (loading) return <ClientSidebar />
  if (isMatchaLitePending(me?.profile)) return <MatchaLitePendingSidebar headcount={me?.profile?.headcount ?? 0} />
  if (isResourcesFreeTier(me?.profile)) return <ResourcesFreeSidebar />
  if (isIrOnlyTier(me?.profile)) return <IrSidebar />
  return <ClientSidebar />
}

function MatchaLitePendingSidebar({ headcount }: { headcount: number }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const validHeadcount = headcount >= 1 && headcount <= 300
  const price = validHeadcount ? litePriceDollars(headcount) : null

  async function handleSubscribe() {
    setLoading(true)
    setError(null)
    try {
      const token = localStorage.getItem('matcha_access_token')
      const res = await fetch(`${BASE}/resources/checkout/lite`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          success_url: `${window.location.origin}/ir/onboarding?lite=1`,
          cancel_url: window.location.href,
        }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail ?? 'Failed to start checkout')
        return
      }
      window.location.href = data.checkout_url
    } catch {
      setError('Something went wrong. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full bg-zinc-950 border-r border-zinc-800 p-5">
      <div className="mb-6">
        <h2 className="text-sm font-semibold text-zinc-100 mb-1">Complete your subscription</h2>
        <p className="text-xs text-zinc-400">
          Activate Matcha Lite to access incident reporting, employee management, and HR resources.
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
