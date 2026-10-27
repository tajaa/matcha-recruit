// The bar over what is selected, as Canva and Adobe Express have it: the few
// things changed most (a text's font, size and colour; a picture's crop; a
// shape's fill and border), lining things up, and lock, duplicate, delete
// and the rest of the right-click menu. The panels keep everything else.
// It sits just above the selection (below it when there's no room, at the
// top of the view when neither) and steps aside while something is dragged.

import { useEffect, useLayoutEffect, useRef, type MouseEvent, type ReactNode, type RefObject } from 'react'
import {
  AlignCenter, AlignCenterHorizontal, AlignCenterVertical, AlignEndHorizontal, AlignEndVertical, AlignHorizontalSpaceBetween,
  AlignJustify, AlignLeft, AlignRight, AlignStartHorizontal, AlignStartVertical, AlignVerticalSpaceBetween, Blend, Bold, Columns2,
  Copy, Crop, Ellipsis, Image as ImageIcon, Italic, LetterText, Link2, Lock, LockOpen, Minus, Plus, Scissors, SlidersHorizontal,
  Sparkles, Square, Trash2, Underline,
} from 'lucide-react'
import FontField from '../../magazine/workspace/FontField'
import { ColorPanel, IconBtn, NumberField, Seg, Slider } from '../../magazine/workspace/controls'
import { usePopover } from '../../magazine/workspace/popover'
import { swatchCss } from '../../magazine/workspace/color'
import { bounds, type Layout } from '../canvas/geometry'
import { CUTS } from '../fonts/cuts'
import { CUSTOM_FAMILY, customFamily } from '../model/doc'
import { resolveItem } from '../model/identity'
import { patchItems } from '../model/ops'
import type { Align, Fit, GraphicItem, ImageItem, Item, Stroke } from '../model/types'
import { useStudio, type State } from '../store/store'
import { barPlace, barShown } from './barPlace'
import { command } from './commands'
import { useCtx } from './context'
import { LengthField } from './fields'
import { charSetter, currentType, setPara } from './typeTarget'

const ROTATE_ROOM = 30 // the turn handle above a single selected thing

export default function SelectionBar({ lay, scroller, board }: {
  lay: Layout; scroller: RefObject<HTMLDivElement | null>; board: RefObject<HTMLDivElement | null>
}) {
  const c = useCtx()
  const s = useStudio(c.store, (x) => x)
  const bar = useRef<HTMLDivElement>(null)
  const place = useRef<() => void>(() => {})
  const shown = barShown(s)

  // Placed before it is painted when the selection, its place or the zoom
  // changes (not on each word typed), on a scroll, and when its size does.
  const editing = !!s.editing
  useLayoutEffect(() => {
    place.current = () => {
      const el = bar.current, sc = scroller.current, bd = board.current, host = bar.current?.parentElement
      if (!el || !sc || !bd || !host) return
      const st = c.store.get()
      const pageOf = new Map(st.doc.pages.map((p, i) => [p.id, i]))
      const chosen = st.doc.items.filter((i) => st.selection.includes(i.id))
      const sel = bounds(chosen, (i) => lay.origin[pageOf.get(i.page) ?? 0])
      if (!sel) return
      const one = chosen.length === 1 && !chosen[0].locked && !st.editing
      const b = bd.getBoundingClientRect(), h = host.getBoundingClientRect()
      const at = barPlace(sc.getBoundingClientRect(), b, sel, st.view.zoom, { w: el.offsetWidth, h: el.offsetHeight }, one ? ROTATE_ROOM : 0)
      // Scrolled out of sight: no bar for what can't be seen.
      el.style.visibility = at ? '' : 'hidden'
      if (!at) return
      el.style.left = `${at.left - h.left}px`
      el.style.top = `${at.top - h.top}px`
    }
    place.current()
  }, [c.store, lay, scroller, board, shown, s.selection, s.doc.items, s.doc.pages, s.view.zoom, editing])
  useEffect(() => {
    if (!shown) return
    const run = () => place.current()
    const sc = scroller.current
    sc?.addEventListener('scroll', run, { passive: true })
    window.addEventListener('resize', run)
    const watch = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(run)
    if (bar.current) watch?.observe(bar.current)
    return () => { sc?.removeEventListener('scroll', run); window.removeEventListener('resize', run); watch?.disconnect() }
  }, [shown, scroller])

  if (!shown) return null
  const all = s.doc.items.filter((i) => s.selection.includes(i.id)).map((i) => resolveItem(i, s.doc.identity))
  // What the bar changes: a locked thing stays as it is, as it does for a move.
  const items = all.filter((i) => !i.locked)
  const kinds = new Set(items.map((i) => i.kind))
  const only = kinds.size === 1 ? items[0].kind : null
  const parts: ReactNode[] = []
  if (!items.length) parts.push(<Locked key="locked" />)
  else {
    if (s.editing || only === 'text') parts.push(<TextPart key="text" s={s} />)
    if (!s.editing) {
      if (only === 'image') parts.push(<PicturePart key="picture" items={items as ImageItem[]} s={s} />)
      if (only === 'rect' || only === 'ellipse') parts.push(<ShapePart key="shape" items={items} units={s.doc.units} />)
      if (only === 'line') parts.push(<LinePart key="line" items={items} units={s.doc.units} />)
      const inked = items.filter((i): i is GraphicItem => i.kind === 'graphic' && i.color !== null)
      if (only === 'graphic' && inked.length) parts.push(<GraphicPart key="graphic" inked={inked} />)
      parts.push(<Common key="common" items={items} chosen={all.length} s={s} />)
    }
  }
  return (
    // Clicking the bar leaves the focus where it was (in the words being
    // typed, say); boxes typed in still take it.
    <div ref={bar} role="toolbar" aria-label="Selection" onMouseDown={keepFocus}
      className="absolute z-30 flex max-w-[calc(100%-16px)] flex-wrap items-center gap-1 rounded-lg border border-zinc-700 bg-zinc-900 p-1 text-zinc-200 shadow-2xl">
      {parts.flatMap((p, k) => (k ? [<span key={`sep${k}`} aria-hidden className="mx-0.5 h-5 w-px bg-zinc-700" />, p] : [p]))}
    </div>
  )
}

function keepFocus(e: MouseEvent) {
  if (!(e.target as HTMLElement).closest('input, textarea, select')) e.preventDefault()
}

// ── the parts ───────────────────────────────────────────────────────────────

const NEXT_ALIGN: Record<Align, Align> = { l: 'c', c: 'r', r: 'j', j: 'l', ja: 'l' }
const ALIGN: Record<Align, { label: string; icon: ReactNode }> = {
  l: { label: 'Aligned left', icon: <AlignLeft className="h-4 w-4" /> },
  c: { label: 'Centred', icon: <AlignCenter className="h-4 w-4" /> },
  r: { label: 'Aligned right', icon: <AlignRight className="h-4 w-4" /> },
  j: { label: 'Justified', icon: <AlignJustify className="h-4 w-4" /> },
  ja: { label: 'Justified, every line', icon: <AlignJustify className="h-4 w-4" /> },
}

/** The words: of the text selected (or at the caret), else every word in the frames selected. */
function TextPart({ s }: { s: State }) {
  const c = useCtx()
  const { char, para } = currentType(c, s)
  const set = charSetter(c)
  const custom = CUSTOM_FAMILY.test(char.font)
  const bold = char.wt >= 600
  return (
    <span className="flex items-center gap-0.5">
      <span className="w-40">
        <FontField value={custom ? `${customFamily(char.font)?.[0]?.name ?? 'Your font'} (yours)` : char.font} roles={false} cuts={CUTS}
          onChange={(font) => set({ font })} />
      </span>
      <IconBtn title="Smaller" onClick={() => set({ size: Math.max(1, Math.ceil(char.size) - 1) })}><Minus className="h-3.5 w-3.5" /></IconBtn>
      <span className="w-[4.5rem]">
        <NumberField label="Font size" short="pt" value={char.size} min={1} max={1296} step={1} places={1} onChange={(size) => set({ size })} />
      </span>
      <IconBtn title="Bigger" onClick={() => set({ size: Math.min(1296, Math.floor(char.size) + 1) })}><Plus className="h-3.5 w-3.5" /></IconBtn>
      <Swatch label="Text colour" value={char.color} letter onChange={(color) => color && set({ color })} />
      <IconBtn title="Bold (⌘B)" active={bold} onClick={() => set({ wt: bold ? 400 : 700 })}><Bold className="h-4 w-4" /></IconBtn>
      <IconBtn title="Italic (⌘I)" active={char.it} onClick={() => set({ it: !char.it })}><Italic className="h-4 w-4" /></IconBtn>
      <IconBtn title="Underline (⌘U)" active={char.u} onClick={() => set({ u: !char.u })}><Underline className="h-4 w-4" /></IconBtn>
      <IconBtn title={`${ALIGN[para.align].label}: click for ${ALIGN[NEXT_ALIGN[para.align]].label.toLowerCase()}`}
        onClick={() => setPara(c, { align: NEXT_ALIGN[para.align] })}>{ALIGN[para.align].icon}</IconBtn>
      <Pop label="Spacing" icon={<LetterText className="h-4 w-4" />} w={230} h={110}>
        <NumberField label="Letter spacing" short="VA" value={char.track} min={-500} max={2000} step={5} places={0}
          onChange={(track) => set({ track })} />
        <NumberField label="Line spacing" short="↕" value={para.lead} min={0} max={2000} step={0.5} places={2}
          blank={para.lead ? undefined : 'Auto'} onChange={(lead) => setPara(c, { lead })} />
      </Pop>
    </span>
  )
}

const FITS: { key: Fit; label: string }[] = [{ key: 'fill', label: 'Fill' }, { key: 'fit', label: 'Fit' }, { key: 'stretch', label: 'Stretch' }]

/** Pictures: replace, edit, cut out, crop, across the spread. */
function PicturePart({ items, s }: { items: ImageItem[]; s: State }) {
  const c = useCtx()
  const { store } = c
  const ids = items.map((i) => i.id)
  const first = items[0]
  const set = (patch: Record<string, unknown>, key: string | null = null) => store.edit((d) => patchItems(d, ids, patch), { key })
  const can = (id: string) => { const cmd = command(id); return !cmd.enabled || cmd.enabled(s) }
  if (items.length === 1 && !first.asset_id) {
    return <Labelled primary icon={<ImageIcon className="h-3.5 w-3.5" />} label="Choose a picture" onClick={() => store.set({ dialog: 'library' })} />
  }
  return (
    <span className="flex items-center gap-0.5">
      {items.length === 1 && (
        <>
          <Labelled icon={<ImageIcon className="h-3.5 w-3.5" />} label="Replace" title="Replace the picture" onClick={() => store.set({ dialog: 'library' })} />
          {can('edit-picture') && <Labelled icon={<SlidersHorizontal className="h-3.5 w-3.5" />} label="Edit" title="Edit the picture: light, colour and filters (⇧⌘E)"
            onClick={() => command('edit-picture').run(c)} />}
          {can('cut-out') && <Labelled icon={<Scissors className="h-3.5 w-3.5" />} label="Cut out" title="Cut out the subject"
            onClick={() => command('cut-out').run(c)} />}
        </>
      )}
      <Pop label="Crop" icon={<Crop className="h-4 w-4" />} w={260} h={160}>
        <Seg label="How it fills the frame" value={first.fit} options={FITS} onChange={(fit) => set({ fit })} />
        <Slider label="Zoom" value={first.zoom} min={100} max={400} unit="%" onChange={(zoom) => set({ zoom }, `zoom:${ids}`)} />
        <Slider label="Focus left" value={first.fx} min={0} max={100} unit="%" onChange={(fx) => set({ fx }, `fx:${ids}`)} />
        <Slider label="Focus top" value={first.fy} min={0} max={100} unit="%" onChange={(fy) => set({ fy }, `fy:${ids}`)} />
      </Pop>
      {items.length === 1 && can('across-spread') && <Labelled icon={<Columns2 className="h-3.5 w-3.5" />} label="Across"
        title="Run the picture across the spread" onClick={() => command('across-spread').run(c)} />}
      {items.length > 1 && can('link-crops') && <Labelled icon={<Link2 className="h-3.5 w-3.5" />} label="Link crops"
        title="Show one picture through these frames" onClick={() => command('link-crops').run(c)} />}
    </span>
  )
}

/** Rectangles and ellipses: the fill, and the border (and a rectangle's corners). */
function ShapePart({ items, units }: { items: Item[]; units: State['doc']['units'] }) {
  const { store } = useCtx()
  const ids = items.map((i) => i.id)
  const first = items[0] as Extract<Item, { kind: 'rect' | 'ellipse' }>
  const set = (patch: Record<string, unknown>) => store.edit((d) => patchItems(d, ids, patch))
  const stroke = first.stroke ?? { c: '#1a1a1a', w: 0 }
  return (
    <span className="flex items-center gap-0.5">
      <Swatch label="Fill" value={first.fill ?? ''} none="No fill" onChange={(fill) => set({ fill: fill || null })} />
      <Pop label="Border" icon={<Square className="h-4 w-4" />} w={240} h={first.kind === 'rect' ? 140 : 100}>
        <BorderFields stroke={stroke} units={units} min={0}
          onChange={(next, colour) => set({ stroke: next, ...(colour ? { stroke_swatch: undefined } : {}) })} />
        {first.kind === 'rect' && (
          <LengthField label="Corner radius" short="◜" units={units} value={first.radius} min={0} max={1000} onChange={(radius) => set({ radius })} />
        )}
      </Pop>
    </span>
  )
}

/** Lines: their colour and weight. */
function LinePart({ items, units }: { items: Item[]; units: State['doc']['units'] }) {
  const { store } = useCtx()
  const ids = items.map((i) => i.id)
  const first = items[0] as Extract<Item, { kind: 'line' }>
  return (
    <span className="flex items-center gap-0.5">
      <BorderFields stroke={first.stroke} units={units} min={0.25} line
        onChange={(stroke, colour) => store.edit((d) => patchItems(d, ids, { stroke, ...(colour ? { stroke_swatch: undefined } : {}) }))} />
    </span>
  )
}

/** A border's colour and weight, as the Object panel's Stroke sets them. */
function BorderFields({ stroke, units, min, line, onChange }: {
  stroke: Stroke; units: State['doc']['units']; min: number; line?: boolean; onChange: (s: Stroke | null, colour?: boolean) => void
}) {
  return (
    <span className="flex items-center gap-1">
      <Swatch label={line ? 'Line colour' : 'Border colour'} value={stroke.c} onChange={(c) => c && onChange({ c, w: stroke.w || 1 }, true)} />
      <span className="w-24">
        <LengthField label={line ? 'Line weight' : 'Border weight'} short="≡" units={units} value={stroke.w} min={min} max={144}
          onChange={(w) => onChange(w > 0 ? { c: stroke.c, w } : line ? { c: stroke.c, w: min } : null)} />
      </span>
    </span>
  )
}

/** One-colour graphics: their colour (a colourful one keeps its own). */
function GraphicPart({ inked }: { inked: GraphicItem[] }) {
  const { store } = useCtx()
  return <Swatch label="Graphic colour" value={inked[0].color ?? ''}
    onChange={(color) => color && store.edit((d) => patchItems(d, inked.map((i) => i.id), { color }))} />
}

const ALIGNS: { id: string; label: string; icon: ReactNode }[] = [
  { id: 'align-left', label: 'Left', icon: <AlignStartVertical className="h-4 w-4" /> },
  { id: 'align-centre', label: 'Centre', icon: <AlignCenterVertical className="h-4 w-4" /> },
  { id: 'align-right', label: 'Right', icon: <AlignEndVertical className="h-4 w-4" /> },
  { id: 'align-top', label: 'Top', icon: <AlignStartHorizontal className="h-4 w-4" /> },
  { id: 'align-middle', label: 'Middle', icon: <AlignCenterHorizontal className="h-4 w-4" /> },
  { id: 'align-bottom', label: 'Bottom', icon: <AlignEndHorizontal className="h-4 w-4" /> },
]

/** Everything selected: line it up, see through it, lock, duplicate, delete,
 *  more. `items`: the unlocked ones; `chosen`: how many are selected (locked
 *  ones count when lining up). */
function Common({ items, chosen, s }: { items: Item[]; chosen: number; s: State }) {
  const c = useCtx()
  const { store } = c
  const ids = items.map((i) => i.id)
  const spaced = command('space-across').enabled!(s)
  return (
    <span className="flex items-center gap-0.5">
      <Pop label="Position" icon={<AlignStartVertical className="h-4 w-4" />} w={250} h={spaced ? 150 : 110}>
        <p className="text-[11px] text-zinc-400">{chosen === 1 ? 'Line it up with the page' : 'Line them up with each other'}</p>
        <div className="grid grid-cols-3 gap-1">
          {ALIGNS.map((a) => (
            <button key={a.id} type="button" onClick={() => command(a.id).run(c)} aria-label={command(a.id).label} title={command(a.id).label}
              className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-800">{a.icon}{a.label}</button>
          ))}
        </div>
        {spaced && (
          <div className="grid grid-cols-2 gap-1 border-t border-zinc-800 pt-2">
            <button type="button" onClick={() => command('space-across').run(c)}
              className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-800">
              <AlignHorizontalSpaceBetween className="h-4 w-4" />Space across</button>
            <button type="button" onClick={() => command('space-down').run(c)}
              className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-800">
              <AlignVerticalSpaceBetween className="h-4 w-4" />Space down</button>
          </div>
        )}
      </Pop>
      <Pop label="Transparency" icon={<Blend className="h-4 w-4" />} w={240} h={70}>
        <Slider label="Opacity" value={items[0].opacity} min={0} max={100} unit="%"
          onChange={(opacity) => store.edit((d) => patchItems(d, ids, { opacity }), { key: `opacity:${ids}` })} />
      </Pop>
      <IconBtn title="Lock (⌘L)" onClick={() => command('lock').run(c)}><Lock className="h-4 w-4" /></IconBtn>
      <IconBtn title="Duplicate (⌘D)" onClick={() => command('duplicate').run(c)}><Copy className="h-4 w-4" /></IconBtn>
      <IconBtn title="Delete (⌫)" onClick={() => command('delete').run(c)}><Trash2 className="h-4 w-4" /></IconBtn>
      <IconBtn title="Ask about this: how to make it look like a picture you like" onClick={() => command('ask-about').run(c)}>
        <Sparkles className="h-4 w-4 text-emerald-400" />
      </IconBtn>
      <More />
    </span>
  )
}

/** Everything selected is locked: only the way to unlock it, and the menu. */
function Locked() {
  const c = useCtx()
  return (
    <span className="flex items-center gap-0.5">
      <span className="px-1.5 text-xs text-zinc-400">Locked</span>
      <IconBtn title="Unlock (⌘L)" onClick={() => command('lock').run(c)}><LockOpen className="h-4 w-4" /></IconBtn>
      <More />
    </span>
  )
}

/** The right-click menu, opened under this button. */
function More() {
  const { store } = useCtx()
  return (
    <button type="button" title="More" aria-label="More" aria-haspopup="menu"
      onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); store.set({ menu: { x: r.left, y: r.bottom + 4 } }) }}
      className="inline-flex h-7 min-w-[28px] items-center justify-center rounded-md px-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100">
      <Ellipsis className="h-4 w-4" />
    </button>
  )
}

// ── small pieces ───────────────────────────────────────────────────────────

/** A button with its word beside its icon (`primary`: the one thing to do). */
function Labelled({ icon, label, title, onClick, primary }: { icon: ReactNode; label: string; title?: string; onClick: () => void; primary?: boolean }) {
  return (
    <button type="button" title={title ?? label} onClick={onClick}
      className={`inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-xs ${primary
        ? 'bg-emerald-600 font-medium text-white hover:bg-emerald-500' : 'text-zinc-200 hover:bg-zinc-800 hover:text-white'}`}>
      {icon}{label}
    </button>
  )
}

/** An icon button opening a small panel under it. */
function Pop({ label, icon, w, h, children }: { label: string; icon: ReactNode; w: number; h: number; children: ReactNode }) {
  const btn = useRef<HTMLButtonElement>(null)
  const { panel, at, toggle } = usePopover(btn, { w, h })
  return (
    <>
      <button ref={btn} type="button" title={label} aria-label={label} aria-haspopup="dialog" aria-expanded={!!at} onClick={toggle}
        className={`inline-flex h-7 min-w-[28px] items-center justify-center rounded-md px-1.5 ${at ? 'bg-zinc-700 text-white' : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100'}`}>
        {icon}
      </button>
      {at && (
        <div ref={panel} role="dialog" aria-label={label} style={{ ...at, width: w }}
          className="fixed z-50 space-y-2 rounded-lg border border-zinc-700 bg-zinc-900 p-2.5 text-zinc-200 shadow-2xl">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">{label}</p>
          {children}
        </div>
      )}
    </>
  )
}

/** A colour as a swatch (or, for words, an A underlined in it), the picker under it. */
function Swatch({ label, value, onChange, none, letter }: {
  label: string; value: string; onChange: (c: string) => void
  /** What no colour is called, offered first ("No fill"). */
  none?: string
  letter?: boolean
}) {
  const btn = useRef<HTMLButtonElement>(null)
  const { panel, at, toggle } = usePopover(btn)
  const css = swatchCss(value)
  return (
    <>
      <button ref={btn} type="button" title={label} aria-label={`${label}: ${value === 'accent' ? 'accent' : value || none || ''}`}
        aria-haspopup="dialog" aria-expanded={!!at} onClick={toggle}
        className={`inline-flex h-7 min-w-[28px] items-center justify-center rounded-md px-1.5 ${at ? 'bg-zinc-700' : 'hover:bg-zinc-800'}`}>
        {letter ? (
          <span className="flex flex-col items-center leading-none">
            <span className="text-[13px] font-semibold text-zinc-100">A</span>
            <span className="mt-0.5 h-1 w-4 rounded-sm border border-zinc-600" style={{ background: css }} />
          </span>
        ) : (
          <span className="h-4 w-4 rounded border border-zinc-500"
            style={{ background: value ? css : 'linear-gradient(135deg, transparent 45%, #f87171 45% 55%, transparent 55%)' }} />
        )}
      </button>
      {at && <ColorPanel panel={panel} at={at} label={label} value={value} onChange={onChange} auto={none} />}
    </>
  )
}
