import { Select } from '../../ui'
import { DEFAULT_MAX_SHIFT_HOURS, DEFAULT_MIN_SHIFT_HOURS, type AutopilotPolicyDraft } from './autopilotPolicy'

const inputCls = 'mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-1.5 text-sm text-zinc-200 outline-none focus:border-emerald-500'

export default function AutopilotPolicyFields({ value, onChange }: {
  value: AutopilotPolicyDraft
  onChange(value: AutopilotPolicyDraft): void
}) {
  const change = (patch: Partial<AutopilotPolicyDraft>) => onChange({ ...value, ...patch })
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <Select
        label="Weather sensitivity"
        options={[
          { value: 'none', label: 'None' },
          { value: 'rain_hurts', label: 'Rain hurts demand' },
          { value: 'rain_helps', label: 'Rain helps demand' },
        ]}
        value={value.weatherSensitivity}
        onChange={(event) => change({ weatherSensitivity: event.target.value as AutopilotPolicyDraft['weatherSensitivity'] })}
      />
      <label className="text-xs text-zinc-400">Minimum floor staff
        <input type="number" aria-label="Minimum floor staff" min={0} max={20} step={1} value={value.minFloorStaff} onChange={(event) => change({ minFloorStaff: event.target.value })} className={inputCls} />
        <span className="mt-1 block text-[10px] text-zinc-600">A required leader is planned separately.</span>
      </label>
      <label className="text-xs text-zinc-400">Target labor % <span className="text-zinc-600">optional</span>
        <input type="number" aria-label="Target labor %" min={1} max={90} step="0.5" value={value.targetLaborPct} onChange={(event) => change({ targetLaborPct: event.target.value })} className={inputCls} placeholder="28" />
        <span className="mt-1 block text-[10px] text-zinc-600">Used when sales and pay data are available.</span>
      </label>
      <label className="text-xs text-zinc-400">Minimum shift hours <span className="text-zinc-600">optional</span>
        <input type="number" min={2} max={12} step="0.5" value={value.shiftMinHours} onChange={(event) => change({ shiftMinHours: event.target.value })} className={inputCls} placeholder={String(DEFAULT_MIN_SHIFT_HOURS)} />
      </label>
      <label className="text-xs text-zinc-400">Maximum shift hours <span className="text-zinc-600">optional</span>
        <input type="number" min={2} max={12} step="0.5" value={value.shiftMaxHours} onChange={(event) => change({ shiftMaxHours: event.target.value })} className={inputCls} placeholder={String(DEFAULT_MAX_SHIFT_HOURS)} />
      </label>
    </div>
  )
}
