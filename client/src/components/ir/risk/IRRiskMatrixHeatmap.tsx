import { useMemo } from 'react'
import type {
  IRRiskMatrix,
  IRRiskMatrixCell,
  IRIncidentType,
} from '../../../types/ir'

const TYPE_COLUMNS: { key: IRIncidentType; label: string }[] = [
  { key: 'safety', label: 'Safety' },
  { key: 'behavioral', label: 'Behavioral' },
  { key: 'property', label: 'Property' },
  { key: 'near_miss', label: 'Near Miss' },
  { key: 'other', label: 'Other' },
]

function cellTone(cell: IRRiskMatrixCell | undefined): { bg: string; text: string } {
  if (!cell || cell.count === 0) return { bg: '', text: 'text-zinc-700' }
  if (cell.flagged) return { bg: 'bg-red-500/20', text: 'text-red-300 font-medium' }
  if (cell.deviation_ratio >= 1.5) return { bg: 'bg-orange-500/15', text: 'text-orange-300' }
  if (cell.deviation_ratio >= 1.0) return { bg: 'bg-amber-500/10', text: 'text-amber-300' }
  return { bg: 'bg-emerald-500/5', text: 'text-zinc-200' }
}

export function IRRiskMatrixHeatmap({
  matrix,
  loading,
  error,
}: {
  matrix: IRRiskMatrix | null
  loading: boolean
  error: string | null
}) {
  const totals = useMemo(() => {
    if (!matrix) return null
    const byType: Record<string, number> = {}
    let grand = 0
    for (const r of matrix.rows) {
      for (const c of r.cells) {
        byType[c.incident_type] = (byType[c.incident_type] || 0) + c.count
        grand += c.count
      }
    }
    return { byType, grand }
  }, [matrix])

  return (
    <section>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">
          Risk Matrix · last {matrix?.period_days ?? '—'} days
        </h2>
        {matrix && (
          <span className="text-[10px] text-zinc-600 font-mono">
            {matrix.company_total} incidents · {matrix.location_count} location
            {matrix.location_count === 1 ? '' : 's'}
          </span>
        )}
      </div>
      <div className="bg-zinc-900 border border-white/10 rounded-2xl overflow-hidden">
        {loading ? (
          <div className="p-6 text-xs text-zinc-500 text-center animate-pulse">
            Loading matrix…
          </div>
        ) : error ? (
          <p className="p-4 text-sm text-red-400">{error}</p>
        ) : !matrix || matrix.rows.length === 0 ? (
          <p className="p-6 text-sm text-zinc-500 text-center">
            No incidents reported in this window.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-zinc-950/50 text-zinc-500 text-[10px] uppercase tracking-widest">
              <tr>
                <th className="text-left px-4 py-3 font-bold">Location</th>
                {TYPE_COLUMNS.map((c) => (
                  <th key={c.key} className="text-center px-3 py-3 font-bold">{c.label}</th>
                ))}
                <th className="text-right px-4 py-3 font-bold">Total</th>
              </tr>
            </thead>
            <tbody>
              {matrix.rows.map((row) => (
                <tr key={row.location_id ?? '__unassigned__'} className="border-t border-white/5">
                  <td className="px-4 py-3 text-zinc-200 text-[13px]">{row.location_name}</td>
                  {TYPE_COLUMNS.map((col) => {
                    const cell = row.cells.find((c) => c.incident_type === col.key)
                    const tone = cellTone(cell)
                    return (
                      <td key={col.key} className={`px-3 py-3 text-center ${tone.bg}`}>
                        {!cell || cell.count === 0 ? (
                          <span className="text-zinc-700">—</span>
                        ) : (
                          <span
                            className={`font-mono ${tone.text}`}
                            title={`${cell.count} incidents · ${cell.deviation_ratio.toFixed(1)}× baseline · severity ${cell.severity_score.toFixed(1)}`}
                          >
                            {cell.count}
                          </span>
                        )}
                      </td>
                    )
                  })}
                  <td className="px-4 py-3 text-right text-zinc-300 font-mono font-medium">
                    {row.total_incidents}
                  </td>
                </tr>
              ))}
              {totals && (
                <tr className="border-t border-white/10 bg-zinc-950/50">
                  <td className="px-4 py-3 text-[10px] text-zinc-500 uppercase tracking-widest font-bold">
                    Company total
                  </td>
                  {TYPE_COLUMNS.map((col) => (
                    <td key={col.key} className="px-3 py-3 text-center text-zinc-400 font-mono">
                      {totals.byType[col.key] || 0}
                    </td>
                  ))}
                  <td className="px-4 py-3 text-right text-zinc-200 font-mono font-medium">
                    {totals.grand}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
      <p className="text-[10px] text-zinc-600 mt-2 flex items-center gap-3">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 bg-red-500/20 border border-red-500/40" />
          Flagged ≥2× baseline
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 bg-orange-500/15 border border-orange-500/30" />
          Above baseline
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 bg-emerald-500/5 border border-emerald-500/20" />
          At/below baseline
        </span>
      </p>
    </section>
  )
}
