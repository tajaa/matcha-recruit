import { ArrowDown, ArrowUp, Circle, Copy, Image as ImageIcon, Minus, Square, Trash2, Type } from 'lucide-react'
import type { CappeAsset, StoryBlock } from '../../types'
import { PanelHead } from '../canvas/BlockPanel'
import BlockOptions from '../editor/BlockOptions'
import PictureSlot from '../editor/PictureSlot'
import { BLOCK_LABELS, canDuplicate } from '../editor/blocks'
import { designOf, TEXT_PRESETS, type ArtAt, type TextPreset } from '../design/designOps'
import { PAGE_ASPECTS, type Design, type PageAspect, type Paint, type ShapeKind } from '../design/types'
import { IconBtn, PaintField, Section, Seg } from './controls'
import { LayerList } from './LayersPanel'

const ICON = 'rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200 disabled:opacity-30'
const TILE = 'flex h-14 flex-col items-center justify-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 text-[11px] text-zinc-300 hover:border-zinc-600 hover:text-zinc-50 disabled:opacity-40'
const WHITE: Paint = { kind: 'solid', color: '#ffffff', angle: 180, stops: [] }

export type ArtHandlers = {
  onText: (preset: TextPreset) => void
  onShape: (shape: ShapeKind, square?: boolean) => void
  /** Choose a library picture to lay on it. */
  onImage: () => void
  onSelectLayers: (ids: string[], add: boolean) => void
  onToggle: (id: string, key: 'hidden' | 'locked') => void
  onRename: (id: string, name: string) => void
  onMoveLayer: (id: string, target: string, where: 'above' | 'below') => void
}

/** A picture or a designed page in hand: what can be laid on it, what is on
 *  it already, and its own settings (the picture, its crop and frame; a
 *  page's shape and background). */
export default function ArtInspector({ blocks, art, assets, accent, handlers, onBlock, onMove, onDuplicate, onRemove, onPickAsset, onClose, onWhole }: {
  blocks: StoryBlock[]
  art: ArtAt
  assets: Map<string, CappeAsset>
  accent: string
  handlers: ArtHandlers
  onBlock: (b: StoryBlock) => void
  onMove: (delta: -1 | 1) => void
  onDuplicate: () => void
  onRemove: () => void
  onPickAsset: (done: (a: CappeAsset) => void) => void
  onClose: () => void
  /** A photo group's picture: select the group as a whole. */
  onWhole: () => void
}) {
  const block = blocks[art.block]
  if (!block) return null
  const design: Design | null = designOf(block, art.item)
  const item = art.item !== null && block.type === 'photos' ? block.items[art.item] : null
  const hasPicture = block.type === 'page' || !!(item ? item.asset_id : 'asset_id' in block && block.asset_id)
  const title = item ? `Picture ${art.item! + 1} of the group` : BLOCK_LABELS[block.type]
  const on = block.type === 'page' ? 'this page' : 'this picture'
  return (
    <div>
      <PanelHead title={title} onClose={onClose}>
        {item ? (
          <button type="button" className={`${ICON} hover:text-red-400`} aria-label="Remove this picture" title="Remove this picture"
            onClick={() => block.type === 'photos' && onBlock({ ...block, items: block.items.filter((_, j) => j !== art.item) })}>
            <Trash2 className="h-4 w-4" />
          </button>
        ) : (
          <>
            <button type="button" className={ICON} aria-label="Move up" disabled={block.type === 'cover' || art.block <= (blocks[0]?.type === 'cover' ? 1 : 0)} onClick={() => onMove(-1)}><ArrowUp className="h-4 w-4" /></button>
            <button type="button" className={ICON} aria-label="Move down" disabled={block.type === 'cover' || art.block >= blocks.length - 1} onClick={() => onMove(1)}><ArrowDown className="h-4 w-4" /></button>
            {canDuplicate(block) && <button type="button" className={ICON} aria-label="Duplicate block" title="Duplicate" onClick={onDuplicate}><Copy className="h-4 w-4" /></button>}
            <button type="button" className={`${ICON} hover:text-red-400`} aria-label="Remove block" title="Remove" onClick={onRemove}><Trash2 className="h-4 w-4" /></button>
          </>
        )}
      </PanelHead>

      <Section title={`Add to ${on}`}>
        {!hasPicture && <p className="text-[11px] text-zinc-500">Choose the picture first; then words, shapes and pictures go on it.</p>}
        <div className="grid grid-cols-3 gap-1.5">
          {(['heading', 'subheading', 'body'] as const).map((p) => (
            <button key={p} type="button" className={TILE} disabled={!hasPicture} onClick={() => handlers.onText(p)} aria-label={`Add ${TEXT_PRESETS[p].label.toLowerCase()}`}>
              <Type className={p === 'heading' ? 'h-5 w-5' : p === 'subheading' ? 'h-4 w-4' : 'h-3 w-3'} />{TEXT_PRESETS[p].label}
            </button>
          ))}
          <button type="button" className={TILE} disabled={!hasPicture} onClick={() => handlers.onShape('rect')} aria-label="Add a rectangle"><Square className="h-4 w-4" />Rectangle</button>
          <button type="button" className={TILE} disabled={!hasPicture} onClick={() => handlers.onShape('ellipse', true)} aria-label="Add a circle"><Circle className="h-4 w-4" />Circle</button>
          <button type="button" className={TILE} disabled={!hasPicture} onClick={() => handlers.onShape('line')} aria-label="Add a line"><Minus className="h-4 w-4" />Line</button>
        </div>
        <button type="button" className={`${TILE} h-9 w-full flex-row`} disabled={!hasPicture} onClick={handlers.onImage}>
          <ImageIcon className="h-4 w-4" /> {block.type === 'page' ? 'Lay a picture on this page' : 'Lay another picture on this one'}
        </button>
      </Section>

      <Section title="On it">
        {design?.layers.length ? (
          <div className="-mx-2">
            <LayerList design={design} art={art} selected={[]} onSelect={handlers.onSelectLayers} onToggle={handlers.onToggle}
              onRename={handlers.onRename} onMove={handlers.onMoveLayer} />
          </div>
        ) : <p className="text-[11px] text-zinc-500">Nothing yet. Add something above, or paste layers copied from another picture.</p>}
      </Section>

      {block.type === 'page' ? (
        <Section title="Page">
          <Seg label="Shape" value={block.aspect} onChange={(aspect: PageAspect) => onBlock({ ...block, aspect })}
            options={(Object.keys(PAGE_ASPECTS) as PageAspect[]).map((k) => ({ key: k, label: k }))} />
          <p className="text-[11px] text-zinc-500">The page’s shape, width to height. It is fitted to the book’s page.</p>
          <h4 className="pt-1 text-[11px] text-zinc-400">Background</h4>
          <PaintField value={block.design.background ?? WHITE} accent={accent}
            onChange={(background) => onBlock({ ...block, design: { ...block.design, background } })} />
        </Section>
      ) : item && block.type === 'photos' ? (
        <Section title="Picture">
          <PictureSlot assetId={item.asset_id} assets={assets} label={`Picture ${art.item! + 1}`}
            onPick={() => onPickAsset((a) => onBlock({ ...block, items: block.items.map((x, j) => (j === art.item ? { ...x, asset_id: a.id } : x)) }))}
            onClear={() => onBlock({ ...block, items: block.items.map((x, j) => (j === art.item ? { ...x, asset_id: null } : x)) })} />
          <p className="text-[11px] text-zinc-500">Type its caption under it on the page.</p>
          <IconBtn title="The whole photo group" onClick={onWhole}><span>The whole group: arrangement and pictures</span></IconBtn>
        </Section>
      ) : (
        <BlockOptions block={block} assets={assets} accent={accent} onChange={onBlock} onPickAsset={onPickAsset} />
      )}
    </div>
  )
}
