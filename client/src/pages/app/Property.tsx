import { useState, useEffect, type FormEvent } from 'react'
import { Building2, Plus, Loader2, AlertCircle, Pencil, Trash2, X } from 'lucide-react'
import { Card } from '../../components/ui'
import { fetchPropertySov, createBuilding, updateBuilding, deleteBuilding } from '../../api/property'
import type { PropertySov, PropertyBuilding, BuildingPayload, ConstructionType } from '../../types/property'
import { CONSTRUCTION_LABEL, COPE_TONE, PERIL_TONE } from '../../types/property'

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

export default function Property() {
  const [data, setData] = useState<PropertySov | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [editing, setEditing] = useState<PropertyBuilding | null>(null)
  const [showForm, setShowForm] = useState(false)

  const load = () => {
    setLoading(true); setError(false)
    fetchPropertySov().then(setData).catch(() => setError(true)).finally(() => setLoading(false))
  }
  useEffect(load, [])

  function openAdd() { setEditing(null); setShowForm(true) }
  function openEdit(b: PropertyBuilding) { setEditing(b); setShowForm(true) }

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

  const { rollup: r, buildings } = data
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
        <button onClick={openAdd} className="inline-flex items-center gap-1.5 text-sm text-zinc-200 px-3 py-1.5 rounded-lg border border-zinc-700 hover:border-zinc-500 transition-colors">
          <Plus className="h-4 w-4" /> Add building
        </button>
      </div>

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
                <th className="px-4 py-2.5">Building</th>
                <th className="px-4 py-2.5">Construction</th>
                <th className="px-4 py-2.5 text-right">TIV</th>
                <th className="px-4 py-2.5 text-center">COPE</th>
                <th className="px-4 py-2.5 text-right">ITV</th>
                <th className="px-4 py-2.5 text-center">Cat</th>
                <th className="px-4 py-2.5"></th>
              </tr>
            </thead>
            <tbody>
              {buildings.map((b) => {
                const worst = WORST_PERIL(b)
                const itv = b.itv_ratio != null ? Math.round(b.itv_ratio * 100) : null
                return (
                  <tr key={b.id} className="border-b border-zinc-800/30 last:border-0 hover:bg-zinc-900/30">
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
                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      <button onClick={() => openEdit(b)} className="text-zinc-500 hover:text-zinc-200 mr-2"><Pencil className="h-3.5 w-3.5 inline" /></button>
                      <button onClick={() => onDelete(b)} className="text-zinc-600 hover:text-red-400"><Trash2 className="h-3.5 w-3.5 inline" /></button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </Card>
      )}

      {showForm && (
        <BuildingModal building={editing} onClose={() => setShowForm(false)} onSaved={(sov) => { setData(sov); setShowForm(false) }} />
      )}
    </div>
  )
}

const NUM_FIELDS = ['year_built', 'sq_ft', 'stories', 'roof_year', 'building_value', 'contents_value', 'bi_value', 'replacement_cost', 'insured_value'] as const

function BuildingModal({ building, onClose, onSaved }: { building: PropertyBuilding | null; onClose: () => void; onSaved: (s: PropertySov) => void }) {
  const [f, setF] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {}
    const keys = ['name', 'address', 'city', 'state', 'zipcode', 'occupancy', 'construction_type', 'protection_class', 'note', ...NUM_FIELDS]
    keys.forEach((k) => { const v = building?.[k as keyof PropertyBuilding]; init[k] = v == null ? '' : String(v) })
    return init
  })
  const [sprinklered, setSprinklered] = useState(building?.sprinklered ?? false)
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
    }
    try {
      const sov = building ? await updateBuilding(building.id, payload) : await createBuilding(payload)
      onSaved(sov)
    } catch { /* keep open */ } finally { setSaving(false) }
  }

  const Lbl = ({ k, label, ph, type = 'text' }: { k: string; label: string; ph?: string; type?: string }) => (
    <div>
      <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">{label}</label>
      <input type={type} value={f[k] ?? ''} onChange={(e) => set(k, e.target.value)} className={inputCls} placeholder={ph} />
    </div>
  )

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
              <Lbl k="name" label="Name" ph="HQ" />
              <Lbl k="address" label="Address" />
              <Lbl k="occupancy" label="Occupancy" ph="office" />
              <Lbl k="city" label="City" />
              <Lbl k="state" label="State" ph="CA" />
              <Lbl k="zipcode" label="ZIP" />
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
              <Lbl k="year_built" label="Year built" type="number" />
              <Lbl k="sq_ft" label="Sq ft" type="number" />
              <Lbl k="stories" label="Stories" type="number" />
              <Lbl k="roof_year" label="Roof year" type="number" />
              <Lbl k="protection_class" label="ISO PPC (1-10)" />
            </div>
            <label className="inline-flex items-center gap-2 mt-2 text-sm text-zinc-300">
              <input type="checkbox" checked={sprinklered} onChange={(e) => setSprinklered(e.target.checked)} className="rounded border-zinc-600 bg-zinc-800 text-emerald-500 focus:ring-emerald-500" />
              Sprinklered
            </label>
          </div>
          <div>
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold mb-2">Values</div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              <Lbl k="building_value" label="Building $" type="number" />
              <Lbl k="contents_value" label="Contents $" type="number" />
              <Lbl k="bi_value" label="Business interruption $" type="number" />
              <Lbl k="replacement_cost" label="Replacement cost $" type="number" />
              <Lbl k="insured_value" label="Insured value $" type="number" />
            </div>
            <p className="text-[10px] text-zinc-600 mt-1">Insured-value vs replacement-cost drives the insurance-to-value (ITV) check.</p>
          </div>
          <button type="submit" disabled={saving} className="bg-zinc-100 text-zinc-900 text-sm font-medium rounded-lg px-4 py-1.5 hover:bg-white disabled:opacity-50 transition-colors">
            {saving ? 'Saving…' : building ? 'Save building' : 'Add building'}
          </button>
        </form>
      </div>
    </div>
  )
}
