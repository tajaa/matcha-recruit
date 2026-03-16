import { Badge } from '../ui'
import type { UpcomingLegislation } from '../../types/compliance'
import { CATEGORY_LABELS } from '../../types/compliance'

type Props = { legislation: UpcomingLegislation[]; loading: boolean }

const STATUS_STYLE: Record<string, string> = {
  proposed: 'bg-blue-900/20 text-blue-400 border-blue-800/40',
  passed: 'bg-amber-900/20 text-amber-400 border-amber-800/40',
  signed: 'bg-amber-900/20 text-amber-400 border-amber-800/40',
  effective_soon: 'bg-red-900/20 text-red-400 border-red-800/40',
  effective: 'bg-emerald-900/20 text-emerald-400 border-emerald-800/40',
  dismissed: 'bg-zinc-800 text-zinc-500 border-zinc-700',
}

export function ComplianceUpcomingTab({ legislation, loading }: Props) {
  if (loading) return <p className="text-sm text-zinc-500">Loading legislation...</p>

  if (legislation.length === 0) {
    return (
      <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
        <p className="text-sm text-zinc-600">No upcoming legislation detected for this location.</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {legislation.map((leg) => (
        <div key={leg.id} id={`legislation-${leg.id}`}
          className="border border-zinc-800 rounded-lg p-4 space-y-2 hover:border-zinc-700 transition-colors">
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <p className="text-sm font-medium text-zinc-200">{leg.title}</p>
                <span className={`text-[10px] px-1.5 py-0.5 rounded border ${STATUS_STYLE[leg.current_status] || 'bg-zinc-800 text-zinc-400 border-zinc-700'}`}>
                  {leg.current_status.replace(/_/g, ' ')}
                </span>
                {leg.category && (
                  <Badge variant="neutral">{CATEGORY_LABELS[leg.category] || leg.category}</Badge>
                )}
              </div>
              {leg.description && (
                <p className="text-xs text-zinc-400 mt-1.5 leading-relaxed">{leg.description}</p>
              )}
              {leg.impact_summary && (
                <div className="mt-2 px-3 py-2 bg-amber-900/10 border border-amber-800/30 rounded">
                  <p className="text-xs text-amber-300">{leg.impact_summary}</p>
                </div>
              )}
              <div className="flex items-center gap-3 mt-2">
                {leg.expected_effective_date && (
                  <span className="text-[11px] text-zinc-500">
                    Effective: {new Date(leg.expected_effective_date).toLocaleDateString()}
                  </span>
                )}
                {leg.confidence != null && (
                  <span className="text-[11px] font-mono text-zinc-600">{Math.round(leg.confidence * 100)}% confidence</span>
                )}
                {(leg.affected_employee_count ?? 0) > 0 && (
                  <span className="text-[11px] text-zinc-500">{leg.affected_employee_count} employees</span>
                )}
                {leg.source_url && (
                  <a href={leg.source_url} target="_blank" rel="noopener noreferrer"
                    className="text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors">
                    {leg.source_name || 'Source'} &rarr;
                  </a>
                )}
              </div>
            </div>
            {leg.days_until_effective != null && (
              <div className="text-right shrink-0">
                <span className={`text-xl font-mono font-semibold ${
                  leg.days_until_effective <= 30 ? 'text-red-400'
                  : leg.days_until_effective <= 90 ? 'text-amber-400'
                  : 'text-zinc-500'
                }`}>
                  {leg.days_until_effective <= 0 ? 'NOW' : leg.days_until_effective}
                </span>
                {leg.days_until_effective > 0 && (
                  <span className="block text-[10px] text-zinc-600">days</span>
                )}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
