import { useMemo, useState, type ReactNode } from 'react'
import {
  Circle, FileImage, Image as ImageIcon, Images, LayoutTemplate, Lock, MessagesSquare, Minus, Quote, Search, Square, StickyNote, Text as TextIcon,
  Upload, RectangleHorizontal,
} from 'lucide-react'
import type { CappeAsset, StoryBlock } from '../../types'
import { thumbUrl } from '../library/assets'
import { TEXT_PRESETS, type TextPreset } from '../design/designOps'
import { PAGE_ASPECTS, type PageAspect, type ShapeKind } from '../design/types'

/** The workspace's left panels: what can be added, where it goes. Words,
 *  shapes and pictures go ON the picture or page in hand; blocks go into the
 *  story after the block in hand. */

const TILE = 'flex flex-col items-center justify-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 p-2 text-[11px] text-zinc-300 hover:border-zinc-600 hover:text-zinc-50 disabled:cursor-not-allowed disabled:opacity-40'

function Group({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="border-b border-zinc-800 p-3">
      <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-zinc-400">{title}</h3>
      {hint && <p className="mb-2 text-[11px] leading-snug text-zinc-500">{hint}</p>}
      {children}
    </section>
  )
}

const NO_ART = 'Select a picture or a designed page first (click it on the page).'

/** How each preset reads in the list. */
const PRESET_LOOK: Record<TextPreset, string> = {
  heading: 'text-2xl font-bold leading-tight font-serif', subheading: 'text-lg font-semibold leading-tight font-serif',
  body: 'text-sm', caption: 'text-xs font-medium', kicker: 'text-[11px] font-bold uppercase tracking-[0.2em]',
}

function BlockTile({ icon, label, onClick }: { icon: ReactNode; label: string; onClick: () => void }) {
  return <button type="button" className={`${TILE} h-16`} onClick={onClick} aria-label={`Add ${label.toLowerCase()} to the story`}>{icon}{label}</button>
}

export function TextPanel({ canArt, onText, onBlock }: {
  canArt: boolean
  onText: (preset: TextPreset) => void
  onBlock: (type: StoryBlock['type']) => void
}) {
  return (
    <div>
      <Group title="Words on a picture or page" hint={canArt ? 'Click a style to put it on what is selected; then type in it on the page.' : NO_ART}>
        <div className="space-y-1.5">
          {(Object.keys(TEXT_PRESETS) as TextPreset[]).map((p) => (
            <button key={p} type="button" disabled={!canArt} onClick={() => onText(p)} aria-label={`Add ${TEXT_PRESETS[p].label.toLowerCase()}`}
              className="block w-full rounded-md border border-zinc-800 bg-zinc-900 px-3 py-2 text-left text-zinc-100 hover:border-zinc-600 disabled:cursor-not-allowed disabled:opacity-40">
              <span className={PRESET_LOOK[p]}>{TEXT_PRESETS[p].label}</span>
            </button>
          ))}
        </div>
      </Group>
      <Group title="Text in the story" hint="Added after what is selected.">
        <div className="grid grid-cols-2 gap-1.5">
          <BlockTile icon={<TextIcon className="h-4 w-4" />} label="Text" onClick={() => onBlock('text')} />
          <BlockTile icon={<Quote className="h-4 w-4" />} label="Pull quote" onClick={() => onBlock('quote')} />
          <BlockTile icon={<StickyNote className="h-4 w-4" />} label="Sidebar" onClick={() => onBlock('sidebar')} />
          <BlockTile icon={<MessagesSquare className="h-4 w-4" />} label="Q & A" onClick={() => onBlock('qa')} />
        </div>
      </Group>
    </div>
  )
}

export function PhotosPanel({ assets, canArt, onUse, onMore }: {
  assets: CappeAsset[]
  /** A picture or page is in hand: a picture goes on it; else into the story. */
  canArt: boolean
  onUse: (a: CappeAsset) => void
  /** The library: upload, find free pictures, illustrate. */
  onMore: () => void
}) {
  const [q, setQ] = useState('')
  const shown = useMemo(() => {
    const t = q.trim().toLowerCase()
    return assets.filter((a) => (a.mime ? a.mime.startsWith('image/') : true) && a.moderation !== 'blocked')
      .filter((a) => !t || `${a.title || ''} ${a.alt || ''} ${a.creator || ''}`.toLowerCase().includes(t))
  }, [assets, q])
  return (
    <div>
      <Group title="Pictures" hint={canArt ? 'Click one to lay it on what is selected.' : 'Click one to add it to the story as a photo, after what is selected.'}>
        <button type="button" onClick={onMore} className="mb-2 flex h-9 w-full items-center justify-center gap-2 rounded-md bg-emerald-600 text-xs font-medium text-white hover:bg-emerald-500">
          <Upload className="h-4 w-4" /> Upload or find pictures
        </button>
        <label className="mb-2 flex items-center gap-2 rounded-md border border-zinc-800 bg-zinc-950 px-2">
          <Search className="h-3.5 w-3.5 text-zinc-500" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search your library" aria-label="Search your library"
            className="h-7 min-w-0 flex-1 bg-transparent text-xs text-zinc-100 outline-none" />
        </label>
        {shown.length ? (
          <ul className="grid grid-cols-2 gap-1.5" aria-label="Your pictures">
            {shown.map((a) => (
              <li key={a.id}>
                <button type="button" onClick={() => onUse(a)} title={a.title || a.alt || 'Picture'} aria-label={`Use ${a.title || a.alt || 'this picture'}`}
                  className="block aspect-square w-full overflow-hidden rounded-md border border-zinc-800 hover:border-emerald-500">
                  <img src={thumbUrl(a)} alt={a.alt || ''} loading="lazy" className="h-full w-full object-cover" />
                </button>
              </li>
            ))}
          </ul>
        ) : <p className="text-[11px] text-zinc-500">{q ? 'No picture matches.' : 'No pictures yet. Upload some, or find free ones.'}</p>}
      </Group>
    </div>
  )
}

export function ElementsPanel({ canArt, onShape, onPage, onBlock, withCover, withPaywall }: {
  canArt: boolean
  onShape: (shape: ShapeKind, square?: boolean) => void
  onPage: (aspect: PageAspect) => void
  onBlock: (type: StoryBlock['type']) => void
  withCover: boolean
  withPaywall: boolean
}) {
  return (
    <div>
      <Group title="Shapes" hint={canArt ? 'Added on what is selected.' : NO_ART}>
        <div className="grid grid-cols-3 gap-1.5">
          <button type="button" className={`${TILE} h-16`} disabled={!canArt} onClick={() => onShape('rect')} aria-label="Add a rectangle"><RectangleHorizontal className="h-5 w-5" />Rectangle</button>
          <button type="button" className={`${TILE} h-16`} disabled={!canArt} onClick={() => onShape('rect', true)} aria-label="Add a square"><Square className="h-5 w-5" />Square</button>
          <button type="button" className={`${TILE} h-16`} disabled={!canArt} onClick={() => onShape('line')} aria-label="Add a line"><Minus className="h-5 w-5" />Line</button>
          <button type="button" className={`${TILE} h-16`} disabled={!canArt} onClick={() => onShape('ellipse')} aria-label="Add an ellipse"><Circle className="h-5 w-5 scale-x-125" />Ellipse</button>
          <button type="button" className={`${TILE} h-16`} disabled={!canArt} onClick={() => onShape('ellipse', true)} aria-label="Add a circle"><Circle className="h-5 w-5" />Circle</button>
        </div>
      </Group>
      <Group title="Designed pages" hint="A page laid out freely: words, shapes and pictures anywhere on it. Added after what is selected.">
        <div className="grid grid-cols-4 gap-1.5">
          {(Object.keys(PAGE_ASPECTS) as PageAspect[]).map((k) => (
            <button key={k} type="button" className={`${TILE} h-20`} onClick={() => onPage(k)} aria-label={`Add a designed page, ${k}`}>
              <span className="block border border-zinc-500 bg-zinc-800" style={{ width: 28 * Math.min(1, PAGE_ASPECTS[k] / 0.8), aspectRatio: String(PAGE_ASPECTS[k]) }} />
              {k}
            </button>
          ))}
        </div>
      </Group>
      <Group title="Story blocks" hint="Added after what is selected.">
        <div className="grid grid-cols-2 gap-1.5">
          <BlockTile icon={<ImageIcon className="h-4 w-4" />} label="Photo" onClick={() => onBlock('photo')} />
          <BlockTile icon={<Images className="h-4 w-4" />} label="Photo group" onClick={() => onBlock('photos')} />
          <BlockTile icon={<Minus className="h-4 w-4" />} label="Divider" onClick={() => onBlock('divider')} />
          {withPaywall && <BlockTile icon={<Lock className="h-4 w-4" />} label="Paywall" onClick={() => onBlock('paywall')} />}
          {withCover && <BlockTile icon={<LayoutTemplate className="h-4 w-4" />} label="Cover" onClick={() => onBlock('cover')} />}
          <BlockTile icon={<FileImage className="h-4 w-4" />} label="Designed page" onClick={() => onPage('3:4')} />
        </div>
      </Group>
    </div>
  )
}
