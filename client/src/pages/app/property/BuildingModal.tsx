import { useState, type FormEvent } from 'react'
import { X } from 'lucide-react'
import { createBuilding, updateBuilding } from '../../../api/property/property'
import type { PropertySov, PropertyBuilding, BuildingPayload, ConstructionType } from '../../../types/property'
import { CONSTRUCTION_LABEL } from '../../../types/property'
import { inputCls } from './shared'

const CONSTRUCTION_OPTS: ConstructionType[] = ['fire_resistive', 'modified_fire_resistive', 'masonry_non_combustible', 'non_combustible', 'joisted_masonry', 'frame']

const NUM_FIELDS = ['year_built', 'sq_ft', 'stories', 'roof_year', 'building_value', 'contents_value', 'bi_value', 'replacement_cost', 'insured_value', 'coinsurance_pct', 'bi_months', 'aop_deductible', 'wind_deductible_pct', 'named_storm_deductible_pct', 'quake_deductible_pct', 'wiring_year'] as const

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

export function BuildingModal({ building, onClose, onSaved }: { building: PropertyBuilding | null; onClose: () => void; onSaved: (s: PropertySov) => void }) {
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
