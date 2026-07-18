import { useEffect, useState } from 'react'
import { Loader2, ArrowUpRight } from 'lucide-react'
import { createLiteUpgradeCheckout } from '../../api/billing/liteAddons'
import { computeLitePriceDollars, useMatchaLitePricing } from '../../api/billing/matchaLitePricing'

/** Sidebar-footer upgrade card for Essentials tenants (Essentials → standard
 *  Lite). Checkout-first: nothing changes until Stripe payment completes, at
 *  which point the webhook flips signup_source and the tier overlay restores
 *  `employees` + `osha_logs`. */
export default function EssentialsUpgradePanel({ headcount, nudge = 0 }: { headcount: number; nudge?: number }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const pricing = useMatchaLitePricing('matcha_lite')
  const maxHeadcount = pricing?.max_headcount ?? 300

  const validHeadcount = headcount >= 1 && headcount <= maxHeadcount
  const price = validHeadcount && pricing ? computeLitePriceDollars(headcount, pricing) : null

  // Brief pulse each time a locked nav item routes the user here.
  const [pulsing, setPulsing] = useState(false)
  useEffect(() => {
    if (nudge === 0) return
    setPulsing(true)
    const t = setTimeout(() => setPulsing(false), 1600)
    return () => clearTimeout(t)
  }, [nudge])

  async function handleUpgrade() {
    setLoading(true)
    setError(null)
    try {
      const { checkout_url } = await createLiteUpgradeCheckout(
        `${window.location.origin}/app/upgrade/complete`,
        window.location.href,
      )
      window.location.href = checkout_url
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start checkout')
      setLoading(false)
    }
  }

  return (
    <div
      className={`rounded-lg border bg-zinc-900 p-3 transition-all duration-300 ${
        pulsing ? 'border-emerald-500/60 ring-2 ring-emerald-500/25' : 'border-zinc-800'
      }`}
    >
      <p className="text-[12px] font-medium text-zinc-200">Upgrade to Matcha Lite</p>
      <p className="mt-1 text-[11px] text-zinc-500 leading-relaxed">
        Unlock your employee roster + OSHA logs and the full insight suite.
      </p>
      {price !== null ? (
        <p className="mt-1.5 text-[11px] text-zinc-500">
          <span className="text-zinc-200 font-medium">${price}/month</span> for {headcount} employee{headcount !== 1 ? 's' : ''}
        </p>
      ) : headcount > maxHeadcount ? (
        <p className="mt-1.5 text-[11px] text-amber-400">
          Over {maxHeadcount} employees — <a href="mailto:hello@matcha.work" className="underline">contact us</a>
        </p>
      ) : null}
      {error && <p className="mt-1.5 text-[11px] text-red-400">{error}</p>}
      <button
        type="button"
        onClick={handleUpgrade}
        disabled={!validHeadcount || loading}
        className="mt-2.5 w-full bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white text-[12px] font-medium py-1.5 rounded transition-colors flex items-center justify-center gap-1.5"
      >
        {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <ArrowUpRight className="w-3 h-3" />}
        Upgrade
      </button>
    </div>
  )
}
