import { useMemo, useState } from 'react'
import { Button } from '../../../ui'
import { fmtScore, scoreCellBg, scoreColor, statusBadge } from './helpers'
import type { ScorecardCell } from './types'

export function Scorecard({ cells }: { cells: ScorecardCell[] }) {
  const [selected, setSelected] = useState<ScorecardCell | null>(null)

  const { jurisdictions, industries, byKey } = useMemo(() => {
    const jMap = new Map<string, string>()
    const iSet = new Set<string>()
    const map = new Map<string, ScorecardCell>()
    for (const c of cells) {
      jMap.set(c.jurisdiction_id, c.jurisdiction_label || c.jurisdiction_id)
      if (c.industry) iSet.add(c.industry)
      map.set(`${c.jurisdiction_id}|${c.industry}`, c)
    }
    return {
      jurisdictions: [...jMap.entries()].sort((a, b) => a[1].localeCompare(b[1])),
      industries: [...iSet].sort(),
      byKey: map,
    }
  }, [cells])

  if (!cells.length) {
    return (
      <p className="text-sm text-zinc-500 border border-zinc-800 rounded-lg p-6 text-center">
        No scorecard yet. Trigger a run to populate it.
      </p>
    )
  }

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto border border-zinc-800 rounded-lg">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800">
              <th className="text-left px-3 py-2 text-[10px] uppercase tracking-wider text-zinc-500 font-medium sticky left-0 bg-zinc-950">
                Jurisdiction
              </th>
              {industries.map((i) => (
                <th key={i} className="px-2 py-2 text-[10px] uppercase tracking-wider text-zinc-500 font-medium">
                  {i}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {jurisdictions.map(([jid, label]) => (
              <tr key={jid} className="border-b border-zinc-900">
                <td className="px-3 py-1.5 text-zinc-300 whitespace-nowrap sticky left-0 bg-zinc-950">{label}</td>
                {industries.map((ind) => {
                  const cell = byKey.get(`${jid}|${ind}`)
                  return (
                    <td key={ind} className="px-1 py-1">
                      <button
                        onClick={() => cell && setSelected(cell)}
                        disabled={!cell}
                        className={`w-full rounded px-2 py-1 font-medium ${scoreCellBg(cell?.composite)} ${scoreColor(cell?.composite)} ${cell ? 'hover:ring-1 hover:ring-zinc-600' : 'cursor-default'}`}
                      >
                        {fmtScore(cell?.composite)}
                      </button>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected && (
        <div className="border border-zinc-700 rounded-lg p-4">
          <div className="flex items-start justify-between mb-3">
            <div>
              <p className="text-sm font-semibold text-zinc-200">
                {selected.jurisdiction_label} · {selected.industry}
              </p>
              <p className="text-[11px] text-zinc-500">measured {selected.measured_at?.slice(0, 10)}</p>
            </div>
            <div className="flex items-center gap-2">
              {statusBadge(selected.status)}
              <Button variant="ghost" size="sm" onClick={() => setSelected(null)}>Close</Button>
            </div>
          </div>
          <div className="grid grid-cols-5 gap-2 mb-3">
            {(['completeness', 'accuracy', 'authority', 'freshness', 'tagging'] as const).map((k) => (
              <div key={k} className="border border-zinc-800 rounded px-2 py-2">
                <p className="text-[10px] uppercase tracking-wider text-zinc-500">{k}</p>
                <p className={`text-lg font-bold ${scoreColor(selected.subscores[k])}`}>
                  {fmtScore(selected.subscores[k])}
                </p>
              </div>
            ))}
          </div>
          {selected.blocking?.length > 0 && (
            <ul className="space-y-1">
              {selected.blocking.map((b) => (
                <li key={b} className="text-xs text-red-300">• {b}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
