import type { ReactNode } from 'react'
import { Trash2 } from 'lucide-react'
import { useCappeMe } from '../../../hooks/useCappeMe'
import { dLabel, inputCls } from './styles'
import { arr, str } from './valueHelpers'

export function usePremium(): boolean {
  const { account } = useCappeMe()
  return account?.plan === 'pro' || account?.plan === 'business'
}

export function PremiumLock({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-amber-700/40 bg-amber-500/[0.06] px-3 py-2.5 text-xs text-amber-300/90">
      <span className="font-medium">Premium feature.</span> {children}
    </div>
  )
}

export function DSelect({ label, value, options, onChange }: {
  label: string; value: string; options: [string, string][]; onChange: (v: string) => void
}) {
  return (
    <label className="block">
      <span className={dLabel}>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} className={`${inputCls} py-1.5`}>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  )
}

export function DNum({ label, value, onChange, min, max, step }: {
  label: string; value: number; onChange: (v: number) => void; min: number; max: number; step?: number
}) {
  return (
    <label className="block">
      <span className={dLabel}>{label}</span>
      <input type="number" value={value} min={min} max={max} step={step ?? 1}
        onChange={(e) => onChange(Number(e.target.value))} className={`${inputCls} py-1.5`} />
    </label>
  )
}

export function DCheck({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 text-xs text-zinc-300">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)}
        className="h-3.5 w-3.5 rounded border-zinc-600 bg-zinc-900 text-emerald-500" />
      {label}
    </label>
  )
}

export function DColor({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-xs text-zinc-400">{label}</span>
      <div className="flex items-center gap-1">
        <input type="color" value={value || '#000000'} onChange={(e) => onChange(e.target.value)}
          className="h-7 w-10 cursor-pointer rounded border border-zinc-700 bg-transparent" />
        {value && <button type="button" onClick={() => onChange('')} className="text-zinc-500 hover:text-red-400" title="Clear"><Trash2 className="h-3.5 w-3.5" /></button>}
      </div>
    </div>
  )
}

export function GradientPicker({ value, onChange }: { value: Record<string, unknown>; onChange: (g: Record<string, unknown>) => void }) {
  const stops = arr(value.stops).map(str)
  const s0 = stops[0] || '#10b981', s1 = stops[1] || '#a3e635'
  const setStop = (i: number, v: string) => { const next = [s0, s1]; next[i] = v; onChange({ ...value, stops: next }) }
  return (
    <div className="space-y-1.5">
      <div className="grid grid-cols-2 gap-2">
        <label className="block"><span className={dLabel}>From</span>
          <input type="color" value={s0} onChange={(e) => setStop(0, e.target.value)} className="h-8 w-full cursor-pointer rounded border border-zinc-700 bg-transparent" /></label>
        <label className="block"><span className={dLabel}>To</span>
          <input type="color" value={s1} onChange={(e) => setStop(1, e.target.value)} className="h-8 w-full cursor-pointer rounded border border-zinc-700 bg-transparent" /></label>
      </div>
      <DNum label="Angle (°)" value={Number(value.angle) || 135} min={0} max={360} step={5} onChange={(v) => onChange({ ...value, angle: v })} />
    </div>
  )
}
