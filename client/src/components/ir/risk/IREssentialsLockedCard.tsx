import { useState } from 'react'
import { ArrowUpRight, Loader2, Lock } from 'lucide-react'
import { createLiteUpgradeCheckout } from '../../../api/liteAddons'

// Essentials replacement for the Workers' Comp metric cards. Those metrics
// are computed from OSHA recordable data maintained through the OSHA log
// tooling + employee roster — neither exists on Essentials, so rendering the
// real cards would show misleading zeros. Tease what's missing instead and
// route straight into the Essentials → Lite upgrade checkout.
const LOCKED_METRICS = [
  {
    label: 'TRIR & DART rates',
    detail: 'OSHA-standard frequency rates benchmarked against your industry sector.',
  },
  {
    label: 'Premium impact estimate',
    detail: 'How your recordable history is likely moving your Workers’ Comp premium.',
  },
  {
    label: 'Quarterly recordable trend',
    detail: 'Trailing 8-quarter OSHA recordable bars — the chart underwriters ask for.',
  },
  {
    label: 'Roster-linked incident history',
    detail: 'Incidents tied to real employee records, with per-person patterns feeding theme detection.',
  },
]

export function IREssentialsLockedCard() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

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
    <section className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6">
      <div className="flex items-center gap-2 mb-1">
        <Lock className="w-3.5 h-3.5 text-zinc-500" strokeWidth={1.6} />
        <h2 className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">
          Workers&rsquo; Comp &amp; roster insights
        </h2>
      </div>
      <p className="text-xs text-zinc-500 leading-relaxed">
        These metrics are built from OSHA recordable logs and your employee roster
        &mdash; both part of Matcha Lite.
      </p>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {LOCKED_METRICS.map((m) => (
          <div key={m.label} className="rounded-xl border border-zinc-800/80 bg-zinc-950/40 p-4">
            <div className="flex items-center gap-2">
              <Lock className="w-3 h-3 text-zinc-600 shrink-0" strokeWidth={1.6} />
              <p className="text-sm font-medium text-zinc-300">{m.label}</p>
            </div>
            <p className="mt-1 text-xs text-zinc-600 leading-relaxed">{m.detail}</p>
          </div>
        ))}
      </div>

      {error && <p className="mt-3 text-xs text-red-400">{error}</p>}
      <div className="mt-4 flex flex-col sm:flex-row sm:items-center gap-3">
        <button
          type="button"
          onClick={handleUpgrade}
          disabled={loading}
          className="inline-flex items-center justify-center gap-1.5 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white text-xs font-medium px-4 py-2 rounded-lg transition-colors"
        >
          {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ArrowUpRight className="w-3.5 h-3.5" />}
          Upgrade &amp; connect employees
        </button>
        <p className="text-[11px] text-zinc-600">
          Want this data? Upgrading unlocks the roster, OSHA logs, and the full insight suite.
        </p>
      </div>
    </section>
  )
}
