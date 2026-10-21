import { ArrowDown, ArrowUp, Copy, Trash2, X } from 'lucide-react'
import type { ReactNode } from 'react'
import type { CappeAsset, StoryBlock } from '../../types'
import BlockOptions from '../editor/BlockOptions'
import { BLOCK_LABELS, canDuplicate } from '../editor/blocks'

const ICON = 'rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200 disabled:opacity-30'

/** The panel's heading for what is selected, with a way to let it go. */
export function PanelHead({ title, onClose, children }: { title: string; onClose?: () => void; children?: ReactNode }) {
  return (
    <div className="flex items-center gap-1 border-b border-zinc-800 px-4 py-3">
      <h2 className="mr-auto text-xs font-semibold uppercase tracking-widest text-zinc-400">{title}</h2>
      {children}
      {onClose && (
        <button type="button" className={ICON} onClick={onClose} aria-label="Deselect" title="Deselect (Esc)"><X className="h-4 w-4" /></button>
      )}
    </div>
  )
}

/** The block selected on the page: move, copy or delete it, and its pictures
 *  and look (its words are typed on the page). */
export default function BlockPanel({ block, index, count, assets, onChange, onMove, onDuplicate, onRemove, onPickAsset, onClose }: {
  block: StoryBlock
  index: number
  count: number
  assets: Map<string, CappeAsset>
  onChange: (block: StoryBlock) => void
  onMove: (delta: -1 | 1) => void
  onDuplicate: () => void
  onRemove: () => void
  onPickAsset: (done: (asset: CappeAsset) => void) => void
  onClose: () => void
}) {
  const cover = block.type === 'cover'
  return (
    <div>
      <PanelHead title={BLOCK_LABELS[block.type]} onClose={onClose}>
        <button type="button" className={ICON} aria-label="Move up" disabled={cover || index === 0}
          onClick={() => onMove(-1)}><ArrowUp className="h-4 w-4" /></button>
        <button type="button" className={ICON} aria-label="Move down" disabled={cover || index >= count - 1}
          onClick={() => onMove(1)}><ArrowDown className="h-4 w-4" /></button>
        {canDuplicate(block) && (
          <button type="button" className={ICON} aria-label="Duplicate block" title="Duplicate" onClick={onDuplicate}><Copy className="h-4 w-4" /></button>
        )}
        <button type="button" className={`${ICON} hover:text-red-400`} aria-label="Remove block" title="Remove (Delete)" onClick={onRemove}>
          <Trash2 className="h-4 w-4" />
        </button>
      </PanelHead>
      <div className="p-4">
        <BlockOptions block={block} assets={assets} onChange={onChange} onPickAsset={onPickAsset} words={false} />
      </div>
    </div>
  )
}
