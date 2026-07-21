import { AlertTriangle, Inbox, Sparkles } from 'lucide-react'
import type { IRAnalyticsSummary } from '../../types/ir'
import { MetricStrip } from '../ui/MetricStrip'

type MiniKey = 'open' | 'investigating' | 'critical' | 'high' | 'closed'

const MINIS: Array<{ key: MiniKey; label: string; tone: string }> = [
  { key: 'open',          label: 'Open',          tone: 'text-amber-400' },
  { key: 'investigating', label: 'Investigating', tone: 'text-orange-400' },
  { key: 'critical',      label: 'Critical',      tone: 'text-red-400' },
  { key: 'high',          label: 'High',          tone: 'text-orange-300' },
  { key: 'closed',        label: 'Closed',        tone: 'text-zinc-400' },
]

const NUM = 'font-light tabular-nums'

export function IRStatHero({ summary, captionLeft }: {
  summary: IRAnalyticsSummary
  captionLeft?: string
}) {
  const open = summary.open
  const critical = summary.critical
  return (
    <MetricStrip cols="grid-cols-1 lg:grid-cols-7" subtle>
      {/* Big number — span 2 of 7 */}
      <div className="lg:col-span-2 bg-zinc-900 px-7 py-7 flex flex-col">
        <div className="text-[10px] text-zinc-500 uppercase tracking-[0.16em]">
          {captionLeft ?? 'Total Incidents'}
        </div>
        <div className="mt-3 leading-none">
          <span className={`text-7xl ${NUM} text-zinc-100`} style={{ fontStretch: '75%' }}>
            {summary.total}
          </span>
        </div>
        <div className="mt-auto pt-5 flex flex-wrap items-center gap-3 text-[11px]">
          {critical > 0 ? (
            <span className="inline-flex items-center gap-1.5 text-red-400">
              <AlertTriangle className="w-3 h-3" strokeWidth={1.6} />
              <span className="tabular-nums">{critical}</span> critical
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 text-zinc-600">
              <Sparkles className="w-3 h-3" strokeWidth={1.6} />
              No critical incidents
            </span>
          )}
          {open > 0 && (
            <span className="inline-flex items-center gap-1.5 text-amber-400">
              <Inbox className="w-3 h-3" strokeWidth={1.6} />
              <span className="tabular-nums">{open}</span> open
            </span>
          )}
        </div>
      </div>

      {/* Mini stats */}
      {MINIS.map((m) => {
        const value = summary[m.key]
        const tone = value === 0 ? 'text-zinc-700' : m.tone
        return (
          <div key={m.key} className="bg-zinc-900 px-5 py-7 flex flex-col">
            <div className="text-[9px] text-zinc-500 uppercase tracking-[0.16em]">
              {m.label}
            </div>
            <div className={`mt-3 text-3xl ${NUM} ${tone} leading-none`} style={{ fontStretch: '75%' }}>
              {value}
            </div>
          </div>
        )
      })}
    </MetricStrip>
  )
}
