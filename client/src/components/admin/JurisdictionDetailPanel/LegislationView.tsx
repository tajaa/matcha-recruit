import type { JurisdictionDetail } from './types'
import { getCategoryLabel } from './helpers'

type Props = {
  legislation: JurisdictionDetail['legislation']
}

export default function LegislationView({ legislation }: Props) {
  if (legislation.length === 0) {
    return (
      <div className="border border-zinc-800 rounded-lg px-4 py-6 text-center">
        <p className="text-sm text-zinc-600">No legislation tracked.</p>
      </div>
    )
  }

  return (
    <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60 max-h-[55vh] overflow-y-auto">
      {legislation.map((leg) => (
        <div key={leg.id} className="px-4 py-2.5">
          <div className="flex items-start justify-between gap-2">
            <p className="text-sm text-zinc-200">{leg.title}</p>
            <span className={`text-[10px] shrink-0 px-1.5 py-0.5 rounded ${
              leg.current_status === 'effective' ? 'text-emerald-400 bg-emerald-500/10'
                : leg.current_status === 'effective_soon' ? 'text-red-400 bg-red-500/10'
                : leg.current_status === 'signed' ? 'text-amber-400 bg-amber-500/10'
                : 'text-zinc-400 bg-zinc-500/10'
            }`}>
              {leg.current_status?.replace(/_/g, ' ')}
            </span>
          </div>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-[11px] text-zinc-500">{getCategoryLabel(leg.category)}</span>
            {leg.expected_effective_date && <span className="text-[11px] text-zinc-600">eff. {leg.expected_effective_date}</span>}
            {leg.source_url && (
              <a href={leg.source_url} target="_blank" rel="noopener noreferrer" className="text-[11px] text-zinc-600 hover:text-zinc-400 underline">source</a>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
