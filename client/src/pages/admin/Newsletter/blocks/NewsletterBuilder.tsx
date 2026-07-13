import { useMemo, useRef, useState } from 'react'
import {
  Plus, ChevronUp, ChevronDown, Copy, Trash2, Pencil, X, Palette, ImageOff, AlertTriangle,
} from 'lucide-react'
import { FieldForm } from './FieldForm'
import {
  BLOCK_SCHEMAS, BLOCK_ORDER, makeBlock, designHasMedia,
  type NewsletterDesign, type NLBlock, type ThemePreset,
} from './schema'

const GROUPS = ['Layout', 'Content', 'Media', 'Social proof'] as const

/** One-line human summary of a block for its collapsed card. */
function blockSummary(b: NLBlock): string {
  const s = (v: unknown) => (typeof v === 'string' ? v : '')
  switch (b.type) {
    case 'hero': return s(b.heading) || 'Hero'
    case 'heading': return s(b.heading) || 'Heading'
    case 'text': return s(b.body).slice(0, 60) || 'Text'
    case 'button': return s(b.label) || 'Button'
    case 'image': return s(b.caption) || s(b.alt) || 'Image'
    case 'imageText': return s(b.heading) || 'Image + text'
    case 'columns': return `${(b.columns as unknown[])?.length ?? 0} columns`
    case 'features': return s(b.heading) || `${(b.items as unknown[])?.length ?? 0} features`
    case 'articles': return s(b.heading) || `${(b.items as unknown[])?.length ?? 0} articles`
    case 'quote': return s(b.quote).slice(0, 50) || 'Quote'
    case 'stats': return `${(b.items as unknown[])?.length ?? 0} stats`
    case 'video': return s(b.caption) || 'Video'
    case 'footer': return s(b.brandName) || 'Footer'
    default: return BLOCK_SCHEMAS[b.type]?.label ?? b.type
  }
}

export function NewsletterBuilder({
  design,
  onChange,
}: {
  design: NewsletterDesign
  onChange: (next: NewsletterDesign) => void
}) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [insertOpen, setInsertOpen] = useState(false)
  const [showTheme, setShowTheme] = useState(false)
  const insertRef = useRef<HTMLDivElement>(null)

  const blocks = design.blocks
  const hasMedia = useMemo(() => designHasMedia(design), [design])

  const setBlocks = (next: NLBlock[]) => onChange({ ...design, blocks: next })
  const setTheme = (patch: Partial<NewsletterDesign['theme']>) => onChange({ ...design, theme: { ...design.theme, ...patch } })

  const addBlock = (type: string) => {
    const block = makeBlock(type)
    setBlocks([...blocks, block])
    setEditingId(block.id)
    setInsertOpen(false)
  }
  const updateBlock = (id: string, next: NLBlock) => setBlocks(blocks.map((b) => (b.id === id ? next : b)))
  const removeBlock = (id: string) => { setBlocks(blocks.filter((b) => b.id !== id)); if (editingId === id) setEditingId(null) }
  const duplicateBlock = (id: string) => {
    const i = blocks.findIndex((b) => b.id === id)
    if (i < 0) return
    const copy = makeBlock(blocks[i].type)
    const cloned: NLBlock = { ...blocks[i], id: copy.id }
    setBlocks([...blocks.slice(0, i + 1), cloned, ...blocks.slice(i + 1)])
  }
  const move = (id: string, dir: -1 | 1) => {
    const i = blocks.findIndex((b) => b.id === id)
    const j = i + dir
    if (i < 0 || j < 0 || j >= blocks.length) return
    const copy = blocks.slice()
    ;[copy[i], copy[j]] = [copy[j], copy[i]]
    setBlocks(copy)
  }

  return (
    <div className="space-y-3">
      {/* Theme / brand controls */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/40">
        <button
          type="button"
          onClick={() => setShowTheme((v) => !v)}
          className="w-full flex items-center gap-2 px-3 py-2 text-xs text-zinc-300"
        >
          <Palette size={13} className="text-zinc-500" />
          <span className="font-medium">Theme &amp; branding</span>
          <span className="ml-auto flex items-center gap-1.5">
            <span
              className="inline-block w-3.5 h-3.5 rounded-full border border-zinc-700"
              style={{ background: design.theme.brandColor || (design.theme.preset === 'dark' ? '#10b981' : '#059669') }}
            />
            <span className="text-zinc-500 capitalize">{design.theme.preset}</span>
            {showTheme ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </span>
        </button>
        {showTheme && (
          <div className="px-3 pb-3 space-y-2.5 border-t border-zinc-800/60 pt-2.5">
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-zinc-400 w-24">Background</span>
              {(['light', 'dark'] as ThemePreset[]).map((p) => (
                <button
                  key={p} type="button" onClick={() => setTheme({ preset: p })}
                  className={`text-[11px] px-2.5 py-1 rounded-md capitalize ${design.theme.preset === p ? 'bg-zinc-700 text-zinc-100' : 'bg-zinc-900 text-zinc-400 hover:text-zinc-200'}`}
                >{p}</button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-zinc-400 w-24">Brand color</span>
              <input
                type="color"
                value={design.theme.brandColor || (design.theme.preset === 'dark' ? '#10b981' : '#059669')}
                onChange={(e) => setTheme({ brandColor: e.target.value })}
                className="h-7 w-10 rounded bg-transparent border border-zinc-700 cursor-pointer"
              />
              {design.theme.brandColor && (
                <button type="button" onClick={() => setTheme({ brandColor: undefined })} className="text-[10px] text-zinc-500 hover:text-zinc-300">reset</button>
              )}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-zinc-400 w-24">Brand name</span>
              <input
                value={design.theme.brandName ?? ''}
                onChange={(e) => setTheme({ brandName: e.target.value })}
                placeholder="Matcha"
                className="flex-1 px-2.5 py-1 rounded-md border border-zinc-700 bg-zinc-900 text-sm text-zinc-200 outline-none"
              />
            </div>
          </div>
        )}
      </div>

      {/* Mandatory-media hint */}
      {blocks.length > 0 && !hasMedia && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-300">
          <AlertTriangle size={13} className="shrink-0" />
          Add at least one visual (hero, image, or video) so this newsletter isn't all text.
        </div>
      )}

      {/* Block list */}
      {blocks.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-800 px-4 py-8 text-center">
          <ImageOff size={20} className="mx-auto text-zinc-600 mb-2" />
          <p className="text-sm text-zinc-400">No blocks yet.</p>
          <p className="text-xs text-zinc-600 mt-0.5">Add a hero, then build your newsletter section by section.</p>
        </div>
      )}

      <div className="space-y-2">
        {blocks.map((b, i) => {
          const schema = BLOCK_SCHEMAS[b.type]
          const open = editingId === b.id
          return (
            <div key={b.id} className={`rounded-xl border ${open ? 'border-emerald-600/50' : 'border-zinc-800'} bg-zinc-900/30`}>
              <div className="flex items-center gap-2 px-3 py-2">
                <span className="text-base leading-none w-5 text-center shrink-0" aria-hidden>{schema?.icon ?? '▦'}</span>
                <button type="button" onClick={() => setEditingId(open ? null : b.id)} className="flex-1 min-w-0 text-left">
                  <span className="text-xs font-medium text-zinc-200">{schema?.label ?? b.type}</span>
                  <span className="block text-[11px] text-zinc-500 truncate">{blockSummary(b)}</span>
                </button>
                <div className="flex items-center gap-0.5 shrink-0 text-zinc-500">
                  <button type="button" title="Move up" onClick={() => move(b.id, -1)} disabled={i === 0} className="p-1 hover:text-zinc-200 disabled:opacity-30"><ChevronUp size={14} /></button>
                  <button type="button" title="Move down" onClick={() => move(b.id, 1)} disabled={i === blocks.length - 1} className="p-1 hover:text-zinc-200 disabled:opacity-30"><ChevronDown size={14} /></button>
                  <button type="button" title="Duplicate" onClick={() => duplicateBlock(b.id)} className="p-1 hover:text-zinc-200"><Copy size={13} /></button>
                  <button type="button" title="Edit" onClick={() => setEditingId(open ? null : b.id)} className={`p-1 ${open ? 'text-emerald-400' : 'hover:text-zinc-200'}`}><Pencil size={13} /></button>
                  <button type="button" title="Delete" onClick={() => removeBlock(b.id)} className="p-1 hover:text-red-400"><Trash2 size={13} /></button>
                </div>
              </div>
              {open && schema && (
                <div className="px-3 pb-3 pt-1 border-t border-zinc-800/60">
                  <FieldForm
                    fields={schema.fields}
                    value={b as unknown as Record<string, unknown>}
                    onChange={(next) => updateBlock(b.id, { ...(next as NLBlock), id: b.id, type: b.type })}
                  />
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Add block */}
      <div className="relative" ref={insertRef}>
        <button
          type="button"
          onClick={() => setInsertOpen((v) => !v)}
          className="w-full flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl border border-dashed border-zinc-700 text-sm text-zinc-300 hover:border-emerald-600/60 hover:text-emerald-300 transition-colors"
        >
          {insertOpen ? <X size={15} /> : <Plus size={15} />} Add block
        </button>
        {insertOpen && (
          <div className="absolute z-20 left-0 right-0 mt-2 rounded-xl border border-zinc-700 bg-zinc-900 shadow-xl p-2 max-h-96 overflow-y-auto">
            {GROUPS.map((group) => {
              const types = BLOCK_ORDER.filter((t) => BLOCK_SCHEMAS[t]?.group === group)
              if (!types.length) return null
              return (
                <div key={group} className="mb-1.5 last:mb-0">
                  <p className="px-2 pt-1.5 pb-1 text-[10px] uppercase tracking-wider text-zinc-500">{group}</p>
                  <div className="grid grid-cols-2 gap-1">
                    {types.map((t) => (
                      <button
                        key={t} type="button" onClick={() => addBlock(t)}
                        className="flex items-center gap-2 px-2.5 py-2 rounded-lg text-left text-xs text-zinc-300 hover:bg-zinc-800"
                      >
                        <span className="text-sm w-4 text-center" aria-hidden>{BLOCK_SCHEMAS[t].icon}</span>
                        {BLOCK_SCHEMAS[t].label}
                      </button>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
