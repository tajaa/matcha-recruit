import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Shield, TrendingDown, TrendingUp, Minus } from 'lucide-react'
import { api } from '../../api/client'

type Severity = 'good' | 'fair' | 'at_risk' | 'critical' | 'unknown'

type Benchmark = { sector: string; label: string; trir: number; dart: number } | null

type PremiumImpact = {
  base_premium_estimate: number
  mod_swing: number
  annual_impact_dollars: number
  direction: 'increase' | 'decrease' | 'neutral'
} | null

type PortfolioRow = {
  company_id: string
  company_name: string
  industry: string | null
  headcount: number | null
  recordable_cases: number
  dart_cases: number
  lost_days: number
  trir: number | null
  dart_rate: number | null
  days_since_last_recordable: number | null
  trir_delta_pct: number | null
  benchmark: Benchmark
  premium_impact: PremiumImpact
  severity_band: Severity
  data_quality: { insufficient_population: boolean; headcount_missing: boolean }
}

type Portfolio = {
  summary: {
    client_count: number
    critical: number
    at_risk: number
    fair: number
    good: number
    unknown: number
    total_recordable_cases: number
    total_lost_days: number
  }
  companies: PortfolioRow[]
}

const BAND_TONE: Record<Severity, { dot: string; text: string; bg: string; label: string }> = {
  critical: { dot: 'bg-red-500',     text: 'text-red-400',     bg: 'bg-red-500/10 border-red-500/20',         label: 'Critical' },
  at_risk:  { dot: 'bg-orange-500',  text: 'text-orange-400',  bg: 'bg-orange-500/10 border-orange-500/20',   label: 'At Risk' },
  fair:     { dot: 'bg-amber-500',   text: 'text-amber-400',   bg: 'bg-amber-500/10 border-amber-500/20',     label: 'Fair' },
  good:     { dot: 'bg-emerald-500', text: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/20', label: 'Good' },
  unknown:  { dot: 'bg-zinc-600',    text: 'text-zinc-500',    bg: 'bg-zinc-800 border-white/5',              label: 'Unknown' },
}

function fmtMoney(n: number): string {
  const abs = Math.abs(n)
  if (abs >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`
  if (abs >= 10_000) return `$${Math.round(n / 1000)}K`
  return `$${Math.round(n).toLocaleString()}`
}

function DeltaPill({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-zinc-700 text-[10px]">—</span>
  const Icon = pct < -1 ? TrendingDown : pct > 1 ? TrendingUp : Minus
  const tone = pct < -5 ? 'text-emerald-400' : pct > 5 ? 'text-red-400' : 'text-zinc-500'
  const sign = pct > 0 ? '+' : ''
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-mono ${tone}`}>
      <Icon className="w-3 h-3" />
      {sign}{pct.toFixed(0)}%
    </span>
  )
}

function streakLabel(days: number | null): string {
  if (days === null) return '∞'
  if (days < 60) return `${days}d`
  if (days < 730) return `${Math.floor(days / 30)}mo`
  return `${(days / 365).toFixed(1)}y`
}

const SUMMARY_BANDS: Array<{ key: keyof Portfolio['summary']; label: string; tone: string }> = [
  { key: 'critical', label: 'Critical', tone: 'text-red-400' },
  { key: 'at_risk',  label: 'At Risk',  tone: 'text-orange-400' },
  { key: 'fair',     label: 'Fair',     tone: 'text-amber-400' },
  { key: 'good',     label: 'Good',     tone: 'text-emerald-400' },
]

export default function BrokerWcPortfolio() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.get<Portfolio>('/broker/wc-portfolio')
      .then(setPortfolio)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load portfolio'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100 flex items-center gap-2">
          <Shield className="w-5 h-5 text-zinc-500" />
          WC Portfolio
        </h1>
        <p className="mt-1 text-[10px] text-zinc-500 font-mono uppercase tracking-wider">
          Workers Comp posture across your active book · trailing 12 months
        </p>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-2xl p-4 text-sm text-red-400">{error}</div>
      )}

      {loading ? (
        <div className="flex items-center justify-center min-h-[40vh]">
          <div className="text-xs text-zinc-500 uppercase tracking-widest font-mono animate-pulse">Loading portfolio…</div>
        </div>
      ) : !portfolio || portfolio.companies.length === 0 ? (
        <div className="bg-zinc-900 border border-white/10 rounded-2xl p-12 text-center">
          <p className="text-sm text-zinc-400">No active client links yet.</p>
          <p className="text-[11px] text-zinc-600 mt-1">Link clients via the Client Onboarding flow to see them here.</p>
        </div>
      ) : (
        <>
          {/* Summary strip */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-px bg-white/10 border border-white/10 rounded-2xl overflow-hidden">
            <div className="bg-zinc-900 px-5 py-5">
              <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Clients</div>
              <div className="text-3xl font-light font-mono mt-2 text-zinc-100">{portfolio.summary.client_count}</div>
            </div>
            {SUMMARY_BANDS.map((b) => {
              const v = portfolio.summary[b.key] as number
              return (
                <div key={b.key} className="bg-zinc-900 px-5 py-5">
                  <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">{b.label}</div>
                  <div className={`text-3xl font-light font-mono mt-2 ${v > 0 ? b.tone : 'text-zinc-700'}`}>{v}</div>
                </div>
              )
            })}
          </div>

          {/* Table */}
          <div className="bg-zinc-900 border border-white/10 rounded-2xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="bg-zinc-950/50 text-zinc-500">
                  <tr>
                    <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Band</th>
                    <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Company</th>
                    <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Industry</th>
                    <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold text-right">FTE</th>
                    <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold text-right">TRIR</th>
                    <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold text-right">DART</th>
                    <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold text-right">Lost Days</th>
                    <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold text-right">Streak</th>
                    <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold text-right">Premium Δ</th>
                  </tr>
                </thead>
                <tbody>
                  {portfolio.companies.map((c) => {
                    const tone = BAND_TONE[c.severity_band]
                    const trirRatio = c.benchmark && c.trir ? `${(c.trir / c.benchmark.trir).toFixed(1)}×` : '—'
                    return (
                      <tr key={c.company_id} className="border-t border-white/5 hover:bg-white/[0.02] transition-colors">
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-[10px] uppercase tracking-widest font-bold rounded ${tone.bg} ${tone.text}`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${tone.dot}`} />
                            {tone.label}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <Link
                            to={`/broker/clients/${c.company_id}`}
                            className="text-[13px] font-medium text-zinc-100 hover:text-emerald-400 transition-colors"
                          >
                            {c.company_name}
                          </Link>
                        </td>
                        <td className="px-4 py-3 text-[11px] text-zinc-500">
                          {c.benchmark?.label ?? c.industry ?? '—'}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-[11px] text-zinc-400">
                          {c.headcount ?? '—'}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className="font-mono text-[13px] text-zinc-100">{c.trir?.toFixed(2) ?? '—'}</div>
                          <div className="text-[9px] text-zinc-600 font-mono">{trirRatio} bench</div>
                          <div><DeltaPill pct={c.trir_delta_pct} /></div>
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-[13px] text-zinc-300">
                          {c.dart_rate?.toFixed(2) ?? '—'}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-[13px] text-zinc-300">
                          {c.lost_days}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-[12px] text-zinc-400">
                          {streakLabel(c.days_since_last_recordable)}
                        </td>
                        <td className="px-4 py-3 text-right">
                          {c.premium_impact ? (
                            <span className={`font-mono text-[12px] ${
                              c.premium_impact.direction === 'increase' ? 'text-red-400'
                              : c.premium_impact.direction === 'decrease' ? 'text-emerald-400'
                              : 'text-zinc-500'
                            }`}>
                              {c.premium_impact.annual_impact_dollars > 0 ? '+' : ''}{fmtMoney(c.premium_impact.annual_impact_dollars)}
                            </span>
                          ) : (
                            <span className="text-zinc-700 text-[10px]">—</span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <p className="text-[10px] text-zinc-600 leading-relaxed">
            TRIR/DART = OSHA standard formulas using assumed hours (headcount × 2,000). Benchmarks are BLS sector medians, not NCCI class-specific.
            Premium Δ is a directional estimate based on a 10pt-mod-per-1.0×-deviation rule × industry-average premium per FTE — <strong>not a quote</strong>.
          </p>
        </>
      )}
    </div>
  )
}
