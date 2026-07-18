import { useState, useEffect, Fragment, type FormEvent } from 'react'
import { Building2, Plus, Loader2, AlertCircle, Pencil, Trash2, X, ChevronDown, ChevronRight, Upload } from 'lucide-react'
import { Card } from '../../../components/ui'
import { SovImportModal } from '../../../components/property/SovImportModal'
import { fetchPropertySov, createBuilding, updateBuilding, deleteBuilding } from '../../../api/risk/property'
import type { PropertySov, PropertyBuilding, BuildingPayload, ConstructionType } from '../../../types/property'
import { CONSTRUCTION_LABEL, COPE_TONE, PERIL_TONE, READINESS_TONE, FIX_SEVERITY_TONE, RISK_LEVEL_TONE } from '../../../types/property'

const inputCls = 'w-full bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500'
const CONSTRUCTION_OPTS: ConstructionType[] = ['fire_resistive', 'modified_fire_resistive', 'masonry_non_combustible', 'non_combustible', 'joisted_masonry', 'frame']

function fmtUsd(n: number | null): string {
  if (n == null) return '—'
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`
  if (Math.abs(n) >= 1_000) return `$${Math.round(n / 1000)}K`
  return `$${Math.round(n)}`
}

const WORST_PERIL = (b: PropertyBuilding) => {
  const order = ['severe', 'high', 'elevated', 'moderate', 'low']
  const tiers = b.perils.map((p) => p.tier).filter(Boolean) as string[]
  return tiers.sort((a, z) => order.indexOf(a) - order.indexOf(z))[0] ?? null
}

// Module-scope so it is NOT re-created on every parent render (a nested component
// would remount its <input> each keystroke and drop focus).
function Field({ label, value, onChange, type = 'text', placeholder }:
  { label: string; value: string; onChange: (v: string) => void; type?: string; placeholder?: string }) {
  return (
    <div>
      <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">{label}</label>
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)} className={inputCls} placeholder={placeholder} />
    </div>
  )
}

export default function Property() {
  const [data, setData] = useState<PropertySov | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [editing, setEditing] = useState<PropertyBuilding | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const load = () => {
    setLoading(true); setError(false)
    fetchPropertySov().then(setData).catch(() => setError(true)).finally(() => setLoading(false))
  }
  useEffect(load, [])

  function openAdd() { setEditing(null); setShowForm(true) }
  function openEdit(b: PropertyBuilding) { setEditing(b); setShowForm(true) }
  function toggleExpand(id: string) {
    setExpanded((prev) => { const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n })
  }

  async function onDelete(b: PropertyBuilding) {
    if (!confirm(`Remove ${b.name || 'this building'} from the Statement of Values?`)) return
    setData(await deleteBuilding(b.id))
  }

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>
  if (error || !data) return (
    <div className="flex flex-col items-center justify-center h-64 text-zinc-500">
      <AlertCircle className="h-8 w-8 mb-2" /><p className="text-sm">Unable to load property.</p>
    </div>
  )

  const { rollup: r, buildings, readiness, exposure, plan, risk } = data
  const itvPct = r.itv.portfolio_ratio != null ? Math.round(r.itv.portfolio_ratio * 100) : null

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
            <Building2 className="h-5 w-5 text-zinc-400" /> Commercial Property
          </h1>
          <p className="text-sm text-zinc-500 mt-1">Your Statement of Values — buildings, COPE, and insurance-to-value. Catastrophe exposure populates once buildings are geocoded.</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowImport(true)} className="inline-flex items-center gap-1.5 text-sm text-zinc-300 px-3 py-1.5 rounded-lg border border-zinc-700 hover:border-zinc-500 transition-colors">
            <Upload className="h-4 w-4" /> Import
          </button>
          <button onClick={openAdd} className="inline-flex items-center gap-1.5 text-sm text-zinc-200 px-3 py-1.5 rounded-lg border border-zinc-700 hover:border-zinc-500 transition-colors">
            <Plus className="h-4 w-4" /> Add building
          </button>
        </div>
      </div>

      {/* Composite property risk score (underwriting headline) */}
      {risk && risk.score != null && (
        <Card className="p-5">
          <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Property risk score</div>
          <div className="flex items-baseline gap-3 mt-1">
            <span className={`text-4xl font-light font-mono ${COPE_TONE[risk.grade ?? ''] ?? 'text-zinc-100'}`}>
              {risk.score}<span className="text-lg text-zinc-600">/100</span>
            </span>
            <span className={`text-sm font-semibold uppercase ${RISK_LEVEL_TONE[risk.risk_level ?? ''] ?? 'text-zinc-400'}`}>
              {risk.risk_level} risk · grade {risk.grade}
            </span>
          </div>
          <div className="text-[11px] text-zinc-600 mt-1">TIV-weighted COPE quality, adjusted for insurance-to-value + catastrophe exposure · {risk.rated} buildings scored.</div>
          {risk.top_risks.length > 0 && (
            <div className="mt-3 pt-3 border-t border-white/[0.06]">
              <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold mb-1.5">Top risk contributors</div>
              <ul className="space-y-1">
                {risk.top_risks.slice(0, 3).map((t) => (
                  <li key={t.building_id} className="text-[12px] flex items-center gap-2">
                    <span className={`font-mono font-semibold w-4 ${COPE_TONE[t.grade] ?? 'text-zinc-400'}`}>{t.grade}</span>
                    <span className="text-zinc-300">{t.name || '(unnamed)'}</span>
                    <span className="text-zinc-600">{t.drivers.map((d) => d.detail).join(' · ') || 'COPE-limited'}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      )}

      {/* Rollup */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card className="p-4">
          <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Total insured value</div>
          <div className="text-3xl font-light font-mono mt-1 text-zinc-100">{fmtUsd(r.tiv)}</div>
          <div className="text-[10px] text-zinc-600">building + contents + BI</div>
        </Card>
        <Card className="p-4">
          <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Buildings</div>
          <div className="text-3xl font-light font-mono mt-1 text-zinc-200">{r.building_count}</div>
          <div className="text-[10px] text-zinc-600">on the SOV</div>
        </Card>
        <Card className="p-4">
          <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">COPE quality</div>
          <div className={`text-3xl font-light font-mono mt-1 ${r.worst_cope_grade ? COPE_TONE[r.worst_cope_grade] ?? 'text-zinc-200' : 'text-zinc-600'}`}>
            {r.avg_cope_score ?? '—'}
          </div>
          <div className="text-[10px] text-zinc-600">avg score · worst grade {r.worst_cope_grade ?? '—'}</div>
        </Card>
        <Card className="p-4">
          <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Insurance-to-value</div>
          <div className={`text-3xl font-light font-mono mt-1 ${itvPct == null ? 'text-zinc-600' : itvPct < 90 ? 'text-amber-400' : 'text-emerald-400'}`}>
            {itvPct != null ? `${itvPct}%` : '—'}
          </div>
          <div className="text-[10px] text-zinc-600">{r.itv.under_count} under-insured of {r.itv.rated_count}</div>
        </Card>
      </div>

      {/* Modeled $ exposure (directional) */}
      {exposure && buildings.length > 0 && (
        <Card className="p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Modeled exposure</span>
            <span className="text-[10px] text-zinc-600">directional estimate · not a cat model</span>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <div className="text-2xl font-light font-mono text-zinc-100">{fmtUsd(exposure.total_aal)}</div>
              <div className="text-[10px] text-zinc-600 uppercase tracking-wider mt-0.5">Avg annual loss</div>
            </div>
            <div>
              <div className="text-2xl font-light font-mono text-amber-400">{fmtUsd(exposure.worst_pml)}</div>
              <div className="text-[10px] text-zinc-600 uppercase tracking-wider mt-0.5">Worst PML{exposure.worst_pml_peril ? ` · ${exposure.worst_pml_peril}` : ''}</div>
            </div>
            <div>
              <div className={`text-2xl font-light font-mono ${exposure.coinsurance_shortfall > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>{fmtUsd(exposure.coinsurance_shortfall)}</div>
              <div className="text-[10px] text-zinc-600 uppercase tracking-wider mt-0.5">Coinsurance shortfall</div>
            </div>
          </div>
          <p className="text-[10px] text-zinc-600 mt-3">AAL = expected loss per year · PML = worst single catastrophe event (peril accumulated across buildings) · shortfall = added insured value to meet a 90% coinsurance clause.</p>
        </Card>
      )}

      {/* Submission readiness */}
      {readiness && buildings.length > 0 && (
        <Card className="p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Property submission readiness</span>
            <span className={`text-sm font-semibold ${READINESS_TONE[readiness.band] ?? 'text-zinc-300'}`}>
              {readiness.score}/100 · {readiness.band}
            </span>
          </div>
          {readiness.top_fixes.length > 0 && (
            <ul className="space-y-0.5">
              {readiness.top_fixes.map((f) => (
                <li key={f} className="text-[12px] text-zinc-400 flex items-start gap-1.5"><span className="text-zinc-600 mt-px">•</span>{f}</li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {/* Risk-improvement plan */}
      {plan && plan.fixes.length > 0 && (
        <Card className="p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Risk-improvement plan</span>
            <span className="text-[10px] text-zinc-600">{plan.summary.total} item{plan.summary.total === 1 ? '' : 's'} · prioritized</span>
          </div>
          <ul className="space-y-2.5">
            {plan.fixes.map((f, i) => (
              <li key={f.key + i} className="flex items-start gap-2.5">
                <span className={`mt-0.5 shrink-0 text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded ${FIX_SEVERITY_TONE[f.severity] ?? 'bg-zinc-800 text-zinc-400'}`}>{f.severity}</span>
                <div className="min-w-0">
                  <div className="text-[13px] text-zinc-200">
                    {f.label}
                    {f.impact && <span className="ml-2 text-[11px] font-mono text-emerald-400">{f.impact}</span>}
                  </div>
                  <div className="text-[11px] text-zinc-500">{f.detail}</div>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* Buildings table */}
      {buildings.length === 0 ? (
        <Card className="p-8 text-center">
          <p className="text-sm text-zinc-400">No buildings yet.</p>
          <p className="text-xs text-zinc-600 mt-1">Add your locations' buildings to build the Statement of Values.</p>
        </Card>
      ) : (
        <Card className="p-0 overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-zinc-800/60 bg-zinc-900/40 text-[11px] text-zinc-500 uppercase tracking-wider">
                <th className="px-4 py-2.5 w-6"></th>
                <th className="px-4 py-2.5">Building</th>
                <th className="px-4 py-2.5">Construction</th>
                <th className="px-4 py-2.5 text-right">TIV</th>
                <th className="px-4 py-2.5 text-center">COPE</th>
                <th className="px-4 py-2.5 text-right">ITV</th>
                <th className="px-4 py-2.5 text-center">Cat</th>
                <th className="px-4 py-2.5 text-center">Risk</th>
                <th className="px-4 py-2.5"></th>
              </tr>
            </thead>
            <tbody>
              {buildings.map((b) => {
                const worst = WORST_PERIL(b)
                const itv = b.itv_ratio != null ? Math.round(b.itv_ratio * 100) : null
                const br = risk?.by_building[b.id]
                const isOpen = expanded.has(b.id)
                return (
                  <Fragment key={b.id}>
                    <tr className="border-b border-zinc-800/30 last:border-0 hover:bg-zinc-900/30">
                      <td className="px-4 py-3">
                        <button onClick={() => toggleExpand(b.id)} className="text-zinc-600 hover:text-zinc-300" aria-label="Toggle catastrophe detail">
                          {isOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                        </button>
                      </td>
                      <td className="px-4 py-3">
                        <div className="text-zinc-100">{b.name || '(unnamed)'}</div>
                        <div className="text-[11px] text-zinc-600">{[b.city, b.state].filter(Boolean).join(', ') || '—'}</div>
                      </td>
                      <td className="px-4 py-3 text-zinc-400 text-xs">{b.construction_type ? CONSTRUCTION_LABEL[b.construction_type] : '—'}{b.sprinklered && <span className="ml-1 text-emerald-500">·spr</span>}</td>
                      <td className="px-4 py-3 text-right font-mono text-zinc-300">{fmtUsd(b.tiv)}</td>
                      <td className="px-4 py-3 text-center"><span className={`font-mono font-semibold ${COPE_TONE[b.cope_grade] ?? 'text-zinc-400'}`}>{b.cope_grade}</span></td>
                      <td className={`px-4 py-3 text-right font-mono ${itv == null ? 'text-zinc-600' : itv < 90 ? 'text-amber-400' : 'text-emerald-400'}`}>{itv != null ? `${itv}%` : '—'}</td>
                      <td className="px-4 py-3 text-center text-xs">
                        {worst ? <span className={`uppercase font-semibold ${PERIL_TONE[worst] ?? 'text-zinc-400'}`}>{worst}</span>
                          : <span className="text-zinc-600">{b.geocoded_at ? '—' : 'pending'}</span>}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {br?.grade
                          ? <span className={`font-mono font-semibold ${COPE_TONE[br.grade] ?? 'text-zinc-400'}`} title={`${br.score}/100 · ${br.risk_level} risk`}>{br.grade}</span>
                          : <span className="text-zinc-600">—</span>}
                      </td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <button onClick={() => openEdit(b)} className="text-zinc-500 hover:text-zinc-200 mr-2"><Pencil className="h-3.5 w-3.5 inline" /></button>
                        <button onClick={() => onDelete(b)} className="text-zinc-600 hover:text-red-400"><Trash2 className="h-3.5 w-3.5 inline" /></button>
                      </td>
                    </tr>
                    {isOpen && (
                      <tr className="bg-zinc-900/40 border-b border-zinc-800/30">
                        <td></td>
                        <td colSpan={8} className="px-4 py-3">
                          {br && br.score != null && (
                            <div className="mb-2.5 text-[11px]">
                              <span className="text-zinc-500">Risk score </span>
                              <span className={`font-mono font-semibold ${COPE_TONE[br.grade ?? ''] ?? 'text-zinc-300'}`}>{br.score}/100</span>
                              <span className={`ml-1.5 uppercase ${RISK_LEVEL_TONE[br.risk_level ?? ''] ?? 'text-zinc-500'}`}>{br.risk_level} risk</span>
                              {br.drivers.filter((d) => d.delta < 0).length > 0 && (
                                <span className="text-zinc-600"> — {br.drivers.filter((d) => d.delta < 0).map((d) => `${d.detail} (${d.delta})`).join(', ')}</span>
                              )}
                            </div>
                          )}
                          {exposure?.buildings[b.id] && (
                            <div className="mb-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-zinc-500">
                              <span>AAL <span className="font-mono text-zinc-300">{fmtUsd(exposure.buildings[b.id].aal)}</span></span>
                              <span>worst PML <span className="font-mono text-amber-400">{fmtUsd(exposure.buildings[b.id].worst_pml)}</span></span>
                              {exposure.buildings[b.id].coinsurance_shortfall > 0 && (
                                <span>coinsurance shortfall <span className="font-mono text-amber-400">{fmtUsd(exposure.buildings[b.id].coinsurance_shortfall)}</span></span>
                              )}
                              <span className="text-zinc-700">directional</span>
                            </div>
                          )}
                          <PerilDetail b={b} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </Card>
      )}

      {showForm && (
        <BuildingModal building={editing} onClose={() => setShowForm(false)} onSaved={(sov) => { setData(sov); setShowForm(false) }} />
      )}
      {showImport && (
        <SovImportModal onClose={() => setShowImport(false)} onImported={load} />
      )}
    </div>
  )
}

const PERILS = ['flood', 'quake', 'wildfire', 'wind'] as const
const PERIL_LABEL: Record<string, string> = { flood: 'Flood', quake: 'Earthquake', wildfire: 'Wildfire', wind: 'Wind' }

function PerilDetail({ b }: { b: PropertyBuilding }) {
  if (!b.geocoded_at) {
    return <p className="text-[11px] text-zinc-500">Catastrophe exposure pending — add a full street address; geocoding runs in the background.</p>
  }
  const byPeril = Object.fromEntries(b.perils.map((p) => [p.peril, p]))
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
      {PERILS.map((k) => {
        const p = byPeril[k]
        return (
          <div key={k} className="rounded-lg bg-zinc-950/60 border border-zinc-800/60 px-3 py-2">
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">{PERIL_LABEL[k]}</div>
            {p && p.tier ? (
              <>
                <div className={`text-sm font-semibold uppercase ${PERIL_TONE[p.tier] ?? 'text-zinc-300'}`}>{p.tier}</div>
                <div className="text-[10px] text-zinc-600">{p.zone ?? '—'}{p.source ? ` · ${p.source}` : ''}</div>
              </>
            ) : p && p.error ? (
              <div className="text-[10px] text-zinc-600">lookup failed</div>
            ) : (
              <div className="text-[10px] text-zinc-600">—</div>
            )}
          </div>
        )
      })}
    </div>
  )
}

const NUM_FIELDS = ['year_built', 'sq_ft', 'stories', 'roof_year', 'building_value', 'contents_value', 'bi_value', 'replacement_cost', 'insured_value', 'coinsurance_pct', 'bi_months', 'aop_deductible', 'wind_deductible_pct', 'named_storm_deductible_pct', 'quake_deductible_pct', 'wiring_year'] as const

function BuildingModal({ building, onClose, onSaved }: { building: PropertyBuilding | null; onClose: () => void; onSaved: (s: PropertySov) => void }) {
  const [f, setF] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {}
    const keys = ['name', 'address', 'city', 'state', 'zipcode', 'occupancy', 'construction_type', 'protection_class', 'note', 'valuation_basis', 'ordinance_law', 'roof_type', ...NUM_FIELDS]
    keys.forEach((k) => { const v = building?.[k as keyof PropertyBuilding]; init[k] = v == null ? '' : String(v) })
    return init
  })
  const [sprinklered, setSprinklered] = useState(building?.sprinklered ?? false)
  const [blanket, setBlanket] = useState(building?.blanket ?? false)
  const [centralAlarm, setCentralAlarm] = useState(building?.central_station_alarm ?? false)
  const [cooking, setCooking] = useState(building?.cooking_nfpa96 ?? false)
  const [hotWork, setHotWork] = useState(building?.hot_work ?? false)
  const [hazmat, setHazmat] = useState(building?.hazmat ?? false)
  const [saving, setSaving] = useState(false)
  const set = (k: string, v: string) => setF((p) => ({ ...p, [k]: v }))

  async function submit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    const numOrNull = (k: string) => { const v = parseFloat(f[k]); return Number.isFinite(v) ? v : null }
    const payload: BuildingPayload = {
      name: f.name || null, address: f.address || null, city: f.city || null,
      state: f.state ? f.state.toUpperCase().slice(0, 2) : null, zipcode: f.zipcode || null,
      occupancy: f.occupancy || null,
      construction_type: (f.construction_type || null) as ConstructionType | null,
      year_built: numOrNull('year_built'), sq_ft: numOrNull('sq_ft'), stories: numOrNull('stories'),
      roof_year: numOrNull('roof_year'), sprinklered, protection_class: f.protection_class || null,
      building_value: numOrNull('building_value'), contents_value: numOrNull('contents_value'),
      bi_value: numOrNull('bi_value'), replacement_cost: numOrNull('replacement_cost'),
      insured_value: numOrNull('insured_value'), note: f.note || null,
      // deeper capture (propd01)
      valuation_basis: (f.valuation_basis || null) as 'RCV' | 'ACV' | null,
      coinsurance_pct: numOrNull('coinsurance_pct'),
      ordinance_law: f.ordinance_law || null,
      bi_months: numOrNull('bi_months'),
      blanket,
      aop_deductible: numOrNull('aop_deductible'),
      wind_deductible_pct: numOrNull('wind_deductible_pct'),
      named_storm_deductible_pct: numOrNull('named_storm_deductible_pct'),
      quake_deductible_pct: numOrNull('quake_deductible_pct'),
      roof_type: f.roof_type || null,
      wiring_year: numOrNull('wiring_year'),
      central_station_alarm: centralAlarm,
      cooking_nfpa96: cooking,
      hot_work: hotWork,
      hazmat,
      // preserve the long-tail JSONB (set via CSV/parse) — the form doesn't edit it.
      policy_detail: building?.policy_detail ?? null,
    }
    try {
      const sov = building ? await updateBuilding(building.id, payload) : await createBuilding(payload)
      onSaved(sov)
    } catch { /* keep open */ } finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-zinc-950 border border-zinc-800 rounded-2xl w-full max-w-2xl max-h-[88vh] overflow-y-auto p-5" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-zinc-200">{building ? 'Edit building' : 'Add building'}</h3>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200"><X className="h-4 w-4" /></button>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold mb-2">Identity</div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              <Field label="Name" value={f.name ?? ''} onChange={(v) => set('name', v)} placeholder="HQ" />
              <Field label="Address" value={f.address ?? ''} onChange={(v) => set('address', v)} />
              <Field label="Occupancy" value={f.occupancy ?? ''} onChange={(v) => set('occupancy', v)} placeholder="office" />
              <Field label="City" value={f.city ?? ''} onChange={(v) => set('city', v)} />
              <Field label="State" value={f.state ?? ''} onChange={(v) => set('state', v)} placeholder="CA" />
              <Field label="ZIP" value={f.zipcode ?? ''} onChange={(v) => set('zipcode', v)} />
            </div>
            <p className="text-[10px] text-zinc-600 mt-1">A full street address enables catastrophe geocoding.</p>
          </div>
          <div>
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold mb-2">COPE</div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              <div>
                <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Construction</label>
                <select value={f.construction_type ?? ''} onChange={(e) => set('construction_type', e.target.value)} className={inputCls}>
                  <option value="">—</option>
                  {CONSTRUCTION_OPTS.map((c) => <option key={c} value={c}>{CONSTRUCTION_LABEL[c]}</option>)}
                </select>
              </div>
              <Field label="Year built" value={f.year_built ?? ''} onChange={(v) => set('year_built', v)} type="number" />
              <Field label="Sq ft" value={f.sq_ft ?? ''} onChange={(v) => set('sq_ft', v)} type="number" />
              <Field label="Stories" value={f.stories ?? ''} onChange={(v) => set('stories', v)} type="number" />
              <Field label="Roof year" value={f.roof_year ?? ''} onChange={(v) => set('roof_year', v)} type="number" />
              <Field label="ISO PPC (1-10)" value={f.protection_class ?? ''} onChange={(v) => set('protection_class', v)} />
              <Field label="Roof type" value={f.roof_type ?? ''} onChange={(v) => set('roof_type', v)} placeholder="TPO / metal / shingle" />
              <Field label="Wiring year" value={f.wiring_year ?? ''} onChange={(v) => set('wiring_year', v)} type="number" />
            </div>
            <div className="flex flex-wrap gap-x-5 gap-y-2 mt-2 text-sm text-zinc-300">
              <label className="inline-flex items-center gap-2">
                <input type="checkbox" checked={sprinklered} onChange={(e) => setSprinklered(e.target.checked)} className="rounded border-zinc-600 bg-zinc-800 text-emerald-500 focus:ring-emerald-500" />
                Sprinklered
              </label>
              <label className="inline-flex items-center gap-2">
                <input type="checkbox" checked={centralAlarm} onChange={(e) => setCentralAlarm(e.target.checked)} className="rounded border-zinc-600 bg-zinc-800 text-emerald-500 focus:ring-emerald-500" />
                Central-station fire alarm
              </label>
            </div>
          </div>
          <div>
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold mb-2">Values</div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              <Field label="Building $" value={f.building_value ?? ''} onChange={(v) => set('building_value', v)} type="number" />
              <Field label="Contents $" value={f.contents_value ?? ''} onChange={(v) => set('contents_value', v)} type="number" />
              <Field label="Business interruption $" value={f.bi_value ?? ''} onChange={(v) => set('bi_value', v)} type="number" />
              <Field label="Replacement cost $" value={f.replacement_cost ?? ''} onChange={(v) => set('replacement_cost', v)} type="number" />
              <Field label="Insured value $" value={f.insured_value ?? ''} onChange={(v) => set('insured_value', v)} type="number" />
            </div>
            <p className="text-[10px] text-zinc-600 mt-1">Insured-value vs replacement-cost drives the insurance-to-value (ITV) check.</p>
          </div>
          <div>
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold mb-2">Valuation & policy structure</div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              <div>
                <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Valuation basis</label>
                <select value={f.valuation_basis ?? ''} onChange={(e) => set('valuation_basis', e.target.value)} className={inputCls}>
                  <option value="">—</option>
                  <option value="RCV">Replacement cost</option>
                  <option value="ACV">Actual cash value</option>
                </select>
              </div>
              <Field label="Coinsurance %" value={f.coinsurance_pct ?? ''} onChange={(v) => set('coinsurance_pct', v)} type="number" placeholder="90" />
              <div>
                <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Ordinance & law</label>
                <select value={f.ordinance_law ?? ''} onChange={(e) => set('ordinance_law', e.target.value)} className={inputCls}>
                  <option value="">—</option>
                  <option value="none">None</option>
                  <option value="A">Coverage A</option>
                  <option value="B">Coverage B</option>
                  <option value="C">Coverage C</option>
                  <option value="ABC">A + B + C</option>
                </select>
              </div>
              <Field label="BI period (months)" value={f.bi_months ?? ''} onChange={(v) => set('bi_months', v)} type="number" />
              <Field label="AOP deductible $" value={f.aop_deductible ?? ''} onChange={(v) => set('aop_deductible', v)} type="number" />
              <Field label="Wind ded %" value={f.wind_deductible_pct ?? ''} onChange={(v) => set('wind_deductible_pct', v)} type="number" />
              <Field label="Named-storm ded %" value={f.named_storm_deductible_pct ?? ''} onChange={(v) => set('named_storm_deductible_pct', v)} type="number" />
              <Field label="Quake ded %" value={f.quake_deductible_pct ?? ''} onChange={(v) => set('quake_deductible_pct', v)} type="number" />
            </div>
            <label className="inline-flex items-center gap-2 mt-2 text-sm text-zinc-300">
              <input type="checkbox" checked={blanket} onChange={(e) => setBlanket(e.target.checked)} className="rounded border-zinc-600 bg-zinc-800 text-emerald-500 focus:ring-emerald-500" />
              Blanket limit (vs scheduled)
            </label>
            <p className="text-[10px] text-zinc-600 mt-1">Deductibles + valuation feed the net PML and the risk score; coinsurance % drives the shortfall check.</p>
          </div>
          <div>
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold mb-2">Occupancy hazards</div>
            <div className="flex flex-wrap gap-x-5 gap-y-2 text-sm text-zinc-300">
              <label className="inline-flex items-center gap-2">
                <input type="checkbox" checked={cooking} onChange={(e) => setCooking(e.target.checked)} className="rounded border-zinc-600 bg-zinc-800 text-emerald-500 focus:ring-emerald-500" />
                Commercial cooking (NFPA-96)
              </label>
              <label className="inline-flex items-center gap-2">
                <input type="checkbox" checked={hotWork} onChange={(e) => setHotWork(e.target.checked)} className="rounded border-zinc-600 bg-zinc-800 text-emerald-500 focus:ring-emerald-500" />
                Hot work
              </label>
              <label className="inline-flex items-center gap-2">
                <input type="checkbox" checked={hazmat} onChange={(e) => setHazmat(e.target.checked)} className="rounded border-zinc-600 bg-zinc-800 text-emerald-500 focus:ring-emerald-500" />
                Hazardous materials stored
              </label>
            </div>
          </div>
          <Field label="Note" value={f.note ?? ''} onChange={(v) => set('note', v)} placeholder="optional" />
          <button type="submit" disabled={saving} className="bg-zinc-100 text-zinc-900 text-sm font-medium rounded-lg px-4 py-1.5 hover:bg-white disabled:opacity-50 transition-colors">
            {saving ? 'Saving…' : building ? 'Save building' : 'Add building'}
          </button>
        </form>
      </div>
    </div>
  )
}
