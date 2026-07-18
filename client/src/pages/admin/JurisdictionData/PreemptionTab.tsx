import { useMemo, useState } from 'react'
import type { PreemptionRule } from '../../../components/admin/jurisdiction/types'
import { getShortLabel } from './helpers'

interface PreemptionTabProps {
  requiredCats: string[]
  preemptionRules: PreemptionRule[]
}

export default function PreemptionTab({ requiredCats, preemptionRules }: PreemptionTabProps) {
  const [hoveredCell, setHoveredCell] = useState<{ state: string; cat: string } | null>(null)

  const preemptionMatrix = useMemo(() => {
    const matrix: Record<string, Record<string, { allows: boolean; notes: string | null }>> = {}
    const stateSet = new Set<string>()
    for (const r of preemptionRules ?? []) {
      stateSet.add(r.state)
      if (!matrix[r.state]) matrix[r.state] = {}
      matrix[r.state][r.category] = { allows: r.allows_local_override, notes: r.notes }
    }
    return { states: [...stateSet].sort(), matrix }
  }, [preemptionRules])

  return (
    <div>
      {preemptionMatrix.states.length === 0 ? (
        <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
          <p className="text-sm text-zinc-600">No preemption rules in the database yet.</p>
        </div>
      ) : (
        <div className="border border-zinc-800 rounded-lg p-4">
          <p className="text-[11px] text-zinc-500 mb-3">
            Green = allows local override · Red = state preempts local law · Hover for notes
          </p>
          <div className="overflow-x-auto">
            <table className="text-xs">
              <thead>
                <tr>
                  <th className="py-1.5 px-2 text-left text-[10px] text-zinc-500 uppercase tracking-wide">State</th>
                  {requiredCats.map((c) => (
                    <th key={c} className="py-1.5 px-1.5 text-center text-[10px] text-zinc-500 uppercase tracking-wide whitespace-nowrap">
                      {getShortLabel(c)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preemptionMatrix.states.map((state) => (
                  <tr key={state} className="hover:bg-zinc-800/30">
                    <td className="py-1 px-2 font-mono font-bold text-zinc-200">{state}</td>
                    {requiredCats.map((cat) => {
                      const cell = preemptionMatrix.matrix[state]?.[cat]
                      if (!cell) return <td key={cat} className="py-1 px-1.5 text-center text-zinc-700">—</td>
                      const isHovered = hoveredCell?.state === state && hoveredCell?.cat === cat
                      return (
                        <td key={cat} className="py-1 px-1.5 text-center relative"
                          onMouseEnter={() => setHoveredCell({ state, cat })}
                          onMouseLeave={() => setHoveredCell(null)}>
                          <span className={`inline-flex items-center justify-center w-6 h-6 rounded text-[11px] font-bold ${
                            cell.allows ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400'
                          }`}>
                            {cell.allows ? '✓' : '✗'}
                          </span>
                          {isHovered && cell.notes && (
                            <div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2.5 py-1.5 rounded-lg text-[10px] max-w-[220px] bg-zinc-800 text-zinc-200 shadow-lg whitespace-normal">
                              {cell.notes}
                            </div>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
