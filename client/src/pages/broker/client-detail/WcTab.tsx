import { useState, useEffect, useRef, type FormEvent, type ChangeEvent, type ReactNode } from 'react'
import {
  Loader2, AlertTriangle, TrendingUp, TrendingDown, Minus, Plus, Trash2, Gauge, HeartPulse, Boxes, Sparkles, Upload, MapPin,
} from 'lucide-react'
import { Card } from '../../../components/ui'
import {
  fetchWcClientDetail, recordWcMod, deleteWcMod, parseWcModWorksheet,
  fetchWcClassCodes, fetchWcClassExposures, recordWcClassExposure, deleteWcClassExposure,
  autoMapClassExposures, type ClassAutoMap,
} from '../../../api/broker'
import type {
  WcClientDetailResponse, WcClassCode, WcClassExposure,
} from '../../../types/broker'

const WC_BAND_TONE: Record<string, string> = {
  critical: 'text-red-400',
  at_risk: 'text-orange-400',
  fair: 'text-amber-400',
  good: 'text-emerald-400',
  unknown: 'text-zinc-500',
}

function pct(n: number | null | undefined, digits = 1) {
  if (n === null || n === undefined) return '—'
  return `${n > 0 ? '+' : ''}${n.toFixed(digits)}%`
}

function rateTone(trend: string) {
  // Rate increase = premiums up = bad for the client.
  return trend === 'increase' ? 'text-red-400' : trend === 'decrease' ? 'text-emerald-400' : 'text-zinc-400'
}

function DeltaPill({ value }: { value: number | null }) {
  if (value === null || value === undefined) return <span className="text-zinc-600 text-[11px]">{'—'}</span>
  const flat = value === 0
  // Up is worse for TRIR/DART/lost-days.
  const tone = flat ? 'text-zinc-500' : value > 0 ? 'text-red-400' : 'text-emerald-400'
  const Icon = flat ? Minus : value > 0 ? TrendingUp : TrendingDown
  return (
    <span className={`inline-flex items-center gap-0.5 text-[11px] font-mono ${tone}`}>
      <Icon className="h-3 w-3" />{Math.abs(value).toFixed(1)}%
    </span>
  )
}

function MetricCell({ label, value, sub, delta, tone }: {
  label: string; value: ReactNode; sub?: string; delta?: ReactNode; tone?: string
}) {
  return (
    <div className="bg-zinc-900 px-4 py-3">
      <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">{label}</div>
      <div className={`text-xl font-light font-mono mt-1 ${tone ?? 'text-zinc-200'}`}>{value}</div>
      <div className="flex items-center gap-2 mt-0.5">
        {delta}
        {sub && <span className="text-[10px] text-zinc-600">{sub}</span>}
      </div>
    </div>
  )
}

function TaxCell({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-lg bg-zinc-900/60 py-2">
      <div className={`text-lg font-mono ${tone}`}>{value}</div>
      <div className="text-[10px] text-zinc-500 mt-0.5">{label}</div>
    </div>
  )
}

function proxyTone(v: number): string {
  return v > 1 ? 'text-red-400' : v < 1 ? 'text-emerald-400' : 'text-zinc-300'
}

/* tiny no-dependency sparkline for the proxy mod trajectory (dashed 1.0 baseline) */
function ModSparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null
  const w = 220, h = 40, pad = 4, baseline = 1.0
  const lo = Math.min(baseline, ...values), hi = Math.max(baseline, ...values)
  const span = Math.max(0.001, hi - lo)
  const x = (i: number) => pad + (i / (values.length - 1)) * (w - 2 * pad)
  const y = (v: number) => pad + (1 - (v - lo) / span) * (h - 2 * pad)
  const d = values.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  return (
    <svg width={w} height={h} className="overflow-visible">
      <line x1={pad} y1={y(baseline)} x2={w - pad} y2={y(baseline)} className="stroke-zinc-700" strokeDasharray="2 2" />
      <path d={d} fill="none" className="stroke-sky-400" strokeWidth="1.5" />
      {values.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r="1.8" className="fill-sky-400" />)}
    </svg>
  )
}

export function WcTab({ companyId }: { companyId: string }) {
  const [detail, setDetail] = useState<WcClientDetailResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ policy_period_start: '', experience_mod: '', carrier: '', annual_premium: '', note: '' })
  const [source, setSource] = useState<'manual' | 'worksheet'>('manual')
  const [saving, setSaving] = useState(false)
  const [formErr, setFormErr] = useState<string | null>(null)
  const [parsing, setParsing] = useState(false)
  const [parseMsg, setParseMsg] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const onWorksheet = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''  // allow re-selecting the same file
    if (!file) return
    setParsing(true); setParseMsg(null)
    try {
      const res = await parseWcModWorksheet(companyId, file)
      if (!res.available || res.fields.experience_mod == null) {
        setParseMsg('Could not read a mod from that PDF — enter it manually below.'); setShowForm(true); return
      }
      const f = res.fields
      const mod = res.fields.experience_mod
      setForm({
        policy_period_start: f.policy_period_start ?? '', experience_mod: String(mod),
        carrier: f.carrier ?? '', annual_premium: '', note: 'Auto-extracted from experience-rating worksheet',
      })
      setSource('worksheet'); setShowForm(true)
      setParseMsg(`Extracted mod ${mod.toFixed(2)} from the worksheet — review and save.`)
    } catch {
      setParseMsg('Worksheet parse failed — enter the mod manually below.'); setShowForm(true)
    } finally { setParsing(false) }
  }

  const load = () => {
    setLoading(true)
    setError(false)
    fetchWcClientDetail(companyId)
      .then(setDetail)
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }
  useEffect(load, [companyId])

  const submitMod = async (e: FormEvent) => {
    e.preventDefault()
    const mod = parseFloat(form.experience_mod)
    if (!form.policy_period_start || !mod || mod <= 0) {
      setFormErr('Enter a policy start date and a positive experience mod.')
      return
    }
    setSaving(true)
    setFormErr(null)
    try {
      await recordWcMod(companyId, {
        policy_period_start: form.policy_period_start,
        experience_mod: mod,
        carrier: form.carrier || undefined,
        annual_premium: form.annual_premium ? parseFloat(form.annual_premium) : undefined,
        note: form.note || undefined,
        source,
      })
      setForm({ policy_period_start: '', experience_mod: '', carrier: '', annual_premium: '', note: '' })
      setSource('manual'); setParseMsg(null)
      setShowForm(false)
      load()
    } catch {
      setFormErr('Could not save. Try again.')
    } finally {
      setSaving(false)
    }
  }

  const removeMod = async (id: string) => {
    try {
      await deleteWcMod(companyId, id)
      load()
    } catch { /* leave list as-is on failure */ }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-40"><Loader2 className="h-5 w-5 text-zinc-500 animate-spin" /></div>
  }
  if (error || !detail) {
    return <Card className="p-5"><p className="text-sm text-zinc-500">Unable to load Workers&rsquo; Comp data.</p></Card>
  }

  const m = detail.metrics
  const benchRatio = m.trir && m.benchmark && m.benchmark.trir > 0 ? m.trir / m.benchmark.trir : null
  const latestMod = detail.mods.length ? detail.mods[detail.mods.length - 1] : null
  const cb = m.claim_breakdown
  const typed = cb.cumulative_trauma + cb.acute
  const totalForMix = Math.max(cb.cumulative_trauma + cb.acute + cb.unknown, 1)
  const inputCls = 'w-full bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500'

  return (
    <div className="space-y-4">
      {/* Metric header */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-px bg-white/10 border border-white/10 rounded-2xl overflow-hidden">
        <MetricCell
          label="TRIR"
          value={m.trir ?? '—'}
          sub={benchRatio ? `${benchRatio.toFixed(1)}× bench` : (m.benchmark ? `bench ${m.benchmark.trir}` : 'no benchmark')}
          delta={<DeltaPill value={m.prior.trir_delta_pct} />}
          tone={WC_BAND_TONE[m.severity_band]}
        />
        <MetricCell label="DART" value={m.dart_rate ?? '—'} sub={m.benchmark ? `bench ${m.benchmark.dart}` : undefined} delta={<DeltaPill value={m.prior.dart_delta_pct} />} />
        <MetricCell label="Recordables" value={m.recordable_cases} sub={`${m.dart_cases} DART`} />
        <MetricCell label="Lost days" value={m.lost_days} delta={<DeltaPill value={m.prior.lost_days_delta_pct} />} />
        <MetricCell
          label="Exp. Mod"
          value={latestMod ? latestMod.experience_mod.toFixed(2) : '—'}
          sub={latestMod ? (latestMod.experience_mod > 1 ? 'debit' : latestMod.experience_mod < 1 ? 'credit' : 'unity') : 'none on file'}
          tone={latestMod ? (latestMod.experience_mod > 1 ? 'text-red-400' : latestMod.experience_mod < 1 ? 'text-emerald-400' : 'text-zinc-300') : 'text-zinc-600'}
        />
        <MetricCell label="Days since" value={m.days_since_last_recordable ?? '—'} sub="last recordable" />
      </div>

      {m.data_quality.insufficient_population && (
        <p className="text-[11px] text-amber-400/80">Low exposure base &mdash; TRIR/DART are directional only.</p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Claim taxonomy */}
        <Card className="p-5">
          <div className="flex items-center gap-2 mb-4">
            <AlertTriangle className="h-4 w-4 text-zinc-500" />
            <h3 className="text-sm font-medium text-zinc-200 tracking-wide">Claim mix</h3>
          </div>
          <div className="flex h-2 rounded-full overflow-hidden bg-zinc-800 mb-3">
            <div className="bg-red-500/70" style={{ width: `${(cb.cumulative_trauma / totalForMix) * 100}%` }} />
            <div className="bg-amber-500/70" style={{ width: `${(cb.acute / totalForMix) * 100}%` }} />
            <div className="bg-zinc-600" style={{ width: `${(cb.unknown / totalForMix) * 100}%` }} />
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            <TaxCell label="Cumulative trauma" value={cb.cumulative_trauma} tone="text-red-400" />
            <TaxCell label="Acute" value={cb.acute} tone="text-amber-400" />
            <TaxCell label="Untyped" value={cb.unknown} tone="text-zinc-400" />
          </div>
          <div className="mt-4 pt-3 border-t border-zinc-800/60 flex items-center justify-between">
            <span className="text-xs text-zinc-500">Post-termination claims</span>
            <span className={`text-sm font-mono ${m.post_termination_cases > 0 ? 'text-red-400' : 'text-zinc-400'}`}>{m.post_termination_cases}</span>
          </div>
          {typed === 0 && (
            <p className="text-[11px] text-zinc-600 mt-2">Type recordables (acute vs cumulative trauma) on each incident to populate this.</p>
          )}
        </Card>

        {/* Return to work */}
        <Card className="p-5">
          <div className="flex items-center gap-2 mb-4">
            <HeartPulse className="h-4 w-4 text-zinc-500" />
            <h3 className="text-sm font-medium text-zinc-200 tracking-wide">Return to work</h3>
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            <TaxCell label="Lost-time" value={m.rtw.lost_time_cases} tone="text-zinc-300" />
            <TaxCell label="Open" value={m.rtw.open} tone={m.rtw.open > 0 ? 'text-orange-400' : 'text-zinc-400'} />
            <TaxCell label="Resolved" value={m.rtw.resolved} tone="text-emerald-400" />
          </div>
          <div className="mt-4 pt-3 border-t border-zinc-800/60 flex items-center justify-between">
            <span className="text-xs text-zinc-500">Avg days to RTW</span>
            <span className="text-sm font-mono text-zinc-300">{m.rtw.avg_days_to_rtw ?? '—'}</span>
          </div>
        </Card>
      </div>

      {/* NCCI jurisdiction overlay */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4">
          <MapPin className="h-4 w-4 text-zinc-500" />
          <h3 className="text-sm font-medium text-zinc-200 tracking-wide">NCCI rate trend by state</h3>
          <span className="text-[11px] text-zinc-600">2026 loss-cost filings</span>
        </div>
        {detail.states.length === 0 ? (
          <p className="text-sm text-zinc-500">No operating states on file (add business locations to enable the jurisdiction overlay).</p>
        ) : (
          <div className="space-y-2">
            {detail.states.map((s) => (
              <div key={s.state} className="flex items-center justify-between py-1.5 border-b border-zinc-800/30 last:border-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-zinc-200 w-8">{s.state}</span>
                  {s.rate?.note && <span className="text-[11px] text-zinc-600">{s.rate.note}</span>}
                </div>
                {s.rate ? (
                  <span className={`inline-flex items-center gap-1 text-sm font-mono ${rateTone(s.rate.trend)}`}>
                    {s.rate.trend === 'increase' ? <TrendingUp className="h-3.5 w-3.5" /> : s.rate.trend === 'decrease' ? <TrendingDown className="h-3.5 w-3.5" /> : <Minus className="h-3.5 w-3.5" />}
                    {pct(s.rate.loss_cost_change_pct)}
                  </span>
                ) : (
                  <span className="text-[11px] text-zinc-600">no NCCI data</span>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Experience-mod trajectory */}
      <Card className="p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Gauge className="h-4 w-4 text-zinc-500" />
            <h3 className="text-sm font-medium text-zinc-200 tracking-wide">Experience mod trajectory</h3>
          </div>
          <div className="flex items-center gap-2">
            <input ref={fileRef} type="file" accept="application/pdf" onChange={onWorksheet} className="hidden" />
            <button onClick={() => fileRef.current?.click()} disabled={parsing} className="inline-flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 px-2 py-1 rounded-lg border border-emerald-900/60 hover:border-emerald-700 disabled:opacity-50 transition-colors">
              {parsing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />} {parsing ? 'Reading…' : 'Upload worksheet'}
            </button>
            <button onClick={() => { setSource('manual'); setParseMsg(null); setShowForm((v) => !v) }} className="inline-flex items-center gap-1 text-xs text-zinc-300 hover:text-zinc-100 px-2 py-1 rounded-lg border border-zinc-700 hover:border-zinc-500 transition-colors">
              <Plus className="h-3.5 w-3.5" /> Record mod
            </button>
          </div>
        </div>
        {parseMsg && <p className="text-[11px] text-emerald-400/90 mb-3">{parseMsg}</p>}

        {showForm && (
          <form onSubmit={submitMod} className="grid grid-cols-2 md:grid-cols-5 gap-2 mb-4 p-3 rounded-xl bg-zinc-900/60 border border-zinc-800">
            <div>
              <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Policy start</label>
              <input type="date" value={form.policy_period_start} onChange={(e) => setForm({ ...form, policy_period_start: e.target.value })} className={inputCls} />
            </div>
            <div>
              <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Exp. mod</label>
              <input type="number" step="0.001" placeholder="1.05" value={form.experience_mod} onChange={(e) => setForm({ ...form, experience_mod: e.target.value })} className={inputCls} />
            </div>
            <div>
              <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Carrier</label>
              <input type="text" placeholder="optional" value={form.carrier} onChange={(e) => setForm({ ...form, carrier: e.target.value })} className={inputCls} />
            </div>
            <div>
              <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Annual premium</label>
              <input type="number" step="1" placeholder="optional" value={form.annual_premium} onChange={(e) => setForm({ ...form, annual_premium: e.target.value })} className={inputCls} />
            </div>
            <div className="flex items-end">
              <button type="submit" disabled={saving} className="w-full bg-zinc-100 text-zinc-900 text-sm font-medium rounded-lg px-3 py-1.5 hover:bg-white disabled:opacity-50 transition-colors">
                {saving ? 'Saving…' : 'Save'}
              </button>
            </div>
            {formErr && <p className="col-span-full text-[11px] text-red-400">{formErr}</p>}
          </form>
        )}

        {detail.mods.length === 0 ? (
          <p className="text-sm text-zinc-500">No experience mods recorded. The mod is the number carriers price WC on &mdash; record it each policy period to track the trajectory.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-800/60">
                  <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Policy period</th>
                  <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">Mod</th>
                  <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Carrier</th>
                  <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">Premium</th>
                  <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Source</th>
                  <th className="pb-2 w-8" />
                </tr>
              </thead>
              <tbody>
                {detail.mods.map((mod) => (
                  <tr key={mod.id} className="border-b border-zinc-800/30 last:border-0">
                    <td className="py-2.5 pr-4 text-zinc-300">{mod.policy_period_start}</td>
                    <td className={`py-2.5 pr-4 text-right font-mono ${mod.experience_mod > 1 ? 'text-red-400' : mod.experience_mod < 1 ? 'text-emerald-400' : 'text-zinc-300'}`}>{mod.experience_mod.toFixed(3)}</td>
                    <td className="py-2.5 pr-4 text-zinc-400 text-xs">{mod.carrier ?? '—'}</td>
                    <td className="py-2.5 pr-4 text-right text-zinc-400 tabular-nums">{mod.annual_premium != null ? `$${mod.annual_premium.toLocaleString()}` : '—'}</td>
                    <td className="py-2.5 pr-4">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${mod.source === 'worksheet' ? 'text-sky-300 border-sky-900/60' : 'text-zinc-500 border-zinc-700'}`}>{mod.source === 'worksheet' ? 'worksheet' : 'manual'}</span>
                    </td>
                    <td className="py-2.5 text-right">
                      <button onClick={() => removeMod(mod.id)} className="text-zinc-600 hover:text-red-400 transition-colors"><Trash2 className="h-3.5 w-3.5" /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {detail.mod_proxy && detail.mod_proxy.points.length > 0 && (
          <div className="mt-5 pt-4 border-t border-zinc-800/60">
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-xs font-medium text-zinc-300 flex items-center gap-1.5">
                Directional proxy <span className="text-[10px] font-normal text-zinc-600">auto · incurred ÷ expected losses</span>
              </h4>
              <span className={`text-sm font-mono ${proxyTone(detail.mod_proxy.points[detail.mod_proxy.points.length - 1].experience_mod)}`}>
                {detail.mod_proxy.points[detail.mod_proxy.points.length - 1].experience_mod.toFixed(2)}
              </span>
            </div>
            <ModSparkline values={detail.mod_proxy.points.map((p) => p.experience_mod)} />
            <p className="text-[10px] text-zinc-600 mt-1.5">{detail.mod_proxy.basis}</p>
          </div>
        )}
      </Card>

      {/* WC class-code exposures (wcclass01) */}
      <WcClassExposures companyId={companyId} />
    </div>
  )
}

function WcClassExposures({ companyId }: { companyId: string }) {
  const [exposures, setExposures] = useState<WcClassExposure[]>([])
  const [codes, setCodes] = useState<WcClassCode[]>([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ class_code: '', state: '', payroll: '', headcount: '', note: '' })
  const [saving, setSaving] = useState(false)
  const [autoProps, setAutoProps] = useState<ClassAutoMap | null>(null)
  const [autoBusy, setAutoBusy] = useState(false)
  const [savingAll, setSavingAll] = useState(false)
  const inputCls = 'w-full bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500'

  const load = () => { fetchWcClassExposures(companyId).then((r) => setExposures(r.exposures)).catch(() => {}) }
  useEffect(() => {
    load()
    fetchWcClassCodes().then((r) => setCodes(r.class_codes)).catch(() => {})
  }, [companyId])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!form.class_code) return
    setSaving(true)
    try {
      const r = await recordWcClassExposure(companyId, {
        class_code: form.class_code, state: form.state || undefined,
        payroll: form.payroll ? parseFloat(form.payroll) : undefined,
        headcount: form.headcount ? parseInt(form.headcount, 10) : undefined,
        note: form.note || undefined,
      })
      setExposures(r.exposures)
      setForm({ class_code: '', state: '', payroll: '', headcount: '', note: '' }); setShowForm(false)
    } catch { /* leave as-is */ } finally { setSaving(false) }
  }
  const remove = async (id: string) => { try { await deleteWcClassExposure(companyId, id); load() } catch { /* noop */ } }

  const runAutoMap = async () => {
    setAutoBusy(true); setAutoProps(null)
    try { setAutoProps(await autoMapClassExposures(companyId)) } catch { /* noop */ } finally { setAutoBusy(false) }
  }
  const saveAll = async () => {
    if (!autoProps?.proposed.length) return
    setSavingAll(true)
    try {
      for (const p of autoProps.proposed) {
        await recordWcClassExposure(companyId, { class_code: p.class_code, state: p.state, payroll: p.payroll, headcount: p.headcount })
      }
      setAutoProps(null); load()
    } catch { /* leave */ } finally { setSavingAll(false) }
  }

  const totalPremium = exposures.reduce((s, e) => s + (e.est_manual_premium ?? 0), 0)

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <Boxes className="h-4 w-4 text-zinc-500" />
          <h3 className="text-sm font-medium text-zinc-200 tracking-wide">Class-code exposures</h3>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={runAutoMap} disabled={autoBusy} className="inline-flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 px-2 py-1 rounded-lg border border-emerald-900/60 hover:border-emerald-700 transition-colors disabled:opacity-50">
            <Sparkles className="h-3.5 w-3.5" /> {autoBusy ? 'Mapping…' : 'Auto-map from employees'}
          </button>
          <button onClick={() => setShowForm((v) => !v)} className="inline-flex items-center gap-1 text-xs text-zinc-300 hover:text-zinc-100 px-2 py-1 rounded-lg border border-zinc-700 hover:border-zinc-500 transition-colors">
            <Plus className="h-3.5 w-3.5" /> Add class
          </button>
        </div>
      </div>
      <p className="text-[11px] text-zinc-500 mb-3">Payroll by NCCI class drives class-level underwriting. Rates are an illustrative reference seed (pending a licensed NCCI feed); estimated manual premium = payroll ÷ 100 × rate.</p>

      {autoProps && (
        <div className="mb-4 p-3 rounded-xl bg-emerald-950/20 border border-emerald-900/40">
          {autoProps.proposed.length === 0 ? (
            <p className="text-xs text-zinc-400">{autoProps.employee_count === 0 ? 'No employees on file to map.' : 'Could not map any titles to class codes — add manually.'}</p>
          ) : (
            <>
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] text-emerald-400 font-medium">AI mapped {autoProps.employee_count} employees → {autoProps.proposed.length} class code(s). Review &amp; save.</span>
                <button onClick={saveAll} disabled={savingAll} className="text-xs bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg px-3 py-1 disabled:opacity-50">{savingAll ? 'Saving…' : 'Save all'}</button>
              </div>
              <div className="space-y-1">
                {autoProps.proposed.map((p) => (
                  <div key={p.class_code} className="flex items-center gap-3 text-xs py-1 border-b border-zinc-800/30 last:border-0">
                    <span className="font-mono text-zinc-200">{p.class_code}</span>
                    <span className="text-zinc-400 flex-1 truncate">{p.description}</span>
                    <span className="text-zinc-500">{p.headcount} ppl · ${p.payroll.toLocaleString()}</span>
                  </div>
                ))}
                {autoProps.unmapped.length > 0 && <p className="text-[11px] text-amber-400/80 mt-1">{autoProps.unmapped.length} title(s) unmapped — add manually if needed.</p>}
              </div>
            </>
          )}
        </div>
      )}

      {showForm && (
        <form onSubmit={submit} className="grid grid-cols-2 md:grid-cols-5 gap-2 mb-4 p-3 rounded-xl bg-zinc-900/60 border border-zinc-800">
          <div className="md:col-span-2">
            <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Class code</label>
            <select value={form.class_code} onChange={(e) => setForm({ ...form, class_code: e.target.value })} className={inputCls}>
              <option value="">Select…</option>
              {codes.map((c) => <option key={c.class_code} value={c.class_code}>{c.class_code} — {c.description}</option>)}
            </select>
          </div>
          <div><label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">State</label><input maxLength={2} placeholder="US" value={form.state} onChange={(e) => setForm({ ...form, state: e.target.value.toUpperCase() })} className={inputCls} /></div>
          <div><label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Payroll</label><input type="number" step="1000" placeholder="$" value={form.payroll} onChange={(e) => setForm({ ...form, payroll: e.target.value })} className={inputCls} /></div>
          <div><label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Headcount</label><input type="number" placeholder="optional" value={form.headcount} onChange={(e) => setForm({ ...form, headcount: e.target.value })} className={inputCls} /></div>
          <div className="md:col-span-5">
            <button type="submit" disabled={saving} className="bg-zinc-100 text-zinc-900 text-sm font-medium rounded-lg px-4 py-1.5 hover:bg-white disabled:opacity-50 transition-colors">{saving ? 'Saving…' : 'Save'}</button>
          </div>
        </form>
      )}

      {exposures.length === 0 ? (
        <p className="text-sm text-zinc-500">No class-code exposures recorded. Add the client's payroll by NCCI class for class-level underwriting detail.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-zinc-800/60">
                <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Class</th>
                <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider">State</th>
                <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">Payroll</th>
                <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">Rate</th>
                <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">Est. premium</th>
                <th className="pb-2 w-8" />
              </tr>
            </thead>
            <tbody>
              {exposures.map((e) => (
                <tr key={e.id} className="border-b border-zinc-800/30 last:border-0">
                  <td className="py-2.5 pr-4 text-zinc-300"><span className="font-mono">{e.class_code}</span>{e.description && <span className="text-xs text-zinc-600 ml-2">{e.description}</span>}</td>
                  <td className="py-2.5 pr-4 text-zinc-400">{e.state}</td>
                  <td className="py-2.5 pr-4 text-right text-zinc-400 tabular-nums">{e.payroll != null ? `$${e.payroll.toLocaleString()}` : '—'}</td>
                  <td className="py-2.5 pr-4 text-right text-zinc-400 tabular-nums">{e.base_rate != null ? e.base_rate.toFixed(2) : '—'}</td>
                  <td className="py-2.5 pr-4 text-right font-mono text-zinc-200">{e.est_manual_premium != null ? `$${e.est_manual_premium.toLocaleString()}` : '—'}</td>
                  <td className="py-2.5 text-right"><button onClick={() => remove(e.id)} className="text-zinc-600 hover:text-red-400 transition-colors"><Trash2 className="h-3.5 w-3.5" /></button></td>
                </tr>
              ))}
              {totalPremium > 0 && (
                <tr className="border-t border-zinc-700/60">
                  <td className="py-2.5 pr-4 text-zinc-500 text-xs uppercase tracking-wider" colSpan={4}>Estimated manual premium</td>
                  <td className="py-2.5 pr-4 text-right font-mono text-zinc-100">${totalPremium.toLocaleString()}</td>
                  <td />
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
