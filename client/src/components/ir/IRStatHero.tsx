import { AlertTriangle, Inbox, Sparkles } from 'lucide-react'
import type { IRAnalyticsSummary } from '../../types/ir'

type MiniKey = 'open' | 'investigating' | 'critical' | 'high' | 'closed'

const MINIS: Array<{ key: MiniKey; label: string; tone: string; help: string }> = [
  { key: 'open',          label: 'Open',          tone: 'text-amber-400',  help: 'Reported but not yet assigned to an investigator.' },
  { key: 'investigating', label: 'Investigating', tone: 'text-orange-400', help: 'Active investigation underway.' },
  { key: 'critical',      label: 'Critical',      tone: 'text-red-400',    help: 'Critical-severity incidents (any status).' },
  { key: 'high',          label: 'High',          tone: 'text-orange-300', help: 'High-severity incidents (any status).' },
  { key: 'closed',        label: 'Closed',        tone: 'text-zinc-300',   help: 'Closed or resolved incidents.' },
]

export function IRStatHero({ summary, captionLeft }: {
  summary: IRAnalyticsSummary
  captionLeft?: string
}) {
  const open = summary.open
  const critical = summary.critical
  return (
    <div className="grid grid-cols-1 lg:grid-cols-7 gap-px bg-white/10 border border-white/10 rounded-2xl overflow-hidden">
      {/* Big number — span 2 of 7 */}
      <div className="lg:col-span-2 bg-zinc-900 p-8 flex flex-col justify-between">
        <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">
          {captionLeft ?? 'Total Incidents'}
        </div>
        <div className="flex items-end gap-4 mt-4">
          <span className="text-8xl font-light font-mono text-zinc-100">
            {summary.total}
          </span>
        </div>
        <div className="mt-6 flex flex-wrap items-center gap-3 text-[11px]">
          {critical > 0 ? (
            <span className="inline-flex items-center gap-1.5 text-red-400">
              <AlertTriangle className="w-3 h-3" />
              {critical} critical
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 text-zinc-600">
              <Sparkles className="w-3 h-3" />
              No critical incidents
            </span>
          )}
          {open > 0 && (
            <span className="inline-flex items-center gap-1.5 text-amber-400">
              <Inbox className="w-3 h-3" />
              {open} open
            </span>
          )}
        </div>
      </div>

      {/* 5 mini stats */}
      {MINIS.map((m) => {
        const value = summary[m.key]
        const tone = value === 0 ? 'text-zinc-700' : m.tone
        return (
          <div key={m.key} className="bg-zinc-900 p-6 flex flex-col justify-between" title={m.help}>
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">
              {m.label}
            </div>
            <div className={`text-3xl font-light font-mono mt-2 ${tone}`}>{value}</div>
            <div className="text-[9px] text-zinc-700 uppercase tracking-widest mt-3">
              {value === 0 ? 'none' : value === 1 ? 'incident' : 'incidents'}
            </div>
          </div>
        )
      })}
    </div>
  )
}
