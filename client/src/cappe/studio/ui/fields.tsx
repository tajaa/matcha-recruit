import { useState } from 'react'
import type { Units } from '../model/types'
import { PT_PER, parse, show } from '../model/units'

const BOX = 'h-7 rounded-md border border-zinc-800 bg-zinc-900 text-xs text-zinc-100 outline-none focus-within:border-emerald-500'

/** A length shown in the document's units. Type any unit ("3in", "12p6",
 *  "40mm") or a sum; drag the label to scrub; ↑/↓ step it (Shift: ten). */
export function LengthField({ label, short, value, onChange, units, min = -Infinity, max = Infinity, mixed }: {
  label: string; short?: string; value: number; onChange: (pt: number) => void; units: Units
  min?: number; max?: number; mixed?: boolean
}) {
  const [text, setText] = useState<string | null>(null)
  const clamp = (v: number) => Math.max(min, Math.min(max, v))
  const step = units === 'pt' || units === 'px' ? PT_PER[units] : units === 'pc' ? 1 : PT_PER[units] / (units === 'in' ? 16 : 1)
  const commit = (raw: string) => {
    const v = parse(raw, units)
    if (v !== null) onChange(clamp(v))
    setText(null)
  }
  const scrub = (e: React.PointerEvent) => {
    e.preventDefault()
    const x0 = e.clientX, v0 = value
    const el = e.currentTarget as HTMLElement
    el.setPointerCapture(e.pointerId)
    const move = (ev: PointerEvent) => onChange(clamp(v0 + Math.round((ev.clientX - x0) / 2) * step * (ev.shiftKey ? 10 : 1)))
    const up = () => { el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', up) }
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerup', up)
  }
  return (
    <div className={`${BOX} flex min-w-0 items-center`}>
      <span onPointerDown={scrub} title={`${label}: drag to change`}
        className="flex h-full w-6 shrink-0 cursor-ew-resize select-none items-center justify-center text-[10px] text-zinc-500">
        {short ?? label[0]}
      </span>
      <input aria-label={label} value={text ?? (mixed ? '' : show(value, units))} placeholder={mixed ? 'Mixed' : undefined}
        onChange={(e) => setText(e.target.value)} onFocus={(e) => e.target.select()} onBlur={(e) => commit(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') { e.preventDefault(); commit((e.target as HTMLInputElement).value) }
          else if (e.key === 'Escape') { setText(null); (e.target as HTMLInputElement).blur() }
          else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
            e.preventDefault()
            onChange(clamp(value + (e.key === 'ArrowUp' ? 1 : -1) * step * (e.shiftKey ? 10 : 1)))
            setText(null)
          }
        }}
        className="h-full min-w-0 flex-1 bg-transparent pr-1 text-right tabular-nums outline-none" />
      <span className="pr-1.5 text-[10px] text-zinc-500">{units}</span>
    </div>
  )
}

/** A labelled field in a panel row. */
export function Labeled({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block min-w-0">
      <span className="mb-1 block text-[10px] uppercase tracking-wider text-zinc-500">{label}</span>
      {children}
    </label>
  )
}
