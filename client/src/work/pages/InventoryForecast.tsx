import { useEffect, useState } from 'react'
import { ArrowRight, BarChart3, Check, CircleAlert, Loader2, MapPin, RefreshCw, Save, Sparkles, Truck } from 'lucide-react'
import { Button, Input, useToast } from '../../components/ui'
import { listChannelLocations, type ChannelLocation } from '../api/channels'
import {
  createForecastRun,
  createOrder,
  applyForecastPar,
  getForecastSettings,
  getForecastInsight,
  getInventoryNetworkPlan,
  previewForecastPar,
  getLatestForecastRun,
  draftForecastAdjustments,
  putForecastSettings,
  type ForecastAIDraft,
  type ForecastOverride,
  type ForecastRun,
  type ForecastSettings,
  type ForecastPlanLine,
  type ForecastParPreview,
  type InventoryInsight,
} from '../api/inventory'
import type { InventoryNetworkPlan as InventoryNetworkPlanType } from '../types'
import InventoryWasteGuide from '../components/inventory/InventoryWasteGuide'
import InventoryNavigation from '../components/inventory/InventoryNavigation'
import { useMe } from '../../hooks/useMe'
import { useNavigate } from 'react-router-dom'
import { useWorkBase } from '../routes/WorkSurfaceContext'

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
  const { me } = useMe()
  const navigate = useNavigate()
  const base = useWorkBase()
  const { toast } = useToast()
  const [locations, setLocations] = useState<ChannelLocation[]>([])
  const [locationId, setLocationId] = useState('')
  const [settings, setSettings] = useState<ForecastSettings>(DEFAULT_SETTINGS)
  const [run, setRun] = useState<ForecastRun | null>(null)
  const [networkPlan, setNetworkPlan] = useState<InventoryNetworkPlanType | null>(null)
  const [networkError, setNetworkError] = useState(false)
  const [insight, setInsight] = useState<InventoryInsight | null>(null)
  const [parPreview, setParPreview] = useState<ForecastParPreview | null>(null)
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
    setNetworkPlan(null)
    setNetworkError(false)
    Promise.all([getForecastSettings(locationId || undefined), getLatestForecastRun(locationId || undefined)]).then(async ([nextSettings, latest]) => {
      if (!active) return
      setSettings(nextSettings)
      const stale = !latest || Date.now() - new Date(latest.created_at).getTime() > 12 * 60 * 60 * 1000
      const nextRun = stale ? await createForecastRun({ location_id: locationId || null }) : latest
      if (!active) return
      let nextNetworkPlan: InventoryNetworkPlanType | null = null
      let nextNetworkError = false
      if (!locationId) {
        try { nextNetworkPlan = await getInventoryNetworkPlan(nextRun.id) }
        catch { nextNetworkError = true }
      }
      if (!active) return
      setRun(nextRun)
      setNetworkPlan(nextNetworkPlan)
      setNetworkError(nextNetworkError)
      void getForecastInsight(nextRun.id).then(setInsight).catch(() => setInsight(null))
      void previewForecastPar(nextRun.id).then(setParPreview).catch(() => setParPreview(null))
    }).catch(() => { if (active) toast('Failed to load reorder plan', 'error') }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [locationId, toast])

  function updateSetting<K extends keyof ForecastSettings>(key: K, value: ForecastSettings[K]) {
    setSettings((current) => ({ ...current, [key]: value }))
  }

  async function saveSettings() {
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
      toast('Forecast settings saved', 'success')
    } catch {
      toast('Could not save the forecast', 'error')
    } finally {
      setSaving(false)
    }
  }

  async function recalculate() {
    setSaving(true)
    try {
      const nextRun = await createForecastRun({ location_id: locationId || null, overrides: acceptedOverrides })
      let nextNetworkPlan: InventoryNetworkPlanType | null = null
      let nextNetworkError = false
      if (!locationId) {
        try { nextNetworkPlan = await getInventoryNetworkPlan(nextRun.id) }
        catch { nextNetworkError = true }
      }
      setRun(nextRun)
      setNetworkPlan(nextNetworkPlan)
      setNetworkError(nextNetworkError)
      void getForecastInsight(nextRun.id).then(setInsight).catch(() => setInsight(null))
      void previewForecastPar(nextRun.id).then(setParPreview).catch(() => setParPreview(null))
      toast(nextNetworkError ? 'Reorder plan refreshed, but network balancing is unavailable' : 'Reorder plan refreshed', nextNetworkError ? 'error' : 'success')
    }
    catch { toast('Could not refresh the reorder plan', 'error') }
    finally { setSaving(false) }
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


  if (loading) {
    return <div className="flex h-full items-center justify-center bg-w-bg"><Loader2 className="h-5 w-5 animate-spin text-w-dim" /></div>
  }

  return (
    <div className="h-full overflow-y-auto bg-w-bg text-w-text">
      <div className="mx-auto max-w-[1500px] space-y-4 p-3 sm:p-4">
        <header className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.2em] text-w-accent"><BarChart3 size={13} /> Operations / Inventory</div>
            <h1 className="text-2xl font-semibold tracking-tight text-w-text sm:text-3xl">Inventory intelligence</h1>
            <p className="mt-1.5 max-w-2xl text-sm text-w-dim">Connect sales and stock across locations to transfer surplus before placing an urgent order, then right-size replenishment with explainable forecasts.</p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => setGuideOpen(true)}>How forecasts work</Button>
            <select value={locationId} onChange={(event) => setLocationId(event.target.value)} className="rounded-lg border border-w-line bg-w-surface px-3 py-2 text-xs text-w-text outline-none focus:border-w-accent/50">
              <option value="">All locations</option>
              {locations.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}
            </select>
            <button type="button" onClick={() => void recalculate()} disabled={saving} className="inline-flex items-center gap-2 rounded-lg border border-w-line bg-w-surface px-3 py-2 text-xs text-w-dim hover:text-w-text disabled:opacity-50"><RefreshCw size={13} /> {saving ? 'Calculating…' : 'Recalculate'}</button>
          </div>
        </header>

        <InventoryNavigation />

        {run && <>
          {!locationId && networkError && <section className="rounded-xl border border-amber-400/25 bg-amber-400/10 px-4 py-3 text-sm text-amber-200"><p className="font-medium">Cross-location balancing is unavailable</p><p className="mt-1 text-xs text-amber-100/70">Review physical stock at other locations before placing orders from this plan.</p></section>}
          {!locationId && networkPlan && <InventoryNetworkPlan plan={networkPlan} onAudit={() => navigate(`${base}/inventory/audit`)} />}
          <ReorderPlan run={run} networkPlan={!locationId ? networkPlan : null} onOrder={async (line) => { try { await createOrder({ item_id: line.item_id, quantity: line.suggested_quantity ?? undefined }); toast(`${line.name} added to the order queue`, 'success') } catch { toast('Could not stage that order', 'error') } }} onAudit={() => navigate(`${base}/inventory/audit`)} />
          {parPreview && <ParPreview preview={parPreview} onApply={async () => { try { await applyForecastPar(run.id); await recalculate(); toast('Eligible PARs applied for review', 'success') } catch { toast('Could not apply eligible PARs', 'error') } }} />}
          {insight && <section className="rounded-xl border border-w-accent/20 bg-w-surface p-4"><p className="text-[10px] font-medium uppercase tracking-[0.16em] text-w-accent">Luna’s read on the plan</p><h2 className="mt-1 font-medium text-w-text">{insight.headline}</h2><p className="mt-1 text-sm text-w-dim">{insight.detail}</p></section>}
        </>}

        <details id="waste-par" className="scroll-mt-6 rounded-xl border border-w-line bg-w-surface"><summary className="cursor-pointer px-4 py-3 text-sm font-medium text-w-text">Adjust the model <span className="ml-2 text-xs font-normal text-w-dim">{settings.configured ? 'your settings' : 'using defaults'} · {settings.horizon_days}d horizon · {settings.history_days}d history · {settings.default_lead_time_days}d lead</span></summary><section className="border-t border-w-line p-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h2 className="text-sm font-medium">Forecast setup</h2>
              <p className="mt-1 text-xs text-w-dim">Use at least four non-zero sales days per item for a reorder recommendation. Sparse items stay review-only.</p>
            </div>
            <Button onClick={saveSettings} disabled={saving}>
              {saving ? <Loader2 className="mr-1.5 inline h-3.5 w-3.5 animate-spin" /> : <Save className="mr-1.5 inline h-3.5 w-3.5" />}
              {saving ? 'Saving…' : 'Save settings'}
            </Button>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <NumberField label="Forecast days" value={settings.horizon_days} min={14} max={90} onChange={(value) => updateSetting('horizon_days', value)} />
            <NumberField label="History days" value={settings.history_days} min={28} max={365} onChange={(value) => updateSetting('history_days', value)} />
            <NumberField label="Default lead time" value={settings.default_lead_time_days} min={0} max={180} onChange={(value) => updateSetting('default_lead_time_days', value)} />
            <NumberField label="Safety stock days" value={settings.default_safety_stock_days} min={0} max={180} onChange={(value) => updateSetting('default_safety_stock_days', value)} />
            <NumberField label="Maximum auto-par drift" value={settings.par_max_drift_pct} min={0.01} max={5} step={0.01} onChange={(value) => updateSetting('par_max_drift_pct', value)} />
          </div>
           <p className="mt-3 text-[11px] text-w-faint">Historical sales come from committed imports and existing product-to-stock mappings. Suggestions below are review-only; staging an order still requires a manager decision in the order queue.</p>
        </section></details>

        <details className="rounded-xl border border-w-line bg-w-surface"><summary className="cursor-pointer px-4 py-3 text-sm font-medium text-w-text">Plan for an event</summary><section className="border-t border-w-line p-4">
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
        </section></details>

        <InventoryWasteGuide open={guideOpen} initialStep={4} autoOpenKey={me?.profile?.company_id ?? me?.user?.id ?? 'current'} onClose={() => setGuideOpen(false)} />
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

function InventoryNetworkPlan({ plan, onAudit }: { plan: InventoryNetworkPlanType; onAudit: () => void }) {
  const summary = plan.summary
  return (
    <section className="overflow-hidden rounded-xl border border-w-accent/25 bg-w-surface">
      <div className="flex flex-col gap-3 border-b border-w-line px-4 py-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.16em] text-w-accent"><Truck size={13} /> Network balancing</div>
          <h2 className="mt-1 text-base font-medium text-w-text">Move available stock before placing an urgent order</h2>
          <p className="mt-1 max-w-3xl text-xs text-w-dim">A donor is used only when it remains above its own lead-time and safety-stock target. Recommendations are read-only until a manager confirms the physical move.</p>
        </div>
        <div className="grid grid-cols-2 gap-2 text-center sm:grid-cols-4">
          <NetworkMetric value={summary.transfer_count} label="moves" />
          <NetworkMetric value={summary.shortages_fully_covered} label="shortages covered" />
          <NetworkMetric value={summary.remaining_reorder_count} label="still to order" />
          <NetworkMetric value={summary.inventory_value_moved === null ? '—' : formatMoney(summary.inventory_value_moved)} label="stock rebalanced" />
        </div>
      </div>

      {summary.location_count < 2 ? (
        <p className="px-4 py-5 text-sm text-w-dim">Add inventory at a second active location to compare stock across the business.</p>
      ) : plan.transfers.length === 0 ? (
        <div className="px-4 py-5 text-sm text-w-dim">
          <p>No safe transfer opportunities were found today.</p>
          <p className="mt-1 text-xs text-w-faint">Items must share the same name and unit at multiple locations, with trustworthy counts and at least four non-zero sales days.</p>
        </div>
      ) : (
        <div className="divide-y divide-w-line">
          {plan.transfers.map((transfer, index) => (
            <div key={`${transfer.from_item_id}:${transfer.to_item_id}:${index}`} className="px-4 py-4">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium text-w-text">{transfer.item_name}</p>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] ${transfer.coverage === 'full' ? 'bg-emerald-400/15 text-emerald-300' : 'bg-amber-400/15 text-amber-300'}`}>{transfer.coverage === 'full' ? 'Covers shortage' : 'Partial coverage'}</span>
                    <span className="text-[10px] text-w-faint">{transfer.confidence} confidence</span>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-w-dim">
                    <span className="inline-flex items-center gap-1"><MapPin size={12} />{transfer.from_location_name}</span>
                    <ArrowRight size={13} className="text-w-faint" />
                    <span className="inline-flex items-center gap-1"><MapPin size={12} />{transfer.to_location_name}</span>
                  </div>
                  <p className="mt-2 text-xs text-w-dim">{transfer.rationale}</p>
                </div>
                <div className="shrink-0 text-left lg:text-right">
                  <p className="text-sm font-medium text-w-text">Move {formatNumber(transfer.quantity)}{transfer.unit ? ` ${transfer.unit}` : ''}</p>
                  <p className="mt-1 text-[11px] text-w-dim">Donor after move: {formatNumber(transfer.from_post_transfer_quantity)} · Recipient after move: {formatNumber(transfer.to_post_transfer_quantity)}</p>
                  <p className="mt-0.5 text-[11px] text-w-faint">{transfer.days_of_cover_added === null ? 'Coverage days unavailable' : `${formatNumber(transfer.days_of_cover_added)} demand days added`}{transfer.inventory_value === null ? '' : ` · ${formatMoney(transfer.inventory_value)} in stock`}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {(plan.remaining_shortages.length > 0 || plan.attention.length > 0) && (
        <div className="grid gap-3 border-t border-w-line bg-w-surface2 p-4 lg:grid-cols-2">
          {plan.remaining_shortages.length > 0 && <div><p className="text-[10px] font-medium uppercase tracking-[0.14em] text-w-dim">Still needs ordering</p><div className="mt-2 space-y-1.5">{plan.remaining_shortages.slice(0, 5).map((line) => <div key={line.item_id} className="flex items-center justify-between gap-3 text-xs"><span className="truncate text-w-text">{line.item_name} · {line.location_name}</span><span className="shrink-0 text-w-dim">Order {formatNumber(line.suggested_order_quantity)}{line.unit ? ` ${line.unit}` : ''}</span></div>)}</div>{plan.remaining_shortages.length > 5 && <p className="mt-2 text-[11px] text-w-faint">+{plan.remaining_shortages.length - 5} more in the reorder plan below</p>}</div>}
          {plan.attention.length > 0 && <div><div className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-[0.14em] text-amber-300"><CircleAlert size={12} /> Data needs attention</div><p className="mt-2 text-xs text-w-dim">{plan.attention.length} location-item record{plan.attention.length === 1 ? '' : 's'} need a physical count or more sales history before they can safely donate stock.</p><button type="button" onClick={onAudit} className="mt-2 text-xs font-medium text-w-accent hover:underline">Open stock audit</button></div>}
        </div>
      )}
    </section>
  )
}

function NetworkMetric({ value, label }: { value: number | string; label: string }) {
  return <div className="min-w-20 rounded-lg bg-w-surface2 px-2.5 py-2"><p className="text-sm font-semibold text-w-text">{value}</p><p className="mt-0.5 text-[9px] uppercase tracking-wide text-w-faint">{label}</p></div>
}

function ReorderPlan({ run, networkPlan, onOrder, onAudit }: { run: ForecastRun; networkPlan: InventoryNetworkPlanType | null; onOrder: (line: ForecastPlanLine) => Promise<void>; onAudit: () => void }) {
  const plan = run.plan
  const [orderingId, setOrderingId] = useState<string | null>(null)
  async function handleOrder(line: ForecastPlanLine) {
    setOrderingId(line.item_id)
    try { await onOrder(line) } finally { setOrderingId(null) }
  }
  return (
    <section className="overflow-hidden rounded-xl border border-w-line bg-w-surface">
      <div className="flex flex-col gap-2 border-b border-w-line px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div><h2 className="text-sm font-medium">Reorder plan</h2><p className="mt-1 text-xs text-w-dim">As of {new Date(run.created_at).toLocaleString()} · based on committed sales through {run.history_start}</p></div>
        <div className="flex flex-wrap gap-2 text-[11px] text-w-dim"><span>{plan.lines.length} items need ordering</span>{plan.total_order_value !== null && <span>{formatMoney(plan.total_order_value)} estimated</span>}<span>{plan.buckets.overdue} overdue</span></div>
      </div>
      <div className="grid divide-y divide-w-line">{plan.lines.map((line) => {
        const transfers = networkPlan?.transfers.filter((transfer) => transfer.to_item_id === line.item_id) ?? []
        const transferQuantity = transfers.reduce((total, transfer) => total + Number(transfer.quantity), 0)
        const remaining = networkPlan?.remaining_shortages.find((shortage) => shortage.item_id === line.item_id)
        return <div key={line.item_id} className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"><div><div className="flex flex-wrap items-center gap-2"><p className="font-medium text-w-text">{line.name}</p><UrgencyBadge urgency={line.urgency} />{transferQuantity > 0 && <span className="rounded-full bg-emerald-400/15 px-2 py-0.5 text-[10px] text-emerald-300">Transfer option</span>}</div><p className="mt-1 text-xs text-w-dim">{formatNumber(line.average_daily_demand)}/day · {line.lead_demand ? `${formatNumber(line.lead_demand)} lead demand` : 'no lead demand'} · {line.runout_date ? `runs out ${line.runout_date}` : 'no runout date'}</p>{transferQuantity > 0 && <p className="mt-1 text-[11px] text-emerald-300">Move {formatNumber(transferQuantity)} from {transfers.map((transfer) => transfer.from_location_name).join(', ')} first{remaining ? `; forecast still suggests ordering ${formatNumber(remaining.suggested_order_quantity)}` : '; this covers the forecast shortage'}.</p>}</div><div className="flex items-center gap-3"><div className="text-right text-xs text-w-dim"><p className="font-medium text-w-text">Order {formatNumber(line.suggested_quantity)}{line.unit ? ` ${line.unit}` : ''}</p><p>{line.extended_cost === null ? 'Cost unavailable' : formatMoney(line.extended_cost)}</p></div><Button size="sm" variant={transferQuantity > 0 ? 'secondary' : undefined} disabled={orderingId === line.item_id} onClick={() => void handleOrder(line)}>{orderingId === line.item_id ? 'Ordering…' : transferQuantity > 0 ? 'Order anyway' : 'Order'}</Button></div></div>
      })}</div>
      {plan.suppressed_count > 0 && <div className="border-t border-w-line bg-w-surface2 px-4 py-3 text-xs text-w-dim"><span>{plan.suppressed_count} item{plan.suppressed_count === 1 ? '' : 's'} can’t be forecast yet: {Object.entries(plan.suppressed_by_status).map(([status, count]) => `${count} ${status.replaceAll('_', ' ')}`).join(', ')}.</span>{plan.suppressed_by_status.count_required && <button type="button" onClick={onAudit} className="ml-2 font-medium text-w-accent hover:underline">Count stock</button>}</div>}
    </section>
  )
}

function UrgencyBadge({ urgency }: { urgency: ForecastPlanLine['urgency'] }) { const label = urgency === 'overdue' ? 'Order now' : urgency === 'within_7_days' ? 'Within 7 days' : urgency === 'within_14_days' ? 'Within 14 days' : 'Later'; return <span className={`rounded-full px-2 py-0.5 text-[10px] ${urgency === 'overdue' ? 'bg-red-400/15 text-red-300' : urgency === 'within_7_days' ? 'bg-amber-400/15 text-amber-300' : 'bg-w-surface2 text-w-dim'}`}>{label}</span> }

function ParPreview({ preview, onApply }: { preview: ForecastParPreview; onApply: () => void }) {
  if (!preview.considered) return null
  return <section className="rounded-xl border border-w-line bg-w-surface p-4"><div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-[10px] font-medium uppercase tracking-[0.16em] text-w-accent">PAR drift</p><h2 className="mt-1 text-sm font-medium text-w-text">{preview.would_apply} PAR{preview.would_apply === 1 ? '' : 's'} ready to right-size</h2><p className="mt-1 text-xs text-w-dim">{preview.would_skip} blocked by the guardrails; nothing changes until you apply it.</p></div>{preview.would_apply > 0 && <Button size="sm" onClick={onApply}>Right-size eligible PARs</Button>}</div><div className="mt-3 divide-y divide-w-line">{preview.proposals.slice(0, 5).map((line) => <div key={line.item_id} className="flex items-center justify-between py-2 text-xs"><span className="font-medium text-w-text">{line.name}</span><span className="text-w-dim">{formatNumber(line.current_par)} → {formatNumber(line.recommended_par)} · {line.allowed ? 'ready' : line.reason.replaceAll('_', ' ')}</span></div>)}</div></section>
}

function formatNumber(value: number | null) {
  if (value === null) return '—'
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value)
}
function formatMoney(value: number) { return new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(value) }
