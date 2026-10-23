import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { ChevronsLeft, Image as ImageIcon, Images, Search, Shapes, Type } from 'lucide-react'
import { graphicsApi, type GraphicBrowse, type GraphicGroup } from '../../model/graphics'
import { familyName } from '../../fonts/faces'
import { CHAR_DEFAULTS } from '../../model/limits'
import type { Doc } from '../../model/types'
import { useStudio, type AddTab } from '../../store/store'
import { useCtx } from '../context'
import { ELEMENT_GROUPS, ELEMENTS, TEXT_COMBOS, TEXT_STYLES, facesOf, type ElementSpec, type TextPart, type TextStyle } from './catalog'
import { endDrag, startDrag } from './drag'
import { GROUP_TITLE } from './graphicSearch'
import { GraphicGrid, GroupView, SearchResults } from './GraphicTiles'
import { PhotosTab, YourPicturesTab } from './PictureTabs'
import { addElement, addText } from './place'

const TABS: { key: AddTab; label: string; title: string; icon: ReactNode }[] = [
  { key: 'elements', label: 'Elements', title: 'Elements', icon: <Shapes className="h-5 w-5" /> },
  { key: 'text', label: 'Text', title: 'Text', icon: <Type className="h-5 w-5" /> },
  { key: 'photos', label: 'Photos', title: 'Free photos', icon: <ImageIcon className="h-5 w-5" /> },
  { key: 'uploads', label: 'Yours', title: 'Your pictures', icon: <Images className="h-5 w-5" /> },
]

/** The side panel, Canva's way: tabs down the far left, and beside them what
 *  each tab offers. Click a thing to put it in the middle of the page in
 *  view, or drag it to where it should go. */
export default function AddPanel() {
  const { store } = useCtx()
  const tab = useStudio(store, (s) => s.drawer)
  const open = TABS.find((t) => t.key === tab)
  return (
    <>
      <nav aria-label="Add to the page" className="flex w-[68px] shrink-0 flex-col items-center gap-1 border-r border-zinc-800 bg-zinc-950 py-2">
        {TABS.map((t) => (
          <button key={t.key} type="button" aria-pressed={tab === t.key} title={t.title}
            onClick={() => store.set({ drawer: tab === t.key ? null : t.key })}
            className={`flex w-14 flex-col items-center gap-1 rounded-lg py-2 text-[10px] ${tab === t.key ? 'bg-zinc-800 text-white' : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100'}`}>
            {t.icon}{t.label}
          </button>
        ))}
      </nav>
      {open && (
        <aside aria-label={open.title} className="flex w-[296px] shrink-0 flex-col border-r border-zinc-800 bg-zinc-900">
          <div className="flex items-center justify-between px-4 py-3">
            <h2 className="text-sm font-semibold text-zinc-100">{open.title}</h2>
            <button type="button" onClick={() => store.set({ drawer: null })} aria-label="Hide the side panel" title="Hide"
              className="rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-white"><ChevronsLeft className="h-4 w-4" /></button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
            {tab === 'elements' && <ElementsTab />}
            {tab === 'text' && <TextTab />}
            {tab === 'photos' && <PhotosTab />}
            {tab === 'uploads' && <YourPicturesTab />}
          </div>
        </aside>
      )}
    </>
  )
}

const HINT = 'text-[11px] leading-snug text-zinc-500'

// ── Elements ─────────────────────────────────────────────────────────────────

/** A small drawing of an element, as it would sit on a page. */
function ElementArt({ el, doc }: { el: ElementSpec; doc: Doc }) {
  const p = (el.patch ?? {}) as { fill?: string | null; stroke?: { c: string; w: number } | null; radius?: number }
  if (el.place) {
    const band = { page: [0, 0, 36, 46], top: [0, 0, 36, 10], bottom: [0, 36, 36, 10], side: [0, 0, 12, 46] }[el.place]
    return (
      <svg viewBox="0 0 36 46" className="h-10 w-8" aria-hidden>
        <rect x="0.5" y="0.5" width="35" height="45" fill="#fafaf9" stroke="#52525b" />
        <rect x={band[0]} y={band[1]} width={band[2]} height={band[3]} fill={el.kind === 'image' ? '#71717a' : (p.fill ?? '#d4d4d8')} />
      </svg>
    )
  }
  const { w, h } = el.size(doc)
  const k = 40 / Math.max(w, h, 1)
  const sw = Math.max(w * k, el.kind === 'line' ? 0 : 1), sh = Math.max(h * k, el.kind === 'line' ? 0 : 1)
  const x = (44 - sw) / 2, y = (44 - sh) / 2
  const stroke = p.stroke ? { stroke: p.stroke.c === '#1a1a1a' ? '#e4e4e7' : p.stroke.c, strokeWidth: Math.max(1, p.stroke.w * 0.75) } : {}
  return (
    <svg viewBox="0 0 44 44" className="h-11 w-11" aria-hidden>
      {el.kind === 'rect' && <rect x={x} y={y} width={sw} height={sh} rx={(p.radius ?? 0) * k} fill={p.fill ?? 'none'} {...stroke} />}
      {el.kind === 'ellipse' && <ellipse cx={22} cy={22} rx={sw / 2} ry={sh / 2} fill={p.fill ?? 'none'} {...stroke} />}
      {el.kind === 'line' && <line x1={x} y1={y} x2={x + sw} y2={y + sh} stroke="#e4e4e7" strokeWidth={Math.max(0.75, (p.stroke?.w ?? 1) * 0.9)} />}
      {el.kind === 'image' && (
        <g>
          <rect x={x} y={y} width={sw} height={sh} rx={(p.radius ?? 0) * k} fill="#52525b" />
          <path d={`M${x + sw * 0.15} ${y + sh * 0.8} l${sw * 0.25} -${sh * 0.3} l${sw * 0.18} ${sh * 0.18} l${sw * 0.14} -${sh * 0.12} l${sw * 0.13} ${sh * 0.24} z`} fill="#a1a1aa" />
        </g>
      )}
    </svg>
  )
}

function ElementTile({ el, doc }: { el: ElementSpec; doc: Doc }) {
  const c = useCtx()
  return (
    <button type="button" draggable onDragStart={(e) => startDrag(e, { kind: 'element', el })} onDragEnd={endDrag}
      onClick={() => addElement(c, el)} aria-label={`Add ${el.label.toLowerCase()}`} title={el.label}
      className="flex flex-col items-center gap-1 rounded-md border border-zinc-800 bg-zinc-950/60 p-2 text-[10px] text-zinc-400 hover:border-emerald-500 hover:text-zinc-100">
      <ElementArt el={el} doc={doc} />
      <span className="max-w-full truncate">{el.label}</span>
    </button>
  )
}

function SectionHead({ title, count, onAll }: { title: string; count?: number; onAll?: () => void }) {
  return (
    <div className="mb-2 flex items-center justify-between">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">{title}</h3>
      {onAll && (
        <button type="button" onClick={onAll} className="text-[11px] text-emerald-400 hover:text-emerald-300">
          See all{count ? ` ${count.toLocaleString()}` : ''}
        </button>
      )}
    </div>
  )
}

/** Where each basic element sits among the bank's groups. */
const NATIVE_IN: Record<string, GraphicGroup | 'frames' | 'blocks'> = {
  Shapes: 'shapes', Lines: 'lines', 'Picture frames': 'frames', 'Colour blocks': 'blocks',
}
const ORDER: (GraphicGroup | 'frames' | 'blocks')[] = ['shapes', 'lines', 'badges', 'icons', 'stickers', 'patterns', 'frames', 'blocks']
const FIRST: Partial<Record<GraphicGroup, number>> = { shapes: 8, badges: 8, icons: 15, stickers: 12, patterns: 8, lines: 4 }

function ElementsTab() {
  const c = useCtx()
  const doc = useStudio(c.store, (s) => s.doc)
  const [q, setQ] = useState('')
  const [open, setOpen] = useState<GraphicGroup | null>(null)
  const [bank, setBank] = useState<GraphicBrowse | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    graphicsApi.browse().then(setBank, (e) => setError(e instanceof Error ? e.message : 'The graphics didn’t load.'))
  }, [])
  const want = q.trim().toLowerCase()
  const native = (title: string) => ELEMENT_GROUPS.find((g) => g.title === title)?.items ?? []
  const nativeMatches = ELEMENTS.filter((el) => {
    const group = ELEMENT_GROUPS.find((g) => g.items.includes(el))!.title
    return `${group} ${el.label}`.toLowerCase().includes(want)
  })

  const search = (
    <label className="relative block">
      <span className="sr-only">Search elements</span>
      <Search className="pointer-events-none absolute left-2.5 top-2 h-4 w-4 text-zinc-500" />
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search shapes, icons, stickers…"
        className="w-full rounded-md border border-zinc-700 bg-zinc-950 py-1.5 pl-8 pr-2 text-xs text-zinc-100 placeholder:text-zinc-600 focus:border-emerald-500 focus:outline-none" />
    </label>
  )
  if (open) return <div className="space-y-3">{search}<GroupView group={open} q={want} onBack={() => setOpen(null)} /></div>
  if (want) {
    return (
      <div className="space-y-4">
        {search}
        {nativeMatches.length > 0 && (
          <div className="grid grid-cols-3 gap-2">{nativeMatches.map((el) => <ElementTile key={el.id} el={el} doc={doc} />)}</div>
        )}
        <SearchResults q={want} />
      </div>
    )
  }
  return (
    <div className="space-y-5">
      {search}
      <p className={HINT}>Click to add one to the page, or drag it where you want it. Change a shape or icon’s colour in the Object panel.</p>
      {error && <p role="alert" className="text-xs text-red-300">{error}</p>}
      {ORDER.map((key) => {
        const title = key === 'frames' ? 'Picture frames' : key === 'blocks' ? 'Colour blocks' : GROUP_TITLE[key]
        const basics = native(Object.keys(NATIVE_IN).find((t) => NATIVE_IN[t] === key) ?? '')
        const group = key === 'frames' || key === 'blocks' ? null : bank?.groups.find((g) => g.group === key)
        if (!basics.length && !group?.items.length) return null
        return (
          <section key={key}>
            <SectionHead title={title} count={group?.count} onAll={group && group.count > (FIRST[group.group] ?? 0) ? () => setOpen(group.group) : undefined} />
            {basics.length > 0 && <div className="mb-1.5 grid grid-cols-3 gap-2">{basics.map((el) => <ElementTile key={el.id} el={el} doc={doc} />)}</div>}
            {group && <GraphicGrid items={group.items.slice(0, FIRST[group.group] ?? 8)} group={group.group} />}
          </section>
        )
      })}
      {bank && (
        <p className="text-[10px] leading-snug text-zinc-600">
          Icons from Lucide (ISC), stickers from Microsoft Fluent Emoji (MIT), the rest drawn by Gummfit.{' '}
          <a href="/api/cappe/public/graphics/licenses.txt" target="_blank" rel="noreferrer" className="underline hover:text-zinc-400">Licences</a>
        </p>
      )}
    </div>
  )
}

// ── Text ─────────────────────────────────────────────────────────────────────

function PartPreview({ part, scale, face }: { part: TextPart; scale: number; face: (p: TextPart) => string | undefined }) {
  const ch = { ...CHAR_DEFAULTS, ...part.char }
  const align = part.para.align === 'c' ? 'center' : part.para.align === 'r' ? 'right' : 'left'
  return (
    <span className="block leading-tight" style={{
      fontFamily: `${face(part) ?? 'serif'}, serif`, fontWeight: ch.wt, fontStyle: ch.it ? 'italic' : 'normal',
      fontSize: Math.max(8, Math.min(30, ch.size * scale)), letterSpacing: `${ch.track / 1000}em`, textAlign: align,
      color: ch.color === CHAR_DEFAULTS.color ? undefined : ch.color,
    }}>{part.text}</span>
  )
}

function TextTab() {
  const c = useCtx()
  const book = c.fonts.book
  const face = (p: TextPart) => {
    const f = book.face(p.char.font ?? CHAR_DEFAULTS.font, p.char.wt ?? CHAR_DEFAULTS.wt, !!p.char.it)
    return f ? familyName(f.sha) : undefined
  }
  // The previews are set in the faces themselves, loaded as the tab opens.
  const all = useMemo(() => [...TEXT_STYLES, ...TEXT_COMBOS], [])
  useEffect(() => {
    for (const s of all) for (const [f, w, i] of facesOf(s, CHAR_DEFAULTS)) {
      const found = book.face(f, w, i)
      if (found) void c.fonts.ensure(found).catch(() => {})
    }
  }, [all, book, c.fonts])

  const tile = (s: TextStyle, children: ReactNode, cls: string, paper = false) => (
    <button key={s.id} type="button" draggable onDragStart={(e) => startDrag(e, { kind: 'text', style: s })} onDragEnd={endDrag}
      onClick={() => void addText(c, s).catch((err) =>
        c.store.set({ notice: err instanceof Error && err.message ? err.message : 'Couldn’t add that text.' }))} aria-label={s.label.startsWith('Add') ? s.label : `Add ${s.label.toLowerCase()} text`}
      className={`w-full rounded-md border text-left hover:border-emerald-500 ${paper ? 'border-zinc-700 bg-stone-100 text-zinc-900' : 'border-zinc-800 bg-zinc-950/60 text-zinc-100'} ${cls}`}>
      {children}
    </button>
  )
  const [heading, sub, body, ...small] = TEXT_STYLES
  return (
    <div className="space-y-3">
      <p className={HINT}>Click to add text to the page, or drag it into place. Double-click it there to type your own.</p>
      {tile(heading, <PartPreview part={heading.parts[0]} scale={0.6} face={face} />, 'px-3 py-3')}
      {tile(sub, <PartPreview part={sub.parts[0]} scale={0.8} face={face} />, 'px-3 py-2.5')}
      {tile(body, <span className="block text-xs text-zinc-300">Add a little bit of body text</span>, 'px-3 py-2')}
      <div className="grid grid-cols-3 gap-2">
        {small.map((s) => tile(s, <span className="block truncate text-center text-[11px] text-zinc-300">{s.label}</span>, 'px-1 py-2'))}
      </div>
      <h3 className="pt-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-400">Font pairings</h3>
      <div className="grid grid-cols-2 gap-2">
        {TEXT_COMBOS.map((s) => tile(s, (
          <span className="flex h-24 flex-col justify-center gap-0.5 overflow-hidden px-2" title={s.label}>
            {s.parts.map((p, k) => <PartPreview key={k} part={p} scale={0.36} face={face} />)}
          </span>
        ), '', true))}
      </div>
    </div>
  )
}
