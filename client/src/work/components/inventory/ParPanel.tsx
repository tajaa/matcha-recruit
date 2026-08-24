import { useEffect, useState } from 'react'
import { Button, useToast } from '../../../components/ui'
import {
  applyForecastPar, enrollAutoPar, getLatestForecastRun, getParHistory,
  type ForecastLine, type InventoryItem, type ParHistoryEntry,
} from '../../api/inventory'
import { InventoryHelpButton } from './InventoryHelp'

export default function ParPanel({ item, forecastEnabled, onUpdated, onGuide }: {
  item: InventoryItem
  forecastEnabled: boolean
  onUpdated: () => void
  onGuide?: () => void
}) {
  const { toast } = useToast()
  const [history, setHistory] = useState<ParHistoryEntry[]>([])
  const [line, setLine] = useState<ForecastLine | null>(null)
  const [saving, setSaving] = useState(false)

  const load = () => {
    void getParHistory(item.id).then(({ history: next }) => setHistory(next)).catch(() => setHistory([]))
    if (!forecastEnabled) {
      setLine(null)
      return
    }
    void getLatestForecastRun().then((run) => {
      setLine(run?.lines.find((candidate) => candidate.item_id === item.id) ?? null)
    }).catch(() => setLine(null))
  }

  useEffect(load, [item.id, forecastEnabled]) // eslint-disable-line react-hooks/exhaustive-deps

  async function toggleEnrollment() {
    setSaving(true)
    try {
      await enrollAutoPar([item.id], item.par_source !== 'auto')
      toast(item.par_source === 'auto' ? 'Automatic par disabled' : 'Automatic par enabled', 'success')
      onUpdated()
    } catch {
      toast('Could not update par enrollment', 'error')
    } finally {
      setSaving(false)
    }
  }

  async function applyRecommendation() {
    if (!line || line.recommended_par == null || !line.item_id) return
    setSaving(true)
    try {
      const result = await applyForecastPar(line.run_id, { item_ids: [line.item_id] })
      if (result.applied) toast('Par recommendation applied', 'success')
      else toast('Par recommendation was not applied', 'error')
      load()
      onUpdated()
    } catch {
      toast('Could not apply par recommendation', 'error')
    } finally {
      setSaving(false)
    }
  }

  const drift = line?.current_par && line.recommended_par != null
    ? Math.abs(line.recommended_par - line.current_par) / line.current_par : null
  const basis = line?.par_basis === 'shelf_life' ? 'Shelf-life capped'
    : line?.par_basis === 'structural_deficit' ? 'Structural deficit'
      : line?.par_basis === 'demand' ? 'Demand based' : 'No recommendation'

  return <section className="rounded-xl border border-w-line bg-w-surface p-4">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 className="text-sm font-medium text-w-text">Predictive par</h2><p className="mt-1 text-xs text-w-dim">Forecast recommendations are reviewable; auto mode stays within its drift guardrail.</p></div>
      <div className="flex gap-2">{onGuide && <InventoryHelpButton onClick={onGuide} />}<Button size="sm" variant={item.par_source === 'auto' ? 'secondary' : 'ghost'} disabled={saving} onClick={() => void toggleEnrollment()}>{item.par_source === 'auto' ? 'Auto-managed' : 'Enable auto par'}</Button></div>
    </div>
    <div className="mt-3 grid gap-2 sm:grid-cols-4">
      <Stat label="Current par" value={item.low_stock_threshold == null ? 'Not set' : String(item.low_stock_threshold)} />
      <Stat label="Recommended" value={line?.recommended_par == null ? '—' : String(line.recommended_par)} />
      <Stat label="Basis" value={basis} />
      <Stat label="Drift" value={drift == null ? '—' : `${(drift * 100).toFixed(0)}%`} />
    </div>
    {line?.recommended_par != null && <div className="mt-3 flex items-center gap-2"><Button size="sm" disabled={saving} onClick={() => void applyRecommendation()}>Apply recommendation</Button>{line.shelf_life_capped && <span className="text-xs text-amber-300">Shelf-life cap active</span>}</div>}
    <div className="mt-4 border-t border-w-line pt-3"><h3 className="text-xs font-medium uppercase tracking-wide text-w-faint">History</h3>{history.length ? <div className="mt-2 space-y-1 text-xs text-w-dim">{history.slice(0, 5).map((entry) => <div key={entry.id} className="flex justify-between gap-3"><span>{entry.previous_par ?? '—'} → {entry.new_par} · {entry.par_basis ?? 'manual'}</span><span>{new Date(entry.changed_at).toLocaleDateString()}</span></div>)}</div> : <p className="mt-2 text-xs text-w-dim">No applied par changes yet.</p>}</div>
  </section>
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div className="rounded-lg bg-w-surface2 px-3 py-2"><p className="text-[10px] uppercase tracking-[0.14em] text-w-faint">{label}</p><p className="mt-1 text-sm font-medium text-w-text">{value}</p></div>
}
