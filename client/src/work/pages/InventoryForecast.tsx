import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, BarChart3, Check, Link2, Loader2, RefreshCw, Save, Sparkles } from 'lucide-react'
import { Button, Input, useToast } from '../../components/ui'
import { listChannelLocations, type ChannelLocation } from '../api/channels'
import {
  createForecastRun,
  getForecastSettings,
  getLatestForecastRun,
  listPOSConnections,
  authorizeSquare,
  draftForecastAdjustments,
  putForecastSettings,
  type ForecastLine,
  type ForecastAIDraft,
  type ForecastOverride,
  type ForecastRun,
  type ForecastSettings,
  type POSConnection,
} from '../api/inventory'
import { useWorkBase } from '../routes/WorkSurfaceContext'
import POSConnectionPanel from '../components/inventory/POSConnectionPanel'
import InventoryWasteGuide from '../components/inventory/InventoryWasteGuide'
import { useMe } from '../../hooks/useMe'

const DEFAULT_SETTINGS: ForecastSettings = {
  location_id: null,
  horizon_days: 56,
  history_days: 90,
  default_lead_time_days: 7,
  default_safety_stock_days: 7,
  timezone: 'America/Los_Angeles',
  par_auto_apply: false,
  par_max_drift_pct: 0.5,
  configured: false,
}

export default function InventoryForecast() {
  const base = useWorkBase()
  const navigate = useNavigate()
  const { me } = useMe()
  const { toast } = useToast()
  const [locations, setLocations] = useState<ChannelLocation[]>([])
  const [locationId, setLocationId] = useState('')
  const [settings, setSettings] = useState<ForecastSettings>(DEFAULT_SETTINGS)
  const [run, setRun] = useState<ForecastRun | null>(null)
  const [connections, setConnections] = useState<POSConnection[]>([])
  const [managerContext, setManagerContext] = useState('')
  const [aiDraft, setAiDraft] = useState<ForecastAIDraft | null>(null)
  const [acceptedOverrides, setAcceptedOverrides] = useState<ForecastOverride[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [askingAI, setAskingAI] = useState(false)
  const [guideOpen, setGuideOpen] = useState(false)

  useEffect(() => {
    listChannelLocations().then(setLocations).catch(() => setLocations([]))
  }, [])

  useEffect(() => {
    let active = true
    setLoading(true)
    Promise.all([
      getForecastSettings(locationId || undefined),
      getLatestForecastRun(locationId || undefined),
      listPOSConnections(),
    ]).then(([nextSettings, latest, nextConnections]) => {
      if (!active) return
      setSettings(nextSettings)
      setRun(latest)
      setConnections(nextConnections.connections)
    }).catch(() => {
      if (active) toast('Failed to load forecast setup', 'error')
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [locationId, toast])

  function updateSetting<K extends keyof ForecastSettings>(key: K, value: ForecastSettings[K]) {
    setSettings((current) => ({ ...current, [key]: value }))
  }

  async function saveAndRun() {
    setSaving(true)
    try {
      await putForecastSettings({
        location_id: locationId || null,
        horizon_days: settings.horizon_days,
        history_days: settings.history_days,
        default_lead_time_days: settings.default_lead_time_days,
        default_safety_stock_days: settings.default_safety_stock_days,
        timezone: settings.timezone,
        par_auto_apply: settings.par_auto_apply,
        par_max_drift_pct: settings.par_max_drift_pct,
      })
      const next = await createForecastRun({ location_id: locationId || null, overrides: acceptedOverrides })
      setRun(next)
      toast('Forecast snapshot saved', 'success')
    } catch {
      toast('Could not save the forecast', 'error')
    } finally {
      setSaving(false)
    }
  }

  async function askAssistant() {
    if (!managerContext.trim()) return
    setAskingAI(true)
    try {
      const next = await draftForecastAdjustments({
        location_id: locationId || null,
        manager_context: managerContext.trim(),
      })
      setAiDraft(next)
    } catch {
      toast('Could not generate a scenario draft', 'error')
    } finally {
      setAskingAI(false)
    }
  }

  function acceptAdjustment(adjustment: ForecastOverride) {
    setAcceptedOverrides((current) => [
      ...current.filter((item) => item.week_start !== adjustment.week_start),
      { ...adjustment, source: 'ai_accepted' as const },
    ].sort((left, right) => left.week_start.localeCompare(right.week_start)))
  }

  async function connectSquare() {
    try {
      const result = await authorizeSquare()
      window.location.assign(result.oauth_url)
    } catch {
      toast('Square is not configured yet', 'error')
    }
  }

  if (loading) {
    return <div className="flex h-full items-center justify-center bg-w-bg"><Loader2 className="h-5 w-5 animate-spin text-w-dim" /></div>
  }

  return (
    <div className="h-full overflow-y-auto bg-w-bg text-w-text">
      <div className="mx-auto max-w-[1500px] space-y-4 p-3 sm:p-5">
        <header className="flex flex-col gap-3 border-b border-w-line pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <button type="button" onClick={() => navigate(`${base}/inventory`)} className="mb-3 inline-flex items-center gap-1.5 text-xs text-w-dim hover:text-w-text">
              <ArrowLeft size={13} /> Inventory
            </button>
            <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.2em] text-w-accent"><BarChart3 size={13} /> Operations / Forecast</div>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight">Demand forecast</h1>
            <p className="mt-1.5 max-w-2xl text-sm text-w-dim">Project demand from committed sales and turn it into an explainable replenishment recommendation. Nothing here approves an order.</p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => setGuideOpen(true)}>How predictive PARs work</Button>
            <select value={locationId} onChange={(event) => setLocationId(event.target.value)} className="rounded-lg border border-w-line bg-w-surface px-3 py-2 text-xs text-w-text outline-none focus:border-w-accent/50">
              <option value="">All locations</option>
              {locations.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}
            </select>
            <button type="button" onClick={() => window.location.reload()} className="inline-flex items-center gap-2 rounded-lg border border-w-line bg-w-surface px-3 py-2 text-xs text-w-dim hover:text-w-text"><RefreshCw size={13} /> Refresh</button>
          </div>
        </header>

        <section id="waste-par" className="scroll-mt-6 rounded-xl border border-w-line bg-w-surface p-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h2 className="text-sm font-medium">Forecast setup</h2>
              <p className="mt-1 text-xs text-w-dim">Use at least four non-zero sales days per item for a reorder recommendation. Sparse items stay review-only.</p>
            </div>
            <Button onClick={saveAndRun} disabled={saving}>
              {saving ? <Loader2 className="mr-1.5 inline h-3.5 w-3.5 animate-spin" /> : <Save className="mr-1.5 inline h-3.5 w-3.5" />}
              {saving ? 'Calculating…' : 'Save and calculate'}
            </Button>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <NumberField label="Forecast days" value={settings.horizon_days} min={14} max={90} onChange={(value) => updateSetting('horizon_days', value)} />
            <NumberField label="History days" value={settings.history_days} min={28} max={365} onChange={(value) => updateSetting('history_days', value)} />
            <NumberField label="Default lead time" value={settings.default_lead_time_days} min={0} max={180} onChange={(value) => updateSetting('default_lead_time_days', value)} />
            <NumberField label="Safety stock days" value={settings.default_safety_stock_days} min={0} max={180} onChange={(value) => updateSetting('default_safety_stock_days', value)} />
            <NumberField label="Maximum auto-par drift" value={settings.par_max_drift_pct} min={0.01} max={5} step={0.01} onChange={(value) => updateSetting('par_max_drift_pct', value)} />
          </div>
          <label className="mt-4 flex items-start gap-2 text-xs text-w-dim"><input type="checkbox" checked={settings.par_auto_apply} onChange={(event) => updateSetting('par_auto_apply', event.target.checked)} className="mt-0.5" /><span><strong className="font-medium text-w-text">Apply enrolled pars automatically</strong><br />Only auto-enrolled items with sufficient confidence and an in-bound drift are changed.</span></label>
           <p className="mt-3 text-[11px] text-w-faint">Historical sales come from committed imports and existing product-to-stock mappings. Suggestions below are review-only and never create an order.</p>
        </section>

        <section className="rounded-xl border border-w-line bg-w-surface p-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-w-accent" /><h2 className="text-sm font-medium">Scenario assistant</h2></div>
              <p className="mt-1 max-w-2xl text-xs text-w-dim">Describe a promotion, closure, holiday, or other operating change. Gemini may suggest weekly multipliers for your review; deterministic forecast math remains authoritative.</p>
            </div>
            <Button variant="secondary" onClick={askAssistant} disabled={askingAI || !managerContext.trim()}>
              {askingAI ? <Loader2 className="mr-1.5 inline h-3.5 w-3.5 animate-spin" /> : <Sparkles className="mr-1.5 inline h-3.5 w-3.5" />}
              {askingAI ? 'Drafting…' : 'Draft scenario'}
            </Button>
          </div>
          <textarea
            value={managerContext}
            onChange={(event) => setManagerContext(event.target.value)}
            maxLength={4000}
            rows={3}
            placeholder="Example: The dining room is closed for renovation during the first week of March."
            className="mt-3 w-full resize-y rounded-lg border border-w-line bg-w-surface2 px-3 py-2 text-sm text-w-text outline-none placeholder:text-w-faint focus:border-w-accent/50"
          />
          {aiDraft && <AIDraftPanel draft={aiDraft} accepted={acceptedOverrides} onAccept={acceptAdjustment} />}
          {acceptedOverrides.length > 0 && <p className="mt-3 text-xs text-w-accent">{acceptedOverrides.length} reviewed scenario adjustment{acceptedOverrides.length === 1 ? '' : 's'} will be included in the next snapshot.</p>}
        </section>

        <section className="rounded-xl border border-w-line bg-w-surface p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-2"><Link2 className="mt-0.5 h-4 w-4 text-w-accent" /><div><h2 className="text-sm font-medium">Sales connection</h2><p className="mt-1 text-xs text-w-dim">Square imports finalized orders into the same reviewed sales ledger as CSV and Gmail imports.</p></div></div>
          </div>
          {connections.length > 0 && <div className="mt-3 space-y-1.5">{connections.map((connection) => <div key={connection.id} className="rounded-lg bg-w-surface2 px-3 py-2 text-xs"><div className="flex items-center justify-between"><span className="font-medium capitalize text-w-text">{connection.provider}</span><span className={connection.status === 'connected' ? 'text-w-accent' : 'text-amber-300'}>{connection.status}{connection.last_sync_at ? ` · last sync ${connection.last_sync_at.slice(0, 10)}` : ''}</span></div><POSConnectionPanel connection={connection} locations={locations} onConnect={connectSquare} /></div>)}</div>}
          {connections.length === 0 && <POSConnectionPanel connection={null} locations={locations} onConnect={connectSquare} />}
        </section>

        {!run ? (
          <section className="rounded-xl border border-dashed border-w-line bg-w-surface px-4 py-10 text-center text-sm text-w-dim">No forecast snapshot yet. Save the setup to calculate one.</section>
        ) : (
          <ForecastResults run={run} />
        )}
        <InventoryWasteGuide open={guideOpen} initialStep={3} autoOpenKey={me?.profile?.company_id ?? me?.user?.id ?? 'current'} onClose={() => setGuideOpen(false)} />
      </div>
    </div>
  )
}

function AIDraftPanel({ draft, accepted, onAccept }: { draft: ForecastAIDraft; accepted: ForecastOverride[]; onAccept: (adjustment: ForecastOverride) => void }) {
  if (!draft.available) return <p className="mt-3 rounded-lg bg-w-surface2 px-3 py-2 text-xs text-w-dim">Scenario assistant unavailable. The deterministic forecast is still ready to run.</p>
  return <div className="mt-3 space-y-2">
    {draft.adjustments.length === 0 && <p className="rounded-lg bg-w-surface2 px-3 py-2 text-xs text-w-dim">No bounded adjustment was suggested from this context.</p>}
    {draft.adjustments.map((adjustment) => {
      const isAccepted = accepted.some((item) => item.week_start === adjustment.week_start)
      return <div key={adjustment.week_start} className="flex flex-col gap-2 rounded-lg bg-w-surface2 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="text-xs"><span className="font-medium text-w-text">Week of {adjustment.week_start}</span><span className="ml-2 text-w-accent">×{adjustment.demand_multiplier}</span><p className="mt-0.5 text-w-dim">{adjustment.reason} · {adjustment.confidence} confidence</p></div>
        <button type="button" onClick={() => onAccept(adjustment)} className="inline-flex items-center gap-1 self-start rounded-md border border-w-line px-2 py-1 text-[11px] text-w-dim hover:text-w-text sm:self-auto">
          {isAccepted ? <Check size={12} className="text-w-accent" /> : null}{isAccepted ? 'Accepted' : 'Accept'}
        </button>
      </div>
    })}
    {(draft.risks.length > 0 || draft.data_gaps.length > 0) && <p className="text-[11px] text-w-faint">Review risks and data gaps before accepting any suggestion.</p>}
  </div>
}

function NumberField({ label, value, min, max, step, onChange }: { label: string; value: number; min: number; max: number; step?: number; onChange: (value: number) => void }) {
  return <Input label={label} type="number" min={min} max={max} step={step} value={String(value)} onChange={(event) => onChange(Math.max(min, Math.min(max, Number(event.target.value) || min)))} className="border-w-line bg-w-surface2" />
}

function ForecastResults({ run }: { run: ForecastRun }) {
  const counts = run.lines.reduce((result, line) => {
    result[line.status] = (result[line.status] ?? 0) + 1
    return result
  }, {} as Record<string, number>)
  return (
    <section className="overflow-hidden rounded-xl border border-w-line bg-w-surface">
      <div className="flex flex-col gap-2 border-b border-w-line px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div><h2 className="text-sm font-medium">Latest snapshot</h2><p className="mt-1 text-xs text-w-dim">{run.forecast_start} to {run.forecast_end} · based on history through {run.history_start}</p></div>
        <div className="flex flex-wrap gap-2 text-[11px] text-w-dim"><span>{run.lines.length} items</span><span>{counts.ready ?? 0} ready</span><span>{counts.count_required ?? 0} count required</span><span>{counts.insufficient_history ?? 0} sparse</span></div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-xs">
          <thead className="bg-w-surface2 text-[10px] uppercase tracking-wider text-w-faint"><tr><th className="px-4 py-3">Item</th><th className="px-3 py-3">History</th><th className="px-3 py-3">Daily demand</th><th className="px-3 py-3">On hand</th><th className="px-3 py-3">Runout</th><th className="px-3 py-3">Order by</th><th className="px-4 py-3 text-right">Suggested</th></tr></thead>
          <tbody className="divide-y divide-w-line">
            {run.lines.map((line) => <ForecastRow key={line.item_id} line={line} />)}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function ForecastRow({ line }: { line: ForecastLine }) {
  const status = line.status === 'ready' ? 'Ready' : line.status === 'count_required' ? 'Count required' : line.status === 'no_demand' ? 'No demand' : 'Sparse history'
  const parBasis = line.par_basis === 'shelf_life' ? 'Shelf-life capped' : line.par_basis === 'structural_deficit' ? 'Structural deficit' : line.par_basis === 'demand' ? 'Demand based' : null
  return <tr className="text-w-dim"><td className="px-4 py-3"><div className="font-medium text-w-text">{line.name}</div><div className="text-[11px] text-w-faint">{status}{line.unit ? ` · ${line.unit}` : ''}</div>{line.recommended_par !== null && <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px]"><span className="text-w-dim">Par {formatNumber(line.recommended_par)}</span>{parBasis && <span className={`rounded-full px-1.5 py-0.5 ${line.shelf_life_capped ? 'bg-amber-500/15 text-amber-300' : 'bg-w-surface2 text-w-faint'}`}>{parBasis}</span>}</div>}</td><td className="px-3 py-3">{line.history_nonzero_days} days</td><td className="px-3 py-3">{formatNumber(line.average_daily_demand)}</td><td className="px-3 py-3">{line.current_quantity === null ? 'Unknown' : formatNumber(line.current_quantity)}</td><td className="px-3 py-3">{line.runout_date ?? '—'}</td><td className="px-3 py-3">{line.order_by_date ?? '—'}</td><td className="px-4 py-3 text-right font-medium text-w-text">{line.suggested_quantity === null ? '—' : formatNumber(line.suggested_quantity)}</td></tr>
}

function formatNumber(value: number | null) {
  if (value === null) return '—'
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value)
}
