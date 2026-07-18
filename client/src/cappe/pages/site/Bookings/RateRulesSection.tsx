import type { Dispatch, SetStateAction } from 'react'
import { Loader2, Trash2, Save } from 'lucide-react'
import { WEEKDAYS } from '../../../components/SurfaceShell'
import type { CappeBookingType, CappeRateRule } from '../../../types'
import { hhmm, inputCls } from './constants'

interface RateRulesSectionProps {
  rules: CappeRateRule[]
  setRules: Dispatch<SetStateAction<CappeRateRule[]>>
  setRule: (i: number, patch: Partial<CappeRateRule>) => void
  types: CappeBookingType[]
  hasHourly: boolean
  addRule: () => void
  saveRules: () => void
  savingRules: boolean
}

export function RateRulesSection({
  rules, setRules, setRule, types, hasHourly, addRule, saveRules, savingRules,
}: RateRulesSectionProps) {
  return (
    <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-5 shadow-sm">
      <h2 className="text-sm font-semibold text-zinc-100">Time-based pricing</h2>
      <p className="mb-3 mt-1 text-xs text-zinc-500">
        Charge more for certain hours or days on <span className="text-zinc-300">per-hour</span> types — e.g. after 8pm at 2×.
        {!hasHourly && ' Add a per-hour appointment type above to use these.'}
      </p>
      <div className="space-y-2">
        {rules.map((r, i) => (
          <div key={r.id} className="flex flex-wrap items-center gap-2">
            <input value={r.label} onChange={(e) => setRule(i, { label: e.target.value })} placeholder="Label (e.g. After hours)" className={`w-40 ${inputCls}`} />
            <select value={r.weekday ?? ''} onChange={(e) => setRule(i, { weekday: e.target.value === '' ? null : parseInt(e.target.value, 10) })} className={inputCls}>
              <option value="">Every day</option>
              {WEEKDAYS.map((d, idx) => <option key={idx} value={idx}>{d}</option>)}
            </select>
            <input type="time" value={hhmm(r.start_time)} onChange={(e) => setRule(i, { start_time: e.target.value })} className={inputCls} />
            <span className="text-zinc-400">to</span>
            <input type="time" value={hhmm(r.end_time)} onChange={(e) => setRule(i, { end_time: e.target.value })} className={inputCls} />
            <div className="flex items-center gap-1">
              <input type="number" min="0" step="0.1" value={r.multiplier} onChange={(e) => setRule(i, { multiplier: parseFloat(e.target.value) || 0 })} className={`w-16 ${inputCls}`} />
              <span className="text-sm text-zinc-400">×</span>
            </div>
            <select value={r.booking_type_id ?? ''} onChange={(e) => setRule(i, { booking_type_id: e.target.value || null })} className={inputCls}>
              <option value="">All types</option>
              {types.filter((t) => t.pricing_mode === 'hourly').map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
            <button type="button" onClick={() => setRules((rl) => rl.filter((_, idx) => idx !== i))} className="text-zinc-400 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
          </div>
        ))}
      </div>
      <div className="mt-3 flex gap-2">
        <button onClick={addRule} className="text-xs font-medium text-emerald-400 hover:underline">+ Add rule</button>
        <button onClick={saveRules} disabled={savingRules} className="ml-auto flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60">
          {savingRules ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Save rules
        </button>
      </div>
    </section>
  )
}
