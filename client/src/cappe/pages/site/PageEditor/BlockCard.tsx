import { useEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronUp, ClipboardPaste, Copy, CopyPlus, GripVertical, MoreVertical, Trash2, Wand2 } from 'lucide-react'
import type { CappeBlock } from '../../../types'
import { BLOCK_SCHEMAS } from './blockSchemas'
import { CanvasFormEditor } from './CanvasEditors'
import { CONVERTIBLE_TO_CANVAS, convertSectionToCanvas } from './canvasHelpers'
import { usePremium } from './DesignPrimitives'
import { DesignInspector } from './DesignInspector'
import { FieldInput } from './FieldInputs'

/** Overflow menu for the less-frequent actions (copy/paste style, duplicate,
 *  reorder) — keeps the always-visible header row down to grip/label/kebab/
 *  delete/chevron instead of up to 7 icon buttons. */
function BlockMenu({ index, total, onMove, onDuplicate, onCopyStyle, onPasteStyle, canPasteStyle, premium }: {
  index: number; total: number
  onMove: (dir: -1 | 1) => void
  onDuplicate?: () => void
  onCopyStyle?: () => void
  onPasteStyle?: () => void
  canPasteStyle?: boolean
  premium: boolean
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])
  const item = (label: string, onClick: (() => void) | undefined, disabled?: boolean, Icon?: typeof Copy) => (
    <button
      type="button"
      disabled={disabled || !onClick}
      onClick={() => { onClick?.(); setOpen(false) }}
      className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-30 disabled:hover:bg-transparent"
    >
      {Icon && <Icon className="h-3.5 w-3.5" />} {label}
    </button>
  )
  return (
    <div ref={ref} className="relative">
      <button type="button" onClick={() => setOpen((o) => !o)} className="hover:text-zinc-200"><MoreVertical className="h-4 w-4" /></button>
      {open && (
        <div className="absolute right-0 top-full z-10 mt-1 w-44 overflow-hidden rounded-lg border border-zinc-700 bg-zinc-900 py-1 shadow-xl shadow-black/40">
          {premium && onCopyStyle && item('Copy design', onCopyStyle, false, Copy)}
          {premium && onPasteStyle && item('Paste design', onPasteStyle, !canPasteStyle, ClipboardPaste)}
          {onDuplicate && item('Duplicate section', onDuplicate, false, CopyPlus)}
          {item('Move up', () => onMove(-1), index === 0, ChevronUp)}
          {item('Move down', () => onMove(1), index === total - 1, ChevronDown)}
        </div>
      )}
    </div>
  )
}

export function BlockCard({
  block, index, total, onChange, onRemove, onMove, defaultOpen,
  onDuplicate, onCopyStyle, onPasteStyle, canPasteStyle, onDragStart, onDragEnd,
  onHoverStart, onHoverEnd, onExpand, forceOpenTick,
}: {
  block: CappeBlock; index: number; total: number
  onChange: (b: CappeBlock) => void
  onRemove: () => void
  onMove: (dir: -1 | 1) => void
  /** Auto-expand once (the block just added), instead of the new collapsed default. */
  defaultOpen?: boolean
  onDuplicate?: () => void
  onCopyStyle?: () => void
  onPasteStyle?: () => void
  canPasteStyle?: boolean
  onDragStart?: () => void
  onDragEnd?: () => void
  /** Hover sync — highlights this block in the live preview. */
  onHoverStart?: () => void
  onHoverEnd?: () => void
  /** Expand sync — highlight + scroll the block into view in the preview
   *  (deliberate action, unlike hover, so scrolling won't yank the preview
   *  around while mousing down the card list). */
  onExpand?: () => void
  /** Bumped when this block is clicked in the preview — expands + scrolls to it. */
  forceOpenTick?: number
}) {
  const [open, setOpen] = useState(!!defaultOpen)
  const schema = BLOCK_SCHEMAS[block.type]
  const premium = usePremium()
  const rootRef = useRef<HTMLDivElement>(null)
  const toggle = () => setOpen((o) => { if (!o) onExpand?.(); return !o })

  // A page click (form-mode preview → card sync) forces this card open and
  // scrolls it into view, even if the user had collapsed it.
  const lastTick = useRef(forceOpenTick)
  useEffect(() => {
    if (forceOpenTick === undefined || forceOpenTick === lastTick.current) return
    lastTick.current = forceOpenTick
    setOpen(true)
    rootRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [forceOpenTick])

  return (
    <div
      ref={rootRef}
      className="rounded-xl border border-zinc-800 bg-zinc-900"
      onMouseEnter={onHoverStart}
      onMouseLeave={onHoverEnd}
    >
      <div className="flex items-center justify-between gap-2 border-b border-zinc-800 px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <span
            draggable={!!onDragStart}
            onDragStart={onDragStart}
            onDragEnd={onDragEnd}
            title="Drag to reorder"
            className={onDragStart ? 'cursor-grab active:cursor-grabbing text-zinc-600 hover:text-zinc-400' : 'text-zinc-600'}
          >
            <GripVertical className="h-4 w-4" />
          </span>
          <button type="button" onClick={toggle} className="truncate text-sm font-semibold text-zinc-100">
            {schema?.label || block.type}
          </button>
        </div>
        <div className="flex items-center gap-1.5 text-zinc-500">
          {premium && CONVERTIBLE_TO_CANVAS.has(block.type) && (
            <button type="button" title="Customize freely — turn this section into a freeform layout you can drag & restyle (one-way)"
              onClick={() => onChange(convertSectionToCanvas(block))}
              className="mr-1 flex items-center gap-1 rounded-md border border-zinc-700 px-2 py-1 text-[11px] font-medium text-zinc-300 hover:border-emerald-500 hover:text-emerald-400">
              <Wand2 className="h-3.5 w-3.5 text-amber-400" /> Customize freely
            </button>
          )}
          <BlockMenu
            index={index} total={total} onMove={onMove} onDuplicate={onDuplicate}
            onCopyStyle={block.type !== 'canvas' ? onCopyStyle : undefined}
            onPasteStyle={block.type !== 'canvas' ? onPasteStyle : undefined}
            canPasteStyle={canPasteStyle} premium={premium}
          />
          <button type="button" onClick={onRemove} className="hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
          <button type="button" onClick={toggle} className="hover:text-zinc-200">{open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}</button>
        </div>
      </div>
      {open && block.type === 'canvas' && <CanvasFormEditor block={block} onChange={onChange} />}
      {open && block.type !== 'canvas' && schema && (
        <div className="space-y-3 p-4">
          {schema.fields.map((f) => (
            <FieldInput key={f.key} field={f} value={block[f.key]} onChange={(v) => onChange({ ...block, [f.key]: v })} />
          ))}
          <DesignInspector blockType={block.type} design={block._design} onChange={(dz) => onChange({ ...block, _design: dz })} />
        </div>
      )}
      {open && block.type !== 'canvas' && !schema && <div className="p-4 text-sm text-zinc-500">Unknown block type “{block.type}”.</div>}
    </div>
  )
}
