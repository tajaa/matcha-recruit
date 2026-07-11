import { useState } from 'react'
import { ChevronDown, ChevronUp, ClipboardPaste, Copy, CopyPlus, GripVertical, Trash2, Wand2 } from 'lucide-react'
import type { CappeBlock } from '../../../../types/cappe'
import { BLOCK_SCHEMAS } from './blockSchemas'
import { CanvasFormEditor } from './CanvasEditors'
import { CONVERTIBLE_TO_CANVAS, convertSectionToCanvas } from './canvasHelpers'
import { usePremium } from './DesignPrimitives'
import { DesignInspector } from './DesignInspector'
import { FieldInput } from './FieldInputs'

export function BlockCard({
  block, index, total, onChange, onRemove, onMove,
  onDuplicate, onCopyStyle, onPasteStyle, canPasteStyle, onDragStart, onDragEnd,
}: {
  block: CappeBlock; index: number; total: number
  onChange: (b: CappeBlock) => void
  onRemove: () => void
  onMove: (dir: -1 | 1) => void
  onDuplicate?: () => void
  onCopyStyle?: () => void
  onPasteStyle?: () => void
  canPasteStyle?: boolean
  onDragStart?: () => void
  onDragEnd?: () => void
}) {
  const [open, setOpen] = useState(true)
  const schema = BLOCK_SCHEMAS[block.type]
  const premium = usePremium()
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900">
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
          <button type="button" onClick={() => setOpen((o) => !o)} className="truncate text-sm font-semibold text-zinc-100">
            {schema?.label || block.type}
          </button>
        </div>
        <div className="flex items-center gap-1 text-zinc-500">
          {premium && CONVERTIBLE_TO_CANVAS.has(block.type) && (
            <button type="button" title="Customize freely — turn this section into a freeform layout you can drag & restyle (one-way)"
              onClick={() => onChange(convertSectionToCanvas(block))}
              className="mr-1 flex items-center gap-1 rounded-md border border-zinc-700 px-2 py-1 text-[11px] font-medium text-zinc-300 hover:border-emerald-500 hover:text-emerald-400">
              <Wand2 className="h-3.5 w-3.5 text-amber-400" /> Customize freely
            </button>
          )}
          {premium && block.type !== 'canvas' && onCopyStyle && (
            <button type="button" onClick={onCopyStyle} title="Copy this section's design" className="hover:text-zinc-200"><Copy className="h-4 w-4" /></button>
          )}
          {premium && block.type !== 'canvas' && onPasteStyle && (
            <button type="button" onClick={onPasteStyle} disabled={!canPasteStyle} title="Paste design onto this section" className="hover:text-zinc-200 disabled:opacity-30"><ClipboardPaste className="h-4 w-4" /></button>
          )}
          {onDuplicate && (
            <button type="button" onClick={onDuplicate} title="Duplicate section" className="hover:text-zinc-200"><CopyPlus className="h-4 w-4" /></button>
          )}
          <button type="button" onClick={() => onMove(-1)} disabled={index === 0} className="hover:text-zinc-200 disabled:opacity-30"><ChevronUp className="h-4 w-4" /></button>
          <button type="button" onClick={() => onMove(1)} disabled={index === total - 1} className="hover:text-zinc-200 disabled:opacity-30"><ChevronDown className="h-4 w-4" /></button>
          <button type="button" onClick={onRemove} className="hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
          <button type="button" onClick={() => setOpen((o) => !o)} className="hover:text-zinc-200">{open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}</button>
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
