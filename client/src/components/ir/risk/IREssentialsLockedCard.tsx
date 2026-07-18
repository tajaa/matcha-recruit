import { useState } from 'react'
import { Activity, ArrowUpRight, Calendar, DollarSign, Heart, Loader2, Lock, TrendingUp, Users } from 'lucide-react'
import { createLiteUpgradeCheckout } from '../../../api/billing/liteAddons'

// Essentials replacement for the Workers' Comp metric cards. Those metrics
// are computed from OSHA recordable data maintained through the OSHA log
// tooling + employee roster — neither exists on Essentials, so rendering the
// real cards would show misleading zeros. Instead, render ghost previews that
// mirror the real cards (labels crisp, numbers blurred illustrative values)
// and route straight into the Essentials → Lite upgrade checkout.

/** Illustrative value, blurred beyond legibility. Never real data. */
function Blurred({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <span aria-hidden className={`blur-[7px] select-none ${className}`}>
      {children}
    </span>
  )
}

const GHOST_TILES = [
  { icon: Activity, label: 'TRIR', value: '3.42', tone: 'text-orange-400', sub: 'vs 2.7 median' },
  { icon: Activity, label: 'DART', value: '1.85', tone: 'text-amber-400', sub: 'vs 1.7 median' },
  { icon: Calendar, label: 'Lost Days', value: '27', tone: 'text-orange-400', sub: '+12 restricted' },
  { icon: Heart, label: 'Claims-Free Streak', value: '84', tone: 'text-amber-400', sub: 'days' },
]

// Trailing-8Q ghost bars — (non-DART, DART) stack heights in px.
const GHOST_QUARTERS: Array<{ q: string; nd: number; d: number }> = [
  { q: 'Q3', nd: 26, d: 10 },
  { q: 'Q4', nd: 34, d: 16 },
  { q: 'Q1', nd: 20, d: 8 },
  { q: 'Q2', nd: 42, d: 12 },
  { q: 'Q3', nd: 30, d: 20 },
  { q: 'Q4', nd: 16, d: 6 },
  { q: 'Q1', nd: 36, d: 10 },
  { q: 'Q2', nd: 24, d: 14 },
]

const GHOST_PEOPLE = [
  { name: 'Jordan Mercado', count: '4 incidents' },
  { name: 'Priya Natarajan', count: '3 incidents' },
  { name: 'Sam Whitfield', count: '2 incidents' },
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
        &mdash; both part of Matcha Lite. Sample view below; your numbers unlock on upgrade.
      </p>

      <div className="mt-4 space-y-4 pointer-events-none" aria-hidden>
        {/* WC posture stat tiles — mirrors IRWcMetricsCard */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-px bg-white/10 border border-white/10 rounded-2xl overflow-hidden">
          {GHOST_TILES.map((t) => (
            <div key={t.label} className="bg-zinc-950/70 p-5 flex flex-col">
              <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold flex items-center gap-1.5">
                <t.icon className="w-3 h-3" /> {t.label}
              </div>
              <div className={`text-3xl font-light font-mono mt-2 ${t.tone}`}>
                <Blurred>{t.value}</Blurred>
              </div>
              <div className="text-[9px] text-zinc-600 uppercase tracking-widest mt-2 font-mono">
                <Blurred className="blur-[4px]">{t.sub}</Blurred>
              </div>
            </div>
          ))}
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          {/* Premium impact — mirrors IRPremiumImpactCard */}
          <div className="rounded-2xl border border-red-500/20 bg-red-500/5 p-5">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-xl bg-red-500/10 flex items-center justify-center shrink-0">
                <TrendingUp className="w-4 h-4 text-red-400" />
              </div>
              <div className="min-w-0">
                <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold flex items-center gap-1.5">
                  <DollarSign className="w-3 h-3" /> Premium Impact Estimate
                </div>
                <div className="mt-1.5 flex items-baseline gap-2">
                  <span className="text-2xl font-light font-mono text-red-400">
                    +<Blurred>$18K</Blurred>
                  </span>
                  <span className="text-xs text-zinc-500">/ year directional</span>
                </div>
                <p className="text-[11px] text-zinc-500 mt-1.5 leading-relaxed">
                  Recordable trend points to a <Blurred className="blur-[4px]">~9pt</Blurred> premium-mod
                  swing at next renewal, worth <Blurred className="blur-[4px]">$18,400</Blurred>/yr
                  against your base premium.
                </p>
              </div>
            </div>
          </div>

          {/* Quarterly recordables — mirrors IRQuarterlyRecordableChart */}
          <div className="rounded-2xl border border-white/10 bg-zinc-950/50 p-5">
            <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">
              OSHA Recordables by Quarter · trailing 8Q
            </div>
            <div className="mt-3 flex items-end gap-2 h-24">
              {GHOST_QUARTERS.map((b, i) => (
                <div key={i} className="flex-1 flex flex-col items-center gap-1">
                  <div className="w-full flex flex-col justify-end" style={{ height: 72 }}>
                    <div className="w-full bg-red-500/80 rounded-t-[3px]" style={{ height: b.d }} />
                    <div className="w-full bg-amber-500/70" style={{ height: b.nd }} />
                  </div>
                  <span className="text-[9px] font-mono text-zinc-600">{b.q}</span>
                </div>
              ))}
            </div>
            <div className="flex items-center gap-4 mt-2.5 text-[9px] font-mono uppercase tracking-widest text-zinc-600">
              <span className="inline-flex items-center gap-1.5"><span className="w-2 h-2 bg-red-500/80" /> DART (lost-time)</span>
              <span className="inline-flex items-center gap-1.5"><span className="w-2 h-2 bg-amber-500/70" /> Non-DART</span>
            </div>
          </div>
        </div>

        {/* Roster-linked people — mirrors IRPeopleCard */}
        <div className="rounded-2xl border border-white/10 bg-zinc-950/50 p-5">
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold flex items-center gap-1.5">
            <Users className="w-3 h-3" /> Roster-linked incident history
          </div>
          <div className="mt-3 divide-y divide-zinc-800/60">
            {GHOST_PEOPLE.map((p) => (
              <div key={p.name} className="flex items-center justify-between gap-3 py-2">
                <span className="text-sm text-zinc-300"><Blurred className="blur-[5px]">{p.name}</Blurred></span>
                <span className="text-xs text-zinc-500"><Blurred className="blur-[4px]">{p.count}</Blurred></span>
              </div>
            ))}
          </div>
          <p className="mt-2 text-[10px] text-zinc-600">
            Incidents tied to real employee records — per-person patterns feed theme detection.
          </p>
        </div>
      </div>

      {error && <p className="mt-4 text-xs text-red-400">{error}</p>}
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
