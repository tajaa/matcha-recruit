import { useEffect, useState } from 'react'
import { Gauge, Loader2, ArrowUpRight } from 'lucide-react'
import { Card } from '../../components/ui'
import { fetchRiskProfile } from '../../api/riskIndex'
import type { RiskIndex } from '../../types/riskIndex'
import { RISK_BAND_TONE } from '../../types/riskIndex'

export default function RiskProfile() {
  const [data, setData] = useState<RiskIndex | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchRiskProfile().then(setData).finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>
  }
  if (!data) return <div className="text-sm text-zinc-500">Risk profile unavailable.</div>

  const tone = data.band ? RISK_BAND_TONE[data.band] ?? 'text-zinc-200' : 'text-zinc-500'

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
          <Gauge className="h-5 w-5 text-zinc-400" /> Risk Profile
        </h1>
        <p className="text-sm text-zinc-500 mt-1">Your insurability at a glance — a composite of workers'-comp, EPL, and compliance posture. The cleaner this is, the better the terms your broker can win at renewal.</p>
      </div>

      {/* Index hero */}
      <Card className="p-6 flex items-center gap-8">
        <div className="text-center">
          <div className={`text-6xl font-light font-mono ${tone}`}>{data.index ?? '—'}</div>
          <div className={`text-xs uppercase tracking-widest font-bold mt-1 ${tone}`}>{data.band ?? 'no data'}</div>
          <div className="text-[10px] text-zinc-600 mt-0.5">/ 100 risk index</div>
        </div>
        <div className="flex-1 space-y-3">
          {data.components.map((c) => (
            <div key={c.key}>
              <div className="flex items-center justify-between text-xs mb-1">
                <span className="text-zinc-300">{c.label} <span className="text-zinc-600">· wt {c.weight}</span></span>
                <span className="font-mono text-zinc-200">{c.score}/100</span>
              </div>
              <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                <div className={`h-full ${c.score >= 80 ? 'bg-emerald-500' : c.score >= 60 ? 'bg-zinc-400' : c.score >= 35 ? 'bg-amber-500' : 'bg-red-500'}`} style={{ width: `${c.score}%` }} />
              </div>
              <div className="text-[11px] text-zinc-600 mt-0.5">{c.detail}</div>
            </div>
          ))}
        </div>
      </Card>

      {/* Top fixes */}
      {data.top_fixes.length > 0 && (
        <Card className="p-5">
          <h3 className="text-sm font-medium text-zinc-200 tracking-wide mb-3">How to improve your terms</h3>
          <ul className="space-y-2">
            {data.top_fixes.map((f, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-zinc-300">
                <ArrowUpRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span className="capitalize">{f}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
