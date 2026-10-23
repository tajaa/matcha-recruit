import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ChevronDown, Pipette, Plus, Trash2 } from 'lucide-react'
import type { Paint, PaintKind, Stop } from '../design/types'
import { alphaOf, hexToHsva, hsvaToHex, readColour, swatchCss, withAlpha, type Hsva } from './color'
import { evalSum } from './sum'

/** The workspace's controls, as a design tool has them: numbers you drag a
 *  label to scrub (or type sums into), colours with a picker, fills with
 *  gradients, buttons in a row. Every control says what it is to a screen
 *  reader. */

const BOX = 'h-7 rounded-md border border-zinc-800 bg-zinc-900 text-xs text-zinc-100 outline-none focus:border-emerald-500'

/** A titled part of the inspector. */
export function Section({ title, children, right }: { title: string; children: ReactNode; right?: ReactNode }) {
  return (
    <section aria-label={title} className="border-b border-zinc-800 px-4 py-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">{title}</h3>
        {right}
      </div>
      <div className="space-y-2">{children}</div>
    </section>
  )
}

export function Row({ children, cols = 2 }: { children: ReactNode; cols?: 2 | 3 | 4 }) {
  return <div className={`grid gap-2 [&>*]:min-w-0 ${cols === 4 ? 'grid-cols-4' : cols === 3 ? 'grid-cols-3' : 'grid-cols-2'}`}>{children}</div>
}

/** A square button with an icon, pressed when `active`. */
export function IconBtn({ title, onClick, active, disabled, children }: {
  title: string; onClick: () => void; active?: boolean; disabled?: boolean; children: ReactNode
}) {
  return (
    <button type="button" title={title} aria-label={title} aria-pressed={active} disabled={disabled} onClick={onClick}
      className={`inline-flex h-7 min-w-[28px] items-center justify-center rounded-md px-1.5 text-xs disabled:opacity-30 ${active
        ? 'bg-emerald-500/20 text-emerald-300' : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100'}`}>
      {children}
    </button>
  )
}

/** Buttons, one of them on. */
export function Seg<T extends string>({ value, options, onChange, label }: {
  value: T; options: { key: T; label: string; icon?: ReactNode }[]; onChange: (v: T) => void; label: string
}) {
  return (
    <div className="flex rounded-md border border-zinc-800 p-0.5" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.key} type="button" title={o.label} aria-pressed={value === o.key} onClick={() => onChange(o.key)}
          className={`flex h-6 flex-1 items-center justify-center rounded px-1 text-[11px] ${value === o.key ? 'bg-zinc-700 text-zinc-50' : 'text-zinc-400 hover:text-zinc-100'}`}>
          {o.icon ?? o.label}{o.icon && <span className="sr-only">{o.label}</span>}
        </button>
      ))}
    </div>
  )
}

export function Select<T extends string>({ value, options, onChange, label }: {
  value: T; options: { key: T; label: string }[]; onChange: (v: T) => void; label: string
}) {
  return (
    <label className="relative block">
      <span className="sr-only">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value as T)} title={label}
        className={`${BOX} w-full appearance-none pl-2 pr-6`}>
        {options.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
      </select>
      <ChevronDown className="pointer-events-none absolute right-1.5 top-1.5 h-4 w-4 text-zinc-500" />
    </label>
  )
}

const fmt = (v: number, places: number) => String(Math.round(v * 10 ** places) / 10 ** places)

/** A number: drag its label left and right to scrub it (Shift: ten times
 *  faster), type a value or a sum, ↑/↓ to step it. */
export function NumberField({ label, short, value, onChange, min = -Infinity, max = Infinity, step = 1, places = 1, unit, mixed, blank }: {
  label: string; short?: string; value: number; onChange: (v: number) => void
  min?: number; max?: number; step?: number; places?: number; unit?: string
  /** Several things selected with different values. */
  mixed?: boolean
  /** Shown instead of the number while it is unset ("Auto"). */
  blank?: string
}) {
  const [text, setText] = useState<string | null>(null)
  const clamp = (v: number) => Math.max(min, Math.min(max, v))
  // Only words typed are applied: a field left as it was changes nothing (no
  // undo step, no new page).
  const commit = (raw: string | null) => {
    const v = raw === null ? null : evalSum(raw)
    if (v !== null) {
      const next = clamp(Number(fmt(v, places)))
      if (mixed || blank || next !== value) onChange(next)
    }
    setText(null)
  }
  const scrub = (e: React.PointerEvent) => {
    e.preventDefault()
    const x0 = e.clientX, v0 = value
    const el = e.currentTarget as HTMLElement
    el.setPointerCapture(e.pointerId)
    const move = (ev: PointerEvent) => onChange(clamp(Number(fmt(v0 + Math.round((ev.clientX - x0) / 2) * step * (ev.shiftKey ? 10 : 1), places))))
    const up = () => { el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', up) }
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerup', up)
  }
  return (
    <div className={`${BOX} flex min-w-0 items-center`}>
      <span onPointerDown={scrub} title={`${label}: drag to change`} className="flex h-full w-6 shrink-0 cursor-ew-resize select-none items-center justify-center text-[10px] text-zinc-500">
        {short ?? label[0]}
      </span>
      <input aria-label={label} value={text ?? (mixed || blank ? '' : fmt(value, places))} placeholder={mixed ? 'Mixed' : blank}
        onChange={(e) => setText(e.target.value)} onFocus={(e) => e.target.select()}
        onBlur={() => commit(text)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') { e.preventDefault(); commit(text) }
          else if (e.key === 'Escape') { setText(null); (e.target as HTMLInputElement).blur() }
          else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
            e.preventDefault()
            onChange(clamp(Number(fmt(value + (e.key === 'ArrowUp' ? 1 : -1) * step * (e.shiftKey ? 10 : 1), places))))
            setText(null)
          }
        }}
        className="h-full min-w-0 flex-1 bg-transparent pr-1 text-right tabular-nums outline-none" />
      {unit && <span className="pr-1.5 text-[10px] text-zinc-500">{unit}</span>}
    </div>
  )
}

/** A range with its number beside it. */
export function Slider({ label, value, onChange, min, max, step = 1, unit = '' }: {
  label: string; value: number; onChange: (v: number) => void; min: number; max: number; step?: number; unit?: string
}) {
  return (
    <label className="flex items-center gap-2 text-xs text-zinc-400">
      <span className="w-16 shrink-0">{label}</span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))}
        className="h-1 min-w-0 flex-1 accent-emerald-500" aria-label={label} />
      <span className="w-10 text-right tabular-nums text-zinc-300">{value}{unit}</span>
    </label>
  )
}

// ── colour ───────────────────────────────────────────────────────────────────

const RECENT: string[] = []
const PRESETS = ['#ffffff', '#000000', '#111111', '#f4efe6', '#e11d48', '#f97316', '#facc15', '#10b981', '#0ea5e9', '#6366f1', '#a855f7', '#78716c']

type EyeDropperCtor = new () => { open: () => Promise<{ sRGBHex: string }> }

/** A popover kept on screen, placed by its anchor when opened, closed by a
 *  click outside it or Escape. */
function usePopover(anchor: React.RefObject<HTMLElement | null>) {
  const panel = useRef<HTMLDivElement>(null)
  const [at, setAt] = useState<{ left: number; top: number } | null>(null)
  const open = at !== null
  const toggle = () => {
    if (open || !anchor.current) { setAt(null); return }
    const r = anchor.current.getBoundingClientRect()
    const w = 248, h = 330
    setAt({ left: Math.max(8, Math.min(window.innerWidth - w - 8, r.right - w)), top: r.bottom + h > window.innerHeight ? Math.max(8, r.top - h - 4) : r.bottom + 4 })
  }
  useEffect(() => {
    if (!open) return
    const down = (e: PointerEvent) => {
      if (panel.current?.contains(e.target as Node) || anchor.current?.contains(e.target as Node)) return
      setAt(null)
    }
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') setAt(null) }
    window.addEventListener('pointerdown', down, true)
    window.addEventListener('keydown', key)
    return () => { window.removeEventListener('pointerdown', down, true); window.removeEventListener('keydown', key) }
  }, [open, anchor])
  return { panel, at, toggle }
}

/** The picker: a square for strength and brightness, hue and opacity bars,
 *  a hex box, the magazine's accent, recent and preset colours, and the
 *  screen dropper where the browser has one. */
export function ColorPicker({ value, onChange, accent }: { value: string; onChange: (c: string) => void; accent: string }) {
  const [hsva, setHsva] = useState<Hsva>(() => hexToHsva(value === 'accent' ? accent : value))
  const [hex, setHex] = useState<string | null>(null)
  // The colour last seen from outside: a new one (undo, another layer) moves
  // the picker; its own changes keep their hue even through grey.
  const [seen, setSeen] = useState(value)
  if (value !== seen) {
    setSeen(value)
    const next = hexToHsva(value === 'accent' ? accent : value)
    if (hsvaToHex(next) !== hsvaToHex(hsva)) setHsva(next)
  }
  const set = (next: Hsva) => { setHsva(next); const c = hsvaToHex(next); setSeen(c); onChange(c) }
  const square = (e: React.PointerEvent<HTMLDivElement>) => {
    const el = e.currentTarget, r = el.getBoundingClientRect()
    el.setPointerCapture(e.pointerId)
    const at = (ev: { clientX: number; clientY: number }) =>
      set({ ...hsva, s: Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width)), v: Math.max(0, Math.min(1, 1 - (ev.clientY - r.top) / r.height)) })
    at(e)
    const move = (ev: PointerEvent) => at(ev)
    const up = () => { el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', up) }
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerup', up)
  }
  const solid = hsvaToHex({ ...hsva, a: 1 })
  const dropper = (window as unknown as { EyeDropper?: EyeDropperCtor }).EyeDropper
  const pick = (c: string) => { onChange(c); if (c !== 'accent' && !RECENT.includes(c)) { RECENT.unshift(c); RECENT.splice(8) } }
  return (
    <div className="space-y-2">
      <div role="slider" aria-label="Strength and brightness" aria-valuenow={Math.round(hsva.s * 100)} tabIndex={0} onPointerDown={square}
        className="relative h-32 cursor-crosshair rounded-md"
        style={{ background: `linear-gradient(to top,#000,transparent),linear-gradient(to right,#fff,hsl(${hsva.h} 100% 50%))` }}>
        <span className="pointer-events-none absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow"
          style={{ left: `${hsva.s * 100}%`, top: `${(1 - hsva.v) * 100}%`, background: solid }} />
      </div>
      <input type="range" min={0} max={360} value={Math.round(hsva.h)} aria-label="Hue" onChange={(e) => set({ ...hsva, h: Number(e.target.value) })}
        className="mze-hue h-2 w-full cursor-pointer appearance-none rounded"
        style={{ background: 'linear-gradient(to right,#f00,#ff0,#0f0,#0ff,#00f,#f0f,#f00)' }} />
      <input type="range" min={0} max={100} value={Math.round(hsva.a * 100)} aria-label="Opacity" onChange={(e) => set({ ...hsva, a: Number(e.target.value) / 100 })}
        className="h-2 w-full cursor-pointer appearance-none rounded"
        style={{ background: `linear-gradient(to right,transparent,${solid}),repeating-conic-gradient(#3f3f46 0 25%,#27272a 0 50%) 0 0/8px 8px` }} />
      <div className="flex items-center gap-1.5">
        <input aria-label="Colour, as hex" value={hex ?? (value === 'accent' ? 'accent' : value)} onChange={(e) => setHex(e.target.value)}
          onBlur={(e) => { const c = readColour(e.target.value); if (c) pick(c); setHex(null) }}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); (e.target as HTMLInputElement).blur() } }}
          className={`${BOX} min-w-0 flex-1 px-2 font-mono`} />
        <span className="w-9 text-right text-[11px] tabular-nums text-zinc-400">{Math.round(alphaOf(value === 'accent' ? accent : value) * 100)}%</span>
        {dropper && (
          <IconBtn title="Pick a colour from the screen" onClick={() => {
            new dropper().open().then((r) => pick(r.sRGBHex.toLowerCase())).catch(() => { /* cancelled */ })
          }}><Pipette className="h-3.5 w-3.5" /></IconBtn>
        )}
      </div>
      <div className="grid grid-cols-8 gap-1">
        <button type="button" title="The magazine's accent" aria-label="The magazine's accent" onClick={() => pick('accent')}
          className={`h-5 rounded border ${value === 'accent' ? 'border-white' : 'border-zinc-700'}`} style={{ background: accent }} />
        {[...RECENT, ...PRESETS.filter((p) => !RECENT.includes(p))].slice(0, 15).map((c) => (
          <button key={c} type="button" title={c} aria-label={c} onClick={() => pick(c)}
            className={`h-5 rounded border ${value === c ? 'border-white' : 'border-zinc-700'}`} style={{ background: c }} />
        ))}
      </div>
    </div>
  )
}

/** A colour: its swatch and value; the picker opens under it. */
export function ColorField({ label, value, onChange, accent = '#10b981', auto }: {
  label: string; value: string; onChange: (c: string) => void; accent?: string
  /** What '' means ("Page ink"): shown for it, and offered to go back to. */
  auto?: string
}) {
  const btn = useRef<HTMLButtonElement>(null)
  const { panel, at, toggle } = usePopover(btn)
  const open = at !== null
  const css = swatchCss(value, accent)
  return (
    <>
      <button ref={btn} type="button" onClick={toggle} aria-expanded={open} aria-label={`${label}: ${value || auto || ''}`}
        className={`${BOX} flex w-full items-center gap-2 px-1.5`}>
        <span className="h-4 w-4 shrink-0 rounded border border-zinc-600"
          style={{ background: `linear-gradient(${css},${css}),repeating-conic-gradient(#71717a 0 25%,#d4d4d8 0 50%) 0 0/6px 6px` }} />
        <span className={`truncate text-[11px] text-zinc-300 ${value ? 'font-mono' : ''}`}>{value === 'accent' ? 'Accent' : value || auto}</span>
      </button>
      {at && (
        <div ref={panel} className="fixed z-50 w-[248px] rounded-lg border border-zinc-700 bg-zinc-900 p-2.5 shadow-2xl" style={at} role="dialog" aria-label={label}>
          {auto !== undefined && (
            <button type="button" aria-pressed={!value} onClick={() => onChange('')}
              className={`mb-2 w-full rounded-md border px-2 py-1 text-left text-[11px] ${value ? 'border-zinc-800 text-zinc-300 hover:border-zinc-600' : 'border-emerald-500 text-emerald-300'}`}>
              {auto}
            </button>
          )}
          <ColorPicker value={value || '#1a1a1a'} onChange={onChange} accent={accent} />
        </div>
      )}
    </>
  )
}

// ── fills ────────────────────────────────────────────────────────────────────

const PAINT_KINDS: { key: PaintKind; label: string }[] = [
  { key: 'none', label: 'None' }, { key: 'solid', label: 'Solid' }, { key: 'linear', label: 'Linear' }, { key: 'radial', label: 'Radial' },
]

const stopsCss = (stops: Stop[], accent: string) => stops.map((s) => `${swatchCss(s.color, accent)} ${s.at}%`).join(',')

/** A fill: none, one colour, or a gradient whose stops are dragged along a
 *  bar (click the bar to add one). */
export function PaintField({ value, onChange, accent = '#10b981' }: { value: Paint; onChange: (p: Paint) => void; accent?: string }) {
  const [stop, setStop] = useState(0)
  const bar = useRef<HTMLDivElement>(null)
  const setKind = (kind: PaintKind) => {
    if (kind === 'none' || kind === 'solid') onChange({ ...value, kind, stops: [] })
    else onChange({ ...value, kind, stops: value.stops.length >= 2 ? value.stops : [{ color: value.color, at: 0 }, { color: withAlpha(value.color === 'accent' ? '#000000' : value.color, 0), at: 100 }] })
  }
  /** The stops in order, the one changed still selected where it lands. */
  const settle = (stops: Stop[], moved: Stop) => {
    const sorted = [...stops].sort((a, b) => a.at - b.at)
    onChange({ ...value, stops: sorted })
    setStop(sorted.indexOf(moved))
  }
  const setStopAt = (i: number, patch: Partial<Stop>) => {
    const moved = { ...value.stops[i], ...patch }
    settle(value.stops.map((s, j) => (j === i ? moved : s)), moved)
  }
  const drag = (i: number) => (e: React.PointerEvent) => {
    e.stopPropagation()
    setStop(i)
    const r = bar.current!.getBoundingClientRect(), el = e.currentTarget as HTMLElement
    el.setPointerCapture(e.pointerId)
    // The stops as dragged so far: `value` is the fill from before the drag.
    let stops = value.stops
    const move = (ev: PointerEvent) => {
      const at = Math.round(Math.max(0, Math.min(100, ((ev.clientX - r.left) / r.width) * 100)))
      stops = stops.map((s, j) => (j === i ? { ...s, at } : s))
      onChange({ ...value, stops })
    }
    const up = () => {
      el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', up)
      if (stops !== value.stops) settle(stops, stops[i])
    }
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerup', up)
  }
  const gradient = value.kind === 'linear' || value.kind === 'radial'
  const current = value.stops[Math.min(stop, value.stops.length - 1)]
  return (
    <div className="space-y-2">
      <Seg label="Fill" value={value.kind} options={PAINT_KINDS} onChange={setKind} />
      {value.kind === 'solid' && <ColorField label="Fill colour" value={value.color} onChange={(color) => onChange({ ...value, color })} accent={accent} />}
      {gradient && (
        <>
          <div ref={bar} role="group" aria-label="Gradient stops: click to add one"
            onPointerDown={(e) => {
              if (value.stops.length >= 8) return
              const r = e.currentTarget.getBoundingClientRect()
              const at = Math.round(((e.clientX - r.left) / r.width) * 100)
              const stops = [...value.stops, { color: current?.color ?? '#000000', at }].sort((a, b) => a.at - b.at)
              onChange({ ...value, stops })
              setStop(stops.findIndex((s) => s.at === at))
            }}
            className="relative h-5 cursor-copy rounded border border-zinc-700"
            style={{ background: `linear-gradient(to right,${stopsCss(value.stops, accent)}),repeating-conic-gradient(#3f3f46 0 25%,#27272a 0 50%) 0 0/8px 8px` }}>
            {value.stops.map((s, i) => (
              <button key={i} type="button" aria-label={`Stop at ${s.at}%`} onPointerDown={drag(i)}
                className={`absolute top-1/2 h-4 w-3 -translate-x-1/2 -translate-y-1/2 rounded-sm border-2 ${i === stop ? 'border-white' : 'border-zinc-400'}`}
                style={{ left: `${s.at}%`, background: swatchCss(s.color, accent) }} />
            ))}
          </div>
          {current && (
            <Row cols={3}>
              <div className="col-span-2"><ColorField label="Stop colour" value={current.color} onChange={(color) => setStopAt(stop, { color })} accent={accent} /></div>
              <div className="flex gap-1">
                <NumberField label="Stop position" short="%" value={current.at} min={0} max={100} places={0} onChange={(at) => setStopAt(stop, { at })} />
                <IconBtn title="Remove this stop" disabled={value.stops.length <= 2}
                  onClick={() => { onChange({ ...value, stops: value.stops.filter((_, j) => j !== stop) }); setStop(0) }}>
                  <Trash2 className="h-3.5 w-3.5" />
                </IconBtn>
              </div>
            </Row>
          )}
          {value.kind === 'linear' && (
            <NumberField label="Angle" short="∠" unit="°" value={value.angle} min={0} max={360} places={0} onChange={(angle) => onChange({ ...value, angle })} />
          )}
        </>
      )}
    </div>
  )
}

/** "Add" at the end of a list. */
export function AddButton({ label, onClick, disabled }: { label: string; onClick: () => void; disabled?: boolean }) {
  return (
    <IconBtn title={label} onClick={onClick} disabled={disabled}><Plus className="h-3.5 w-3.5" /></IconBtn>
  )
}
