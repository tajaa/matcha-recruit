import type { JurisdictionReq, RowContext } from './types'
import { LEVEL_ORDER, LEVEL_COLORS } from './constants'
import { getCategoryLabel } from './helpers'
import RequirementRow from './RequirementRow'

type PreemptionLookup = Record<string, { allows: boolean; notes: string | null }> | null

type Props = {
  filteredReqs: JurisdictionReq[]
  hierarchyGrouped: Record<string, Record<string, JurisdictionReq[]>>
  preemptionLookup: PreemptionLookup
  city: string
  state: string
  ctx: RowContext
}

export default function HierarchyView({ filteredReqs, hierarchyGrouped, preemptionLookup, city, state, ctx }: Props) {
  if (filteredReqs.length === 0) {
    return (
      <div className="border border-zinc-800 rounded-lg px-4 py-6 text-center">
        <p className="text-sm text-zinc-600">No requirements.</p>
      </div>
    )
  }

  return (
    <div className="border border-zinc-800 rounded-lg max-h-[55vh] overflow-y-auto">
      {Object.entries(hierarchyGrouped).map(([cat, levels], catIdx) => (
        <div key={cat}>
          {catIdx > 0 && <div className="border-t border-zinc-800/60" />}
          <div className="px-4 pt-3 pb-1 flex items-center gap-2">
            <p className="text-xs uppercase tracking-wide text-zinc-400 font-medium">{getCategoryLabel(cat)}</p>
            {/* Preemption badge */}
            {preemptionLookup?.[cat] && (
              <span
                className={`text-[9px] px-1.5 py-0.5 rounded font-medium ${
                  preemptionLookup[cat].allows
                    ? 'bg-emerald-500/15 text-emerald-400'
                    : 'bg-red-500/15 text-red-400'
                }`}
                title={preemptionLookup[cat].notes ?? undefined}
              >
                {preemptionLookup[cat].allows ? 'Local override OK' : 'State preempts'}
              </span>
            )}
          </div>
          {LEVEL_ORDER.map((level) => {
            const levelLabel = level === 'state' ? `state (${state})`
              : level === 'city' ? `city (${city})`
              : level
            if (!levels[level]?.length) {
              return (
                <div key={level} className="px-4 pt-2 pb-1.5">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wider font-medium ${LEVEL_COLORS[level] || 'text-zinc-400 bg-zinc-500/10'}`}>
                    {levelLabel}
                  </span>
                  <p className="text-[11px] text-zinc-600 mt-1 pl-1">No {level}-level rules</p>
                </div>
              )
            }
            return (
              <div key={level}>
                <div className="px-4 pt-2 pb-0.5">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wider font-medium ${LEVEL_COLORS[level] || 'text-zinc-400 bg-zinc-500/10'}`}>
                    {levelLabel}
                  </span>
                </div>
                {levels[level].map((req) => <RequirementRow key={req.id} req={req} ctx={ctx} />)}
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}
