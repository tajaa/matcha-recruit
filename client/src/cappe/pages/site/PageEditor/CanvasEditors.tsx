import { useEffect, useState, type PointerEvent as ReactPointerEvent } from 'react'
import {
  ChevronDown, ChevronUp, Copy, GripVertical, ImagePlus, Monitor, Plus, Smartphone, Trash2, Type, Wand2, X,
} from 'lucide-react'
import type { CappeBlock, CappeCanvasElement, CappeCanvasPos } from '../../../types'
import { BLOCK_ORDER, BLOCK_SCHEMAS } from './blockSchemas'
import { CV_ELEMENT_KINDS, CV_MAX_ELEMENTS, CONVERTIBLE_TO_CANVAS, convertSectionToCanvas, cvEls, cvNewElement, cvNextY } from './canvasHelpers'
import { CappeFontPicker } from './CappeFontPicker'
import { DColor, DNum, DSelect } from './DesignPrimitives'
import { DesignInspector } from './DesignInspector'
import { FieldInput, ImageInput } from './FieldInputs'
import { dLabel, inputCls } from './styles'

export function AddPalette({ onPick }: { onPick: (type: string) => void }) {
  return (
    <div className="absolute z-20 mt-1 grid w-full grid-cols-2 gap-1 rounded-xl border border-zinc-700 bg-zinc-900 p-2 shadow-xl shadow-black/40">
      {BLOCK_ORDER.map((t) => (
        <button key={t} onClick={() => onPick(t)} className="rounded-lg px-3 py-2 text-left text-sm text-zinc-300 hover:bg-emerald-500/10 hover:text-emerald-400">
          {BLOCK_SCHEMAS[t].label}
        </button>
      ))}
    </div>
  )
}

/** Contextual editor for the block selected on the canvas. Same controls as the
 *  form editor (schema fields + DesignInspector), driven by selection. */
export function CanvasPanel({ blocks, sel, onChange, onMove, onRemove, onDuplicate, onAddAt, onAdd, onHeaderPointerDown, onClose }: {
  blocks: CappeBlock[]
  sel: number | null
  onChange: (i: number, b: CappeBlock) => void
  onMove: (i: number, dir: -1 | 1) => void
  onRemove: (i: number) => void
  onDuplicate: (i: number) => void
  onAddAt: (type: string, i: number) => void
  onAdd: (type: string) => void
  onHeaderPointerDown?: (e: ReactPointerEvent) => void
  onClose?: () => void
}) {
  const [addOpen, setAddOpen] = useState(false)
  // Close the palette whenever the selection changes.
  useEffect(() => { setAddOpen(false) }, [sel])

  if (sel == null || !blocks[sel]) {
    return (
      <div className="p-4">
        <p className="rounded-lg border border-dashed border-zinc-700 p-4 text-center text-xs text-zinc-500">
          Click any section on the canvas to edit it. Double-click text to type in place.
        </p>
        <div className="relative mt-3">
          <button onClick={() => setAddOpen((o) => !o)} className="flex w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed border-zinc-700 py-3 text-sm font-semibold text-zinc-400 hover:border-emerald-500 hover:text-emerald-400">
            <Plus className="h-4 w-4" /> Add block
          </button>
          {addOpen && <AddPalette onPick={(t) => { onAdd(t); setAddOpen(false) }} />}
        </div>
      </div>
    )
  }

  const block = blocks[sel]
  const schema = BLOCK_SCHEMAS[block.type]
  return (
    <div className="space-y-3 p-4">
      <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
        <button type="button" onPointerDown={onHeaderPointerDown} title="Drag to move" className="flex cursor-move select-none items-center gap-1.5 text-sm font-semibold text-zinc-100">
          <GripVertical className="h-3.5 w-3.5 text-zinc-600" />{schema?.label || block.type}
        </button>
        <div className="flex items-center gap-1.5 text-zinc-500">
          <button title="Move up" onClick={() => onMove(sel, -1)} disabled={sel === 0} className="hover:text-zinc-200 disabled:opacity-30"><ChevronUp className="h-4 w-4" /></button>
          <button title="Move down" onClick={() => onMove(sel, 1)} disabled={sel === blocks.length - 1} className="hover:text-zinc-200 disabled:opacity-30"><ChevronDown className="h-4 w-4" /></button>
          <button title="Duplicate" onClick={() => onDuplicate(sel)} className="hover:text-zinc-200"><Copy className="h-4 w-4" /></button>
          <button title="Delete" onClick={() => onRemove(sel)} className="hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
          {onClose && <button title="Close" onClick={onClose} className="ml-1 border-l border-zinc-700 pl-1.5 hover:text-zinc-200"><X className="h-4 w-4" /></button>}
        </div>
      </div>
      {CONVERTIBLE_TO_CANVAS.has(block.type) && (
        <button onClick={() => onChange(sel, convertSectionToCanvas(block))}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-amber-700/40 bg-amber-500/[0.06] px-3 py-2 text-xs font-semibold text-amber-200 hover:bg-amber-500/10">
          <Wand2 className="h-3.5 w-3.5" /> Customize freely
        </button>
      )}
      {schema ? (
        <>
          {schema.fields.map((f) => (
            <FieldInput key={f.key} field={f} value={block[f.key]} onChange={(v) => onChange(sel, { ...block, [f.key]: v })} />
          ))}
          <DesignInspector design={block._design} onChange={(dz) => onChange(sel, { ...block, _design: dz })} />
        </>
      ) : <p className="text-xs text-zinc-500">Unknown block “{block.type}”.</p>}
      <div className="relative pt-1">
        <button onClick={() => setAddOpen((o) => !o)} className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-zinc-700 py-2 text-xs font-medium text-zinc-400 hover:border-emerald-500 hover:text-emerald-400">
          <Plus className="h-3.5 w-3.5" /> Add block below
        </button>
        {addOpen && <AddPalette onPick={(t) => { onAddAt(t, sel); setAddOpen(false) }} />}
      </div>
    </div>
  )
}

// ── freeform canvas: per-element controls (shared by inspector + form editor) ─
export function ElementControls({ el, bp, onPatch }: {
  el: CappeCanvasElement
  bp: 'd' | 'm'
  onPatch: (fn: (e: CappeCanvasElement) => CappeCanvasElement) => void
}) {
  const style = el.style || {}
  const setStyle = (k: keyof NonNullable<CappeCanvasElement['style']>, v: unknown) =>
    onPatch((e) => ({ ...e, style: { ...(e.style || {}), [k]: v } }))
  const place = (bp === 'm' ? el.m : el.d) || { x: 0, y: 0, w: 1, h: 1 }
  const setPlace = (k: keyof CappeCanvasPos, v: number) =>
    onPatch((e) => {
      const cur = (bp === 'm' ? e.m : e.d) || { x: 0, y: 0, w: 1, h: 1 }
      const next = { ...cur, [k]: Math.max(0, Math.round(v)) }
      return bp === 'm' ? { ...e, m: next } : { ...e, d: next }
    })
  return (
    <div className="space-y-2.5">
      {el.kind === 'image' ? (
        <>
          <div><span className={dLabel}>Image</span><ImageInput value={el.src || ''} onChange={(v) => onPatch((e) => ({ ...e, src: v }))} /></div>
          <input value={el.alt || ''} onChange={(e) => onPatch((x) => ({ ...x, alt: e.target.value }))} placeholder="Alt text (accessibility)" className={`${inputCls} py-1.5`} />
          <div className="grid grid-cols-2 gap-2">
            <DSelect label="Fit" value={style.fit || 'cover'} options={[['cover', 'Cover'], ['contain', 'Contain'], ['fill', 'Fill'], ['none', 'None']]} onChange={(v) => setStyle('fit', v)} />
            <DNum label="Corner radius" value={style.radius || 0} min={0} max={200} onChange={(v) => setStyle('radius', v || undefined)} />
          </div>
        </>
      ) : el.kind === 'button' ? (
        <>
          <div><span className={dLabel}>Label</span><input value={el.text || ''} onChange={(e) => onPatch((x) => ({ ...x, text: e.target.value }))} className={`${inputCls} py-1.5`} /></div>
          <div><span className={dLabel}>Link</span><input value={el.href || ''} onChange={(e) => onPatch((x) => ({ ...x, href: e.target.value }))} placeholder="/p/contact or https://…" className={`${inputCls} py-1.5`} /></div>
          <div className="grid grid-cols-2 gap-2">
            <DSelect label="Style" value={style.variant || 'solid'} options={[['solid', 'Solid'], ['outline', 'Outline']]} onChange={(v) => setStyle('variant', v)} />
            <DNum label="Corner radius" value={style.radius || 0} min={0} max={200} onChange={(v) => setStyle('radius', v || undefined)} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <DColor label="Background" value={style.bg || ''} onChange={(v) => setStyle('bg', v)} />
            <DColor label="Text color" value={style.color || ''} onChange={(v) => setStyle('color', v)} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <CappeFontPicker label="Font" value={style.font || 'Inter'} onChange={(v) => setStyle('font', v)} />
            <DSelect label="Weight" value={String(style.weight || '')} options={[['', 'Default'], ['400', 'Regular'], ['500', 'Medium'], ['600', 'Semibold'], ['700', 'Bold'], ['800', 'Extrabold'], ['900', 'Black']]} onChange={(v) => setStyle('weight', v ? Number(v) : undefined)} />
          </div>
        </>
      ) : (
        <>
          <div><span className={dLabel}>Text</span><textarea value={el.text || ''} onChange={(e) => onPatch((x) => ({ ...x, text: e.target.value }))} rows={2} className={`${inputCls} py-1.5`} /></div>
          <CappeFontPicker label="Font" value={style.font || 'Inter'} onChange={(v) => setStyle('font', v)} />
          <div className="grid grid-cols-2 gap-2">
            <DNum label="Size (px)" value={style.size || 0} min={0} max={200} onChange={(v) => setStyle('size', v || undefined)} />
            <DSelect label="Weight" value={String(style.weight || '')} options={[['', 'Default'], ['400', 'Regular'], ['500', 'Medium'], ['600', 'Semibold'], ['700', 'Bold'], ['800', 'Extrabold'], ['900', 'Black']]} onChange={(v) => setStyle('weight', v ? Number(v) : undefined)} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <DSelect label="Align" value={style.align || 'left'} options={[['left', 'Left'], ['center', 'Center'], ['right', 'Right'], ['justify', 'Justify']]} onChange={(v) => setStyle('align', v)} />
            <DColor label="Color" value={style.color || ''} onChange={(v) => setStyle('color', v)} />
          </div>
        </>
      )}
      <div>
        <span className={dLabel}>Position — {bp === 'm' ? 'Mobile' : 'Desktop'} (grid units)</span>
        <div className="grid grid-cols-4 gap-1.5">
          <DNum label="X" value={place.x} min={0} max={48} onChange={(v) => setPlace('x', v)} />
          <DNum label="Y" value={place.y} min={0} max={400} onChange={(v) => setPlace('y', v)} />
          <DNum label="W" value={place.w} min={1} max={48} onChange={(v) => setPlace('w', v)} />
          <DNum label="H" value={place.h} min={1} max={48} onChange={(v) => setPlace('h', v)} />
        </div>
      </div>
    </div>
  )
}

/** Canvas-mode floating inspector: edits the selected freeform element (or, when
 *  none is selected, shows add-element + the section design). */
export function CanvasInspector({ block, elementId, bp, onSetBp, onPatchElement, onAddElement, onRemoveElement, onChangeBlock, onHeaderPointerDown, onClose }: {
  block: CappeBlock
  elementId: string | null
  bp: 'd' | 'm'
  onSetBp: (bp: 'd' | 'm') => void
  onPatchElement: (id: string, fn: (e: CappeCanvasElement) => CappeCanvasElement) => void
  onAddElement: (kind: CappeCanvasElement['kind']) => void
  onRemoveElement: (id: string) => void
  onChangeBlock: (b: CappeBlock) => void
  onHeaderPointerDown?: (e: ReactPointerEvent) => void
  onClose: () => void
}) {
  const el = cvEls(block).find((e) => e.id === elementId) || null
  const kindLabel = el ? ({ heading: 'Heading', text: 'Text', image: 'Image', button: 'Button' } as const)[el.kind] : 'Freeform section'
  return (
    <div className="space-y-3 p-4">
      <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
        <button type="button" onPointerDown={onHeaderPointerDown} title="Drag to move" className="flex cursor-move select-none items-center gap-1.5 text-sm font-semibold text-zinc-100">
          <GripVertical className="h-3.5 w-3.5 text-zinc-600" />{kindLabel}
        </button>
        <div className="flex items-center gap-1.5 text-zinc-500">
          {el && <button title="Delete element" onClick={() => onRemoveElement(el.id)} className="hover:text-red-400"><Trash2 className="h-4 w-4" /></button>}
          <button title="Close" onClick={onClose} className="ml-1 border-l border-zinc-700 pl-1.5 hover:text-zinc-200"><X className="h-4 w-4" /></button>
        </div>
      </div>
      <div className="flex rounded-lg border border-zinc-700 p-0.5">
        {(['d', 'm'] as const).map((x) => (
          <button key={x} onClick={() => onSetBp(x)} className={`flex flex-1 items-center justify-center gap-1 rounded-md px-2 py-1 text-xs font-medium ${bp === x ? 'bg-emerald-500 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'}`}>
            {x === 'd' ? <Monitor className="h-3.5 w-3.5" /> : <Smartphone className="h-3.5 w-3.5" />} {x === 'd' ? 'Desktop' : 'Mobile'}
          </button>
        ))}
      </div>
      {el ? (
        <ElementControls el={el} bp={bp} onPatch={(fn) => onPatchElement(el.id, fn)} />
      ) : (
        <p className="rounded-lg border border-dashed border-zinc-700 p-3 text-center text-xs text-zinc-500">Click any element on the canvas to edit it. Drag to move; drag a corner to resize.</p>
      )}
      <div className="flex gap-1.5 border-t border-zinc-800 pt-2">
        {CV_ELEMENT_KINDS.map((k) => (
          <button key={k} onClick={() => onAddElement(k)} className="flex-1 rounded-lg border border-dashed border-zinc-700 px-2 py-1.5 text-xs font-medium capitalize text-zinc-300 hover:border-emerald-500 hover:text-emerald-400">+ {k}</button>
        ))}
      </div>
      <DesignInspector design={(block as { _design?: unknown })._design} onChange={(dz) => onChangeBlock({ ...block, _design: dz })} />
    </div>
  )
}

/** Form-mode editor for a freeform canvas block — element list + the same
 *  controls + numeric positions, so it's fully editable without the drag canvas. */
export function CanvasFormEditor({ block, onChange }: { block: CappeBlock; onChange: (b: CappeBlock) => void }) {
  const [openId, setOpenId] = useState<string | null>(null)
  const [bp, setBp] = useState<'d' | 'm'>('d')
  const els = cvEls(block)
  const patchEl = (id: string, fn: (e: CappeCanvasElement) => CappeCanvasElement) =>
    onChange({ ...block, elements: els.map((e) => (e.id === id ? fn(e) : e)) })
  const addEl = (kind: CappeCanvasElement['kind']) => {
    if (els.length >= CV_MAX_ELEMENTS) return
    const ne = cvNewElement(kind, cvNextY(els))
    onChange({ ...block, elements: [...els, ne] }); setOpenId(ne.id)
  }
  const removeEl = (id: string) => onChange({ ...block, elements: els.filter((e) => e.id !== id) })
  return (
    <div className="space-y-3 p-4">
      <p className="text-xs text-zinc-500">Freeform section — switch to <b className="text-zinc-300">Canvas</b> mode to drag elements; here you can edit them and set exact grid positions.</p>
      <div className="flex w-44 rounded-lg border border-zinc-700 p-0.5">
        {(['d', 'm'] as const).map((x) => (
          <button key={x} onClick={() => setBp(x)} className={`flex-1 rounded-md px-2 py-1 text-xs font-medium ${bp === x ? 'bg-emerald-500 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'}`}>{x === 'd' ? 'Desktop' : 'Mobile'}</button>
        ))}
      </div>
      <ul className="space-y-2">
        {els.map((el) => (
          <li key={el.id} className="rounded-lg border border-zinc-800 bg-zinc-950/60">
            <div className="flex items-center justify-between px-3 py-2">
              <button onClick={() => setOpenId((o) => (o === el.id ? null : el.id))} className="flex min-w-0 items-center gap-2 text-sm text-zinc-200">
                {el.kind === 'image' ? <ImagePlus className="h-3.5 w-3.5 shrink-0 text-zinc-500" /> : <Type className="h-3.5 w-3.5 shrink-0 text-zinc-500" />}
                <span className="truncate">{el.kind === 'image' ? (el.src ? 'Image' : 'Image (empty)') : (el.text || '(empty text)')}</span>
              </button>
              <div className="flex items-center gap-1 text-zinc-500">
                <button onClick={() => removeEl(el.id)} className="hover:text-red-400"><Trash2 className="h-3.5 w-3.5" /></button>
                <button onClick={() => setOpenId((o) => (o === el.id ? null : el.id))} className="hover:text-zinc-200">{openId === el.id ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}</button>
              </div>
            </div>
            {openId === el.id && <div className="border-t border-zinc-800 p-3"><ElementControls el={el} bp={bp} onPatch={(fn) => patchEl(el.id, fn)} /></div>}
          </li>
        ))}
        {els.length === 0 && <li className="rounded-lg border border-dashed border-zinc-700 p-3 text-center text-xs text-zinc-500">No elements yet.</li>}
      </ul>
      <div className="flex gap-1.5">
        {CV_ELEMENT_KINDS.map((k) => (
          <button key={k} onClick={() => addEl(k)} className="flex-1 rounded-lg border border-dashed border-zinc-700 px-2 py-1.5 text-xs font-medium capitalize text-zinc-300 hover:border-emerald-500 hover:text-emerald-400">+ {k}</button>
        ))}
      </div>
      <DesignInspector design={(block as { _design?: unknown })._design} onChange={(dz) => onChange({ ...block, _design: dz })} />
    </div>
  )
}
