import { ArrowDown, ArrowUp, Copy, GripVertical, ImagePlus, Trash2 } from 'lucide-react'
import type { DragEvent } from 'react'
import { ui } from '../../components/ui'
import type { CappeAsset, StoryBlock } from '../../types'
import { BLOCK_LABELS, canDuplicate } from './blocks'
import MarkdownField from './MarkdownField'
import PictureSlot from './PictureSlot'
import PhotoDesigner from './PhotoDesigner'

const small = 'rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm text-zinc-100'

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
  const body = (() => {
    switch (block.type) {
      case 'cover':
        return (
          <div className="space-y-3">
            <PictureSlot assetId={block.asset_id} assets={assets} label="Cover picture"
              onPick={() => onPickAsset((a) => onChange({ ...block, asset_id: a.id }))}
              onClear={() => onChange({ ...block, asset_id: null })} />
            <div className="flex flex-wrap gap-3 text-sm">
              <label className="flex items-center gap-2 text-zinc-300">Style
                <select value={block.style} onChange={(e) => onChange({ ...block, style: e.target.value as typeof block.style })} className={small}>
                  <option value="overlay">Headline over the picture</option>
                  <option value="stacked">Headline, then the picture</option>
                  <option value="split">Side by side</option>
                </select>
              </label>
              {block.style === 'overlay' && (
                <label className="flex items-center gap-2 text-zinc-300">Words
                  <select value={block.tone} onChange={(e) => onChange({ ...block, tone: e.target.value as typeof block.tone })} className={small}>
                    <option value="light">White on dark</option>
                    <option value="dark">Dark on light</option>
                  </select>
                </label>
              )}
              {block.style !== 'stacked' && (
                <label className="flex items-center gap-2 text-zinc-300">Focus
                  <input type="range" min={0} max={100} value={block.focal.x} aria-label="Focus left to right"
                    onChange={(e) => onChange({ ...block, focal: { ...block.focal, x: Number(e.target.value) } })} />
                  <input type="range" min={0} max={100} value={block.focal.y} aria-label="Focus top to bottom"
                    onChange={(e) => onChange({ ...block, focal: { ...block.focal, y: Number(e.target.value) } })} />
                </label>
              )}
            </div>
          </div>
        )
      case 'text':
        return (
          <div className="space-y-2">
            <MarkdownField value={block.md} onChange={(md) => onChange({ ...block, md })} label="Text"
              placeholder="Write here. Select words and use the bar above, or type Markdown: **bold**, *italic*, ## heading, > quote, - list" />
            <div className="flex flex-wrap gap-3 text-sm text-zinc-300">
              <label className="flex items-center gap-2">Style
                <select value={block.variant || 'body'} onChange={(e) => onChange({ ...block, variant: e.target.value as typeof block.variant })} className={small}>
                  <option value="body">Paragraphs</option>
                  <option value="lede">Lede (larger opening)</option>
                  <option value="statement">Statement (big, in the headline type)</option>
                  <option value="small">Small print</option>
                </select>
              </label>
              <label className="flex items-center gap-2">Columns
                <select value={block.columns} onChange={(e) => onChange({ ...block, columns: Number(e.target.value) as typeof block.columns })} className={small}>
                  <option value={1}>One</option><option value={2}>Two</option><option value={3}>Three</option>
                </select>
              </label>
              <label className="flex items-center gap-2">Align
                <select value={block.align || 'left'} onChange={(e) => onChange({ ...block, align: e.target.value as typeof block.align })} className={small}>
                  <option value="left">Left</option><option value="center">Centred</option><option value="right">Right</option><option value="justify">Justified</option>
                </select>
              </label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={block.dropcap} onChange={(e) => onChange({ ...block, dropcap: e.target.checked })} /> Drop cap</label>
            </div>
          </div>
        )
      case 'photo':
        return (
          <div className="space-y-3">
            <PictureSlot assetId={block.asset_id} assets={assets}
              onPick={() => onPickAsset((a) => onChange({ ...block, asset_id: a.id }))}
              onClear={() => onChange({ ...block, asset_id: null })} />
            <div className="flex flex-wrap gap-3">
              <input value={block.caption} onChange={(e) => onChange({ ...block, caption: e.target.value })} maxLength={500}
                placeholder="Caption for this story (the credit comes from the library)" className={`${ui.input} flex-1`} />
              <select value={block.size} onChange={(e) => onChange({ ...block, size: e.target.value as typeof block.size })} className={small} aria-label="Size">
                <option value="column">Column width</option>
                <option value="wide">Wide</option>
                <option value="full">Edge to edge</option>
              </select>
            </div>
            {block.asset_id && assets.get(block.asset_id) && (
              <PhotoDesigner block={block} asset={assets.get(block.asset_id)!} onChange={onChange} />
            )}
          </div>
        )
      case 'photos':
        return (
          <div className="space-y-3">
            <label className="flex items-center gap-2 text-sm text-zinc-300">Arrangement
              <select value={block.layout} onChange={(e) => onChange({ ...block, layout: e.target.value as typeof block.layout })} className={small}>
                <option value="pair">Pair</option>
                <option value="trio">Trio</option>
                <option value="grid">Grid</option>
                <option value="mosaic">Mosaic</option>
              </select>
            </label>
            {block.items.map((item, i) => (
              <div key={i} className="flex flex-col gap-2 rounded-lg border border-zinc-800 p-2 sm:flex-row sm:items-center">
                <div className="flex-1">
                  <PictureSlot assetId={item.asset_id} assets={assets} label={`Picture ${i + 1}`}
                    onPick={() => onPickAsset((a) => onChange({ ...block, items: block.items.map((x, j) => (j === i ? { ...x, asset_id: a.id } : x)) }))}
                    onClear={() => onChange({ ...block, items: block.items.map((x, j) => (j === i ? { ...x, asset_id: null } : x)) })} />
                </div>
                <input value={item.caption} onChange={(e) => onChange({ ...block, items: block.items.map((x, j) => (j === i ? { ...x, caption: e.target.value } : x)) })}
                  maxLength={300} placeholder="Caption" className={`${ui.input} sm:w-56`} />
                <button type="button" aria-label={`Remove picture ${i + 1}`} onClick={() => onChange({ ...block, items: block.items.filter((_, j) => j !== i) })}
                  className="text-zinc-500 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
              </div>
            ))}
            {block.items.length < 12 && (
              <button type="button" className={ui.btnGhost} onClick={() => onChange({ ...block, items: [...block.items, { asset_id: null, caption: '' }] })}>
                <ImagePlus className="h-4 w-4" /> Add a picture
              </button>
            )}
          </div>
        )
      case 'quote':
        return (
          <div className="space-y-2">
            <textarea value={block.text} onChange={(e) => onChange({ ...block, text: e.target.value })} rows={2} maxLength={400}
              placeholder="The words to pull out" className={ui.input} />
            <div className="flex flex-wrap gap-3">
              <input value={block.attribution} onChange={(e) => onChange({ ...block, attribution: e.target.value })} maxLength={120}
                placeholder="Who said it" className={`${ui.input} flex-1`} />
              <select value={block.style} onChange={(e) => onChange({ ...block, style: e.target.value as typeof block.style })} className={small} aria-label="Quote style">
                <option value="big">Big, centred</option>
                <option value="side">Ruled, in the column</option>
              </select>
            </div>
          </div>
        )
      case 'sidebar':
        return (
          <div className="space-y-2">
            <input value={block.title} onChange={(e) => onChange({ ...block, title: e.target.value })} maxLength={120} placeholder="Sidebar title" className={ui.input} />
            <MarkdownField value={block.md} onChange={(md) => onChange({ ...block, md })} rows={4} label="Sidebar" placeholder="Facts, a timeline, where to go" />
          </div>
        )
      case 'qa':
        return (
          <div className="space-y-3">
            {block.items.map((item, i) => (
              <div key={i} className="space-y-2 rounded-lg border border-zinc-800 p-2">
                <div className="flex gap-2">
                  <input value={item.q} onChange={(e) => onChange({ ...block, items: block.items.map((x, j) => (j === i ? { ...x, q: e.target.value } : x)) })}
                    maxLength={500} placeholder="Question" className={`${ui.input} flex-1`} />
                  <button type="button" aria-label={`Remove question ${i + 1}`} onClick={() => onChange({ ...block, items: block.items.filter((_, j) => j !== i) })}
                    className="text-zinc-500 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
                </div>
                <MarkdownField value={item.a_md} onChange={(a_md) => onChange({ ...block, items: block.items.map((x, j) => (j === i ? { ...x, a_md } : x)) })}
                  rows={3} label={`Answer ${i + 1}`} placeholder="Answer" />
              </div>
            ))}
            {block.items.length < 40 && (
              <button type="button" className={ui.btnGhost} onClick={() => onChange({ ...block, items: [...block.items, { q: '', a_md: '' }] })}>Add a question</button>
            )}
          </div>
        )
      case 'divider':
        return <p className="text-xs text-zinc-500">A short rule between parts of the story.</p>
      case 'paywall':
        return <p className="text-xs text-zinc-500">Everything below this line is for subscribers, when the story is set to “Subscribers”. Readers see what’s above it free.</p>
    }
  })()

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
      {body}
    </section>
  )
}
