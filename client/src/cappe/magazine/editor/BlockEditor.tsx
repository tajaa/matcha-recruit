import { ArrowDown, ArrowUp, Copy, GripVertical, Trash2 } from 'lucide-react'
import type { DragEvent } from 'react'
import { ui } from '../../components/ui'
import type { CappeAsset, StoryBlock } from '../../types'
import { BLOCK_LABELS, canDuplicate } from './blocks'
import BlockOptions from './BlockOptions'

export default function BlockEditor({ block, index, count, assets, onChange, onMove, onRemove, onDuplicate, onPickAsset, onDragStart }: {
  block: StoryBlock
  index: number
  count: number
  assets: Map<string, CappeAsset>
  onChange: (block: StoryBlock) => void
  onMove: (delta: -1 | 1) => void
  onRemove: () => void
  onDuplicate?: () => void
  /** The grip was picked up: the story editor moves the block where it's dropped. */
  onDragStart?: (e: DragEvent) => void
  /** Open the picker; `done(asset)` is called with the choice. */
  onPickAsset: (done: (asset: CappeAsset) => void) => void
}) {
  return (
    <section className={`${ui.card} p-4`} aria-label={`${BLOCK_LABELS[block.type]} block`}>
      <div className="mb-3 flex items-center gap-2">
        {onDragStart && block.type !== 'cover' && (
          <span draggable onDragStart={onDragStart} title="Drag to move" aria-hidden
            className="-ml-1 cursor-grab rounded p-0.5 text-zinc-600 hover:bg-zinc-800 hover:text-zinc-300 active:cursor-grabbing">
            <GripVertical className="h-4 w-4" />
          </span>
        )}
        <span className="text-xs font-semibold uppercase tracking-widest text-zinc-400">{BLOCK_LABELS[block.type]}</span>
        <div className="ml-auto flex gap-1">
          <button type="button" aria-label="Move up" disabled={index === 0 || block.type === 'cover'} onClick={() => onMove(-1)}
            className="rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200 disabled:opacity-30"><ArrowUp className="h-4 w-4" /></button>
          <button type="button" aria-label="Move down" disabled={index >= count - 1} onClick={() => onMove(1)}
            className="rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200 disabled:opacity-30"><ArrowDown className="h-4 w-4" /></button>
          {onDuplicate && canDuplicate(block) && (
            <button type="button" aria-label="Duplicate block" title="Duplicate" onClick={onDuplicate}
              className="rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"><Copy className="h-4 w-4" /></button>
          )}
          <button type="button" aria-label="Remove block" onClick={onRemove}
            className="rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
        </div>
      </div>
      <BlockOptions block={block} assets={assets} onChange={onChange} onPickAsset={onPickAsset} />
    </section>
  )
}
