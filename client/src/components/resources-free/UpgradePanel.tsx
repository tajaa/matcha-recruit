import { useState } from 'react'
import { AlertTriangle, MessageSquare, Sparkles } from 'lucide-react'

import { api } from '../../api/client'
import { PricingContactModal } from '../PricingContactModal'

interface CheckoutResponse {
  checkout_url: string
  stripe_session_id: string
}

/**
 * Two-action upgrade panel for resources_free tenants. Lives in the sidebar
 * footer.
 *
 * - "Upgrade to Matcha IR" → Stripe-hosted checkout. Webhook flips the
 *   company to incidents=true + signup_source=ir_only_self_serve, after
 *   which the tenant lands on the slim IR layout on next refresh.
 * - "Get full platform" → opens the existing PricingContactModal.
 */
export default function UpgradePanel() {
  const [contactOpen, setContactOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleUpgradeIr = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.post<CheckoutResponse>('/resources/upgrade/ir/checkout', {
        success_url: `${window.location.origin}/app/ir?upgraded=ir`,
        cancel_url: `${window.location.origin}/resources?upgrade_canceled=1`,
      })
      window.location.href = res.checkout_url
    } catch (err: any) {
      setError(err?.message ?? 'Could not start checkout')
      setLoading(false)
    }
  }

  return (
    <>
      <div className="rounded-md p-3 bg-gradient-to-br from-emerald-900/40 to-zinc-900/60 border border-emerald-800/40">
        <div className="flex items-center gap-1.5 mb-2">
          <Sparkles className="h-3.5 w-3.5 text-emerald-300" strokeWidth={2} />
          <span className="text-[11px] font-semibold uppercase tracking-wider text-emerald-300">
            Upgrade
          </span>
        </div>
        <p className="text-[11.5px] text-zinc-300 leading-snug mb-3">
          Add Matcha IR for incident reporting + employee management.
        </p>
        <button
          type="button"
          onClick={handleUpgradeIr}
          disabled={loading}
          className="flex items-center justify-center gap-1.5 w-full rounded-md px-2.5 py-1.5 text-[12px] font-medium bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white transition-colors"
        >
          <AlertTriangle className="h-3.5 w-3.5" strokeWidth={2} />
          {loading ? 'Starting…' : 'Upgrade to Matcha IR'}
        </button>
        {error && (
          <p className="text-[11px] text-red-400 mt-2">{error}</p>
        )}
        <button
          type="button"
          onClick={() => setContactOpen(true)}
          className="flex items-center justify-center gap-1.5 w-full mt-2 rounded-md px-2.5 py-1.5 text-[12px] font-medium border border-zinc-700 text-zinc-300 hover:bg-zinc-800/50 transition-colors"
        >
          <MessageSquare className="h-3.5 w-3.5" strokeWidth={1.6} />
          Get full platform
        </button>
      </div>

      <PricingContactModal
        isOpen={contactOpen}
        onClose={() => setContactOpen(false)}
      />
    </>
  )
}
