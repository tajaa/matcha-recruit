import { useState } from 'react'
import { Loader2, MessageSquarePlus } from 'lucide-react'
import {
  patchDataset,
  type AnalysisSession, type AnalysisDataset, type Extraction,
} from '../../../api/analysis-pilot/analysisPilot'
import { slugify, type FocusChip } from './shared'

// Fallback only — the authoritative role vocabulary is served by the backend
// on the session payload (`canonical_roles`), so new analyzer packs' roles
// appear here without a frontend change.
const ROLE_OPTIONS_FALLBACK = [
  'revenue', 'cogs', 'gross_profit', 'operating_income', 'net_income',
  'interest_expense', 'total_assets', 'current_assets', 'cash', 'receivables',
  'inventory_value', 'current_liabilities', 'total_liabilities', 'total_equity',
  'premium', 'exposure', 'losses_incurred', 'losses_paid', 'reserves',
  'claim_count', 'open_claims', 'units_on_hand', 'units_sold', 'reorder_point',
  'lead_time', 'return', 'price', 'score',
]

// --------------------------------------------------------------------------- //
// Mapping/review modal — confirm roles + config (+ document figures).
// --------------------------------------------------------------------------- //

export function MappingModal({ session, dataset, onClose, onSaved, onFocus }: {
  session: AnalysisSession; dataset: AnalysisDataset; onClose: () => void; onSaved: () => void
  onFocus?: (chip: FocusChip) => void
}) {
  const roleOptions = ['', ...(session.canonical_roles ?? ROLE_OPTIONS_FALLBACK)]
  const [roles, setRoles] = useState<Record<string, string>>(() => ({ ...dataset.normalized.roles }))
  const [ppy, setPpy] = useState<string>(() => String((dataset.config?.periods_per_year as number) ?? ''))
  const [orientation, setOrientation] = useState<'' | 'columns' | 'rows'>('')
  const [busy, setBusy] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [extraction, setExtraction] = useState<Extraction | null>(dataset.extraction)
  const columns = dataset.normalized.columns
  const isTabular = dataset.source_kind !== 'pdf'

  const setFigure = (row: number, col: number, v: string) => {
    setExtraction((ex) => {
      if (!ex) return ex
      const items = ex.line_items.map((it, i) =>
        i === row ? { ...it, values: it.values.map((vv, j) => (j === col ? (v === '' ? null : Number(v)) : vv)) } : it)
      return { ...ex, line_items: items }
    })
  }

  const save = async () => {
    setBusy(true)
    setSaveError(null)
    try {
      await patchDataset(session.id, dataset.id, {
        mapping: roles,
        periods_per_year: ppy ? Number(ppy) : undefined,
        extraction: dataset.source_kind === 'pdf' && extraction ? extraction : undefined,
        orientation: isTabular && orientation ? orientation : undefined,
      })
      onSaved()
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Could not save.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-950 p-5"
        onClick={(e) => e.stopPropagation()}>
        <h3 className="text-base font-semibold text-zinc-100 mb-1">Review — {dataset.filename}</h3>
        <p className="text-xs text-zinc-500 mb-4">
          Map each series to what it represents so the right metrics compute. Numbers are computed
          from these values — nothing is invented.
        </p>

        {dataset.source_kind === 'pdf' && extraction && extraction.line_items.length > 0 && (
          <div className="mb-4">
            <div className="text-xs font-medium text-zinc-300 mb-1">Extracted figures — verify before analyzing</div>
            <div className="overflow-x-auto rounded-lg border border-zinc-800">
              <table className="text-xs">
                <thead>
                  <tr className="bg-zinc-900/60">
                    <th className="px-2 py-1.5 text-left text-[10px] uppercase text-zinc-500">Line item</th>
                    {extraction.periods.map((p, i) => (
                      <th key={i} className="px-2 py-1.5 text-left text-[10px] uppercase text-zinc-500">{p}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {extraction.line_items.map((it, r) => (
                    <tr key={r} className="border-t border-zinc-800/60">
                      <td className="px-2 py-1 text-zinc-300 whitespace-nowrap">
                        {it.label}{it.page ? <span className="text-zinc-600"> · p.{it.page}</span> : null}
                        {onFocus && (
                          <button title="Discuss this figure in chat"
                            onClick={() => onFocus({ cid: `figure:${dataset.id}:${slugify(it.label)}`, label: `${dataset.filename}: ${it.label}` })}
                            className="ml-1.5 align-middle text-zinc-600 hover:text-emerald-400">
                            <MessageSquarePlus className="h-3 w-3" />
                          </button>
                        )}
                      </td>
                      {extraction.periods.map((_p, c) => (
                        <td key={c} className="px-1 py-1">
                          <input value={it.values[c] ?? ''} onChange={(e) => setFigure(r, c, e.target.value)}
                            className="w-20 rounded bg-zinc-900 border border-zinc-700 px-1.5 py-0.5 text-xs text-zinc-200" />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <div className="text-xs font-medium text-zinc-300 mb-1">Series roles</div>
        <div className="grid grid-cols-2 gap-2 mb-4">
          {columns.map((col) => (
            <div key={col} className="flex items-center gap-2">
              <span className="text-xs text-zinc-400 truncate flex-1" title={col}>{col}</span>
              <select value={roles[col] ?? ''} onChange={(e) => setRoles((r) => ({ ...r, [col]: e.target.value }))}
                className="rounded bg-zinc-900 border border-zinc-700 px-1.5 py-1 text-xs text-zinc-200 w-40">
                {roleOptions.map((o) => <option key={o} value={o}>{o || '(unmapped)'}</option>)}
              </select>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 mb-5">
          <div className="flex items-center gap-2">
            <label className="text-xs text-zinc-400">Periods per year (for annualized vol)</label>
            <input value={ppy} onChange={(e) => setPpy(e.target.value.replace(/[^0-9]/g, ''))}
              placeholder="e.g. 252, 12" className="w-24 rounded bg-zinc-900 border border-zinc-700 px-2 py-1 text-xs text-zinc-200" />
          </div>
          {isTabular && (
            <div className="flex items-center gap-2">
              <label className="text-xs text-zinc-400" title="If the table was read the wrong way around, force how series are taken. Re-parses the original file.">
                Layout
              </label>
              <select value={orientation} onChange={(e) => setOrientation(e.target.value as '' | 'columns' | 'rows')}
                className="rounded bg-zinc-900 border border-zinc-700 px-1.5 py-1 text-xs text-zinc-200">
                <option value="">Auto-detected</option>
                <option value="columns">Columns are series</option>
                <option value="rows">Rows are series (line-items)</option>
              </select>
            </div>
          )}
        </div>

        {saveError && <div className="text-xs text-amber-400 mb-3">⚠ {saveError}</div>}

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-2 text-sm text-zinc-400 hover:text-zinc-200">Cancel</button>
          <button onClick={() => void save()} disabled={busy}
            className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-sm font-medium inline-flex items-center gap-2">
            {busy && <Loader2 className="h-4 w-4 animate-spin" />} Confirm & analyze
          </button>
        </div>
      </div>
    </div>
  )
}
