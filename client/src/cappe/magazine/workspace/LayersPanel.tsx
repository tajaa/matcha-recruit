import { useState, type DragEvent } from 'react'
import {
  ChevronDown, ChevronRight, Eye, EyeOff, FileImage, Group, Image as ImageIcon, Images, LayoutTemplate, Lock, Minus, Quote, Square,
  StickyNote, Type, Unlock, MessagesSquare, Lock as Paywall, Text as TextIcon,
} from 'lucide-react'
import type { CappeAsset, StoryBlock } from '../../types'
import type { FrameTarget } from '../canvas/bridge'
import { rtText } from '../canvas/rt'
import { BLOCK_LABELS, textPreview } from '../editor/blocks'
import { designOf, type ArtAt } from '../design/designOps'
import type { Design, Layer } from '../design/types'

const BLOCK_ICON: Record<StoryBlock['type'], typeof Type> = {
  cover: LayoutTemplate, text: TextIcon, photo: ImageIcon, photos: Images, quote: Quote, sidebar: StickyNote, qa: MessagesSquare,
  divider: Minus, paywall: Paywall, page: FileImage,
}
const LAYER_ICON = { text: Type, image: ImageIcon, shape: Square, group: Group }

/** A layer's name in a list: its own, else its words or its kind. */
function layerLabel(l: Layer): string {
  if (l.name) return l.name
  if (l.kind === 'text') return rtText(l.rt).replace(/\s+/g, ' ').trim().slice(0, 40) || 'Words'
  return l.kind === 'image' ? 'Picture' : l.kind === 'group' ? 'Group' : l.shape === 'ellipse' ? 'Ellipse' : l.shape === 'line' ? 'Line' : 'Rectangle'
}

/** A block's name in the tree: its words, else its kind, numbered when the
 *  story has more than one of that kind ("Photo 2"). */
function blockLabel(blocks: StoryBlock[], i: number): string {
  const b = blocks[i]
  if (b.type === 'text') return textPreview(b.md, 6) || 'Text'
  if (b.type === 'quote') return b.text ? `“${b.text.slice(0, 30)}”` : 'Pull quote'
  if (b.type === 'sidebar') return b.title || 'Sidebar'
  const same = blocks.filter((x) => x.type === b.type)
  return same.length > 1 ? `${BLOCK_LABELS[b.type]} ${same.indexOf(b) + 1}` : BLOCK_LABELS[b.type]
}

type Drag = { kind: 'layer'; art: string; id: string } | { kind: 'block'; index: number }

/** One design's layers, the topmost first (as they stack on the page), to
 *  select, show or hide, lock, rename and drag into another order. */
export function LayerList({ design, art, selected, depth = 0, onSelect, onToggle, onRename, onMove }: {
  design: Design; art: ArtAt
  selected: string[]
  depth?: number
  onSelect: (ids: string[], add: boolean) => void
  onToggle: (id: string, key: 'hidden' | 'locked') => void
  onRename: (id: string, name: string) => void
  onMove: (id: string, target: string, where: 'above' | 'below') => void
}) {
  return <Layers layers={design.layers} art={art} selected={selected} depth={depth} onSelect={onSelect} onToggle={onToggle} onRename={onRename} onMove={onMove} />
}

let dragging: Drag | null = null

function Layers({ layers, art, selected, depth, onSelect, onToggle, onRename, onMove }: {
  layers: Layer[]; art: ArtAt; selected: string[]; depth: number
  onSelect: (ids: string[], add: boolean) => void
  onToggle: (id: string, key: 'hidden' | 'locked') => void
  onRename: (id: string, name: string) => void
  onMove: (id: string, target: string, where: 'above' | 'below') => void
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [naming, setNaming] = useState<string | null>(null)
  const [over, setOver] = useState<{ id: string; where: 'above' | 'below' } | null>(null)
  const artKey = `${art.block}:${art.item}`
  return (
    <ul role="group">
      {[...layers].reverse().map((l) => {
        const Icon = LAYER_ICON[l.kind]
        const isSel = selected.includes(l.id)
        const onDrop = (e: DragEvent) => {
          e.preventDefault()
          const d = dragging
          setOver(null)
          if (d?.kind === 'layer' && d.art === artKey && d.id !== l.id && over) onMove(d.id, l.id, over.where)
        }
        return (
          <li key={l.id} role="treeitem" aria-selected={isSel} aria-expanded={l.kind === 'group' ? !!open[l.id] : undefined}>
            <div draggable onDragStart={(e) => { dragging = { kind: 'layer', art: artKey, id: l.id }; e.dataTransfer.effectAllowed = 'move' }}
              onDragEnd={() => { dragging = null; setOver(null) }}
              onDragOver={(e) => {
                if (dragging?.kind !== 'layer' || dragging.art !== artKey) return
                e.preventDefault()
                const r = e.currentTarget.getBoundingClientRect()
                // The list runs top to bottom from the front: dropping on a row's top half puts it above (in front).
                const where = e.clientY < r.top + r.height / 2 ? 'above' : 'below'
                if (over?.id !== l.id || over.where !== where) setOver({ id: l.id, where })
              }}
              onDragLeave={() => setOver((o) => (o?.id === l.id ? null : o))} onDrop={onDrop}
              onClick={(e) => onSelect([l.id], e.shiftKey || e.metaKey)}
              className={`group relative flex h-7 cursor-default items-center gap-1 rounded pr-1 text-xs ${isSel ? 'bg-emerald-500/15 text-emerald-200' : 'text-zinc-300 hover:bg-zinc-800/70'} ${l.hidden ? 'opacity-50' : ''}`}
              style={{ paddingLeft: 8 + depth * 12 }}>
              {over?.id === l.id && <span className={`pointer-events-none absolute inset-x-1 h-0.5 bg-emerald-400 ${over.where === 'above' ? 'top-0' : 'bottom-0'}`} />}
              {l.kind === 'group'
                ? <button type="button" aria-label={open[l.id] ? 'Fold' : 'Open'} onClick={(e) => { e.stopPropagation(); setOpen((o) => ({ ...o, [l.id]: !o[l.id] })) }}
                    className="text-zinc-500 hover:text-zinc-200">{open[l.id] ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}</button>
                : <span className="w-3" />}
              <Icon className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
              {naming === l.id ? (
                <input autoFocus defaultValue={l.name} aria-label="Layer name" onClick={(e) => e.stopPropagation()}
                  onBlur={(e) => { onRename(l.id, e.target.value.trim().slice(0, 60)); setNaming(null) }}
                  onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); if (e.key === 'Escape') setNaming(null) }}
                  className="h-5 min-w-0 flex-1 rounded border border-emerald-500 bg-zinc-950 px-1 text-xs text-zinc-100 outline-none" />
              ) : (
                <span className="min-w-0 flex-1 truncate" onDoubleClick={(e) => { e.stopPropagation(); setNaming(l.id) }} title="Double-click to rename">{layerLabel(l)}</span>
              )}
              <button type="button" aria-label={l.locked ? 'Unlock' : 'Lock'} title={l.locked ? 'Unlock' : 'Lock'} onClick={(e) => { e.stopPropagation(); onToggle(l.id, 'locked') }}
                className={`${l.locked ? 'text-zinc-300' : 'text-zinc-600 opacity-0 group-hover:opacity-100'} hover:text-zinc-100`}>
                {l.locked ? <Lock className="h-3 w-3" /> : <Unlock className="h-3 w-3" />}
              </button>
              <button type="button" aria-label={l.hidden ? 'Show' : 'Hide'} title={l.hidden ? 'Show' : 'Hide'} onClick={(e) => { e.stopPropagation(); onToggle(l.id, 'hidden') }}
                className={`${l.hidden ? 'text-zinc-300' : 'text-zinc-600 opacity-0 group-hover:opacity-100'} hover:text-zinc-100`}>
                {l.hidden ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
              </button>
            </div>
            {l.kind === 'group' && open[l.id] && (
              <Layers layers={l.children} art={art} selected={selected} depth={depth + 1} onSelect={onSelect} onToggle={onToggle} onRename={onRename} onMove={onMove} />
            )}
          </li>
        )
      })}
    </ul>
  )
}

/** The whole story as a tree: its blocks in reading order (drag to reorder),
 *  each picture's layers under it. */
export default function LayersPanel({ blocks, target, story, assets, onSelect, onToggle, onRename, onMoveLayer, onMoveBlock }: {
  blocks: StoryBlock[]
  target: FrameTarget | null
  story: string
  assets: Map<string, CappeAsset>
  onSelect: (t: FrameTarget) => void
  onToggle: (art: ArtAt, id: string, key: 'hidden' | 'locked') => void
  onRename: (art: ArtAt, id: string, name: string) => void
  onMoveLayer: (art: ArtAt, id: string, target: string, where: 'above' | 'below') => void
  onMoveBlock: (from: number, to: number) => void
}) {
  const [over, setOver] = useState<number | null>(null)
  const selIds = target?.kind === 'layer' ? target.ids : []
  const designRows = (b: StoryBlock, i: number, item: number | null) => {
    const d = designOf(b, item)
    if (!d?.layers.length) return null
    const art = { block: i, item }
    const sel = target?.kind === 'layer' && target.block === i && target.item === item ? selIds : []
    return (
      <LayerList design={d} art={art} selected={sel} depth={item === null ? 1 : 2}
        onSelect={(ids, add) => onSelect({ kind: 'layer', story, block: i, item, ids: add && sel.length ? [...new Set([...sel, ...ids])] : ids })}
        onToggle={(id, key) => onToggle(art, id, key)} onRename={(id, name) => onRename(art, id, name)}
        onMove={(id, to, where) => onMoveLayer(art, id, to, where)} />
    )
  }
  return (
    <div className="p-2">
      <ul role="tree" aria-label="The story’s layers">
        {blocks.map((b, i) => {
          const Icon = BLOCK_ICON[b.type]
          const isSel = target?.kind === 'block' && target.block === i && target.item === undefined
          return (
            <li key={i} role="treeitem" aria-selected={isSel}>
              <div draggable={b.type !== 'cover'}
                onDragStart={(e) => { dragging = { kind: 'block', index: i }; e.dataTransfer.effectAllowed = 'move' }}
                onDragEnd={() => { dragging = null; setOver(null) }}
                onDragOver={(e) => { if (dragging?.kind === 'block' && b.type !== 'cover') { e.preventDefault(); setOver(i) } }}
                onDragLeave={() => setOver((o) => (o === i ? null : o))}
                onDrop={(e) => {
                  e.preventDefault()
                  setOver(null)
                  if (dragging?.kind === 'block' && dragging.index !== i && b.type !== 'cover') onMoveBlock(dragging.index, i)
                }}
                onClick={() => onSelect({ kind: 'block', story, block: i })}
                className={`flex h-7 cursor-default items-center gap-1.5 rounded px-2 text-xs ${isSel ? 'bg-emerald-500/15 text-emerald-200' : 'text-zinc-200 hover:bg-zinc-800/70'} ${over === i ? 'ring-1 ring-emerald-500' : ''}`}>
                <Icon className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
                <span className="min-w-0 flex-1 truncate">{blockLabel(blocks, i)}</span>
                {'asset_id' in b && b.asset_id && assets.get(b.asset_id)?.url && (
                  <img src={assets.get(b.asset_id)!.variants?.webp?.[0]?.url || assets.get(b.asset_id)!.url} alt="" className="h-4 w-6 rounded-sm object-cover" />
                )}
              </div>
              {designRows(b, i, null)}
              {b.type === 'photos' && b.items.map((it, j) => (
                <div key={j}>
                  <div onClick={() => onSelect({ kind: 'block', story, block: i, item: j })}
                    className={`flex h-6 cursor-default items-center gap-1.5 rounded pl-6 pr-2 text-[11px] ${target?.kind === 'block' && target.block === i && target.item === j ? 'bg-emerald-500/15 text-emerald-200' : 'text-zinc-400 hover:bg-zinc-800/70'}`}>
                    <ImageIcon className="h-3 w-3 shrink-0 text-zinc-600" /> Picture {j + 1}{!it.asset_id && ' (empty)'}
                  </div>
                  {designRows(b, i, j)}
                </div>
              ))}
            </li>
          )
        })}
      </ul>
      <p className="mt-3 px-2 text-[11px] leading-relaxed text-zinc-500">Drag blocks to reorder the story, and layers to stack them. Double-click a layer to rename it.</p>
    </div>
  )
}
