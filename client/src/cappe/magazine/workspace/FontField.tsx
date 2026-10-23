import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown, Search } from 'lucide-react'
import { FONTS, type FontCategory } from '../design/fonts'
import { previewHref, WEIGHT_NAMES } from './fontPreview'

const CATS: { key: FontCategory | 'all'; label: string }[] = [
  { key: 'all', label: 'All' }, { key: 'serif', label: 'Serif' }, { key: 'sans', label: 'Sans' }, { key: 'display', label: 'Display' },
  { key: 'handwriting', label: 'Script' }, { key: 'mono', label: 'Mono' },
]

const loaded = new Set<string>()
/** Each face's name, set in that face (Google sends only those letters). */
function loadPreviews(names: string[]) {
  for (const name of names) {
    if (loaded.has(name)) continue
    loaded.add(name)
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = previewHref(name)
    document.head.appendChild(link)
  }
}

/** A face: the magazine's own pair first, then every face we offer, searched
 *  and sorted by kind, each shown in its own type. */
export default function FontField({ value, onChange, label = 'Font', roles = true }: {
  value: string; onChange: (font: string) => void; label?: string
  /** Offer the magazine's own heading and body faces. */
  roles?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [cat, setCat] = useState<FontCategory | 'all'>('all')
  const btn = useRef<HTMLButtonElement>(null)
  const panel = useRef<HTMLDivElement>(null)
  const [at, setAt] = useState<{ left: number; top: number } | null>(null)
  const list = useMemo(() => FONTS.filter((f) => (cat === 'all' || f.cat === cat) && f.name.toLowerCase().includes(q.trim().toLowerCase())), [q, cat])

  useLayoutEffect(() => {
    if (!open || !btn.current) return
    const r = btn.current.getBoundingClientRect()
    setAt({ left: Math.max(8, Math.min(window.innerWidth - 288, r.left)), top: Math.min(r.bottom + 4, window.innerHeight - 420) })
  }, [open])
  useEffect(() => { if (open) loadPreviews(list.slice(0, 60).map((f) => f.name)) }, [open, list])
  useEffect(() => { if (!roles && FONTS.some((f) => f.name === value)) loadPreviews([value]) }, [roles, value])
  useEffect(() => {
    if (!open) return
    const down = (e: PointerEvent) => {
      if (panel.current?.contains(e.target as Node) || btn.current?.contains(e.target as Node)) return
      setOpen(false)
    }
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('pointerdown', down, true)
    window.addEventListener('keydown', key)
    return () => { window.removeEventListener('pointerdown', down, true); window.removeEventListener('keydown', key) }
  }, [open])

  const name = value === 'heading' ? 'Magazine heading' : value === 'body' ? 'Magazine body' : value
  const pick = (f: string) => { onChange(f); setOpen(false) }
  return (
    <>
      <button ref={btn} type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-label={`${label}: ${name}`}
        className="flex h-7 w-full items-center justify-between gap-2 rounded-md border border-zinc-800 bg-zinc-900 px-2 text-xs text-zinc-100 hover:border-zinc-700">
        <span className="truncate" style={FONTS.some((f) => f.name === value) ? { fontFamily: `'${value}'` } : undefined}>{name}</span>
        <ChevronDown className="h-4 w-4 shrink-0 text-zinc-500" />
      </button>
      {open && at && (
        <div ref={panel} role="dialog" aria-label={label} style={at}
          className="fixed z-50 flex h-[26rem] w-72 flex-col rounded-lg border border-zinc-700 bg-zinc-900 shadow-2xl">
          <div className="space-y-2 border-b border-zinc-800 p-2">
            <label className="flex items-center gap-2 rounded-md border border-zinc-800 bg-zinc-950 px-2">
              <Search className="h-3.5 w-3.5 text-zinc-500" />
              <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search fonts" aria-label="Search fonts"
                className="h-7 min-w-0 flex-1 bg-transparent text-xs text-zinc-100 outline-none" />
            </label>
            <div className="flex flex-wrap gap-1">
              {CATS.map((c) => (
                <button key={c.key} type="button" aria-pressed={cat === c.key} onClick={() => setCat(c.key)}
                  className={`rounded px-1.5 py-0.5 text-[11px] ${cat === c.key ? 'bg-zinc-700 text-zinc-50' : 'text-zinc-400 hover:text-zinc-100'}`}>{c.label}</button>
              ))}
            </div>
          </div>
          <ul className="min-h-0 flex-1 overflow-y-auto p-1" role="listbox" aria-label="Fonts"
            onScroll={(e) => {
              const el = e.currentTarget
              const shown = Math.ceil((el.scrollTop + el.clientHeight) / 32) + 20
              loadPreviews(list.slice(0, shown).map((f) => f.name))
            }}>
            {roles && !q && (cat === 'all') && (['heading', 'body'] as const).map((r) => (
              <li key={r} role="option" aria-selected={value === r}>
                <button type="button" onClick={() => pick(r)}
                  className={`flex h-8 w-full items-center justify-between rounded px-2 text-left text-sm ${value === r ? 'bg-emerald-500/15 text-emerald-300' : 'text-zinc-200 hover:bg-zinc-800'}`}>
                  <span>{r === 'heading' ? 'Magazine heading' : 'Magazine body'}</span>
                  <span className="text-[10px] text-zinc-500">your masthead’s</span>
                </button>
              </li>
            ))}
            {list.map((f) => (
              <li key={f.name} role="option" aria-selected={value === f.name}>
                <button type="button" onClick={() => pick(f.name)} title={`${f.name} · ${f.w.length} weight${f.w.length === 1 ? '' : 's'}${f.i.length ? ', italics' : ''}`}
                  className={`flex h-8 w-full items-center justify-between gap-2 rounded px-2 text-left ${value === f.name ? 'bg-emerald-500/15 text-emerald-300' : 'text-zinc-100 hover:bg-zinc-800'}`}>
                  <span className="truncate text-[15px]" style={{ fontFamily: `'${f.name}', system-ui` }}>{f.name}</span>
                  <span className="shrink-0 text-[10px] text-zinc-500">{f.w.length > 1 ? `${WEIGHT_NAMES[f.w[0]] ?? f.w[0]}–${WEIGHT_NAMES[f.w[f.w.length - 1]] ?? f.w[f.w.length - 1]}` : 'one weight'}</span>
                </button>
              </li>
            ))}
            {!list.length && <li className="p-3 text-xs text-zinc-500">No font by that name.</li>}
          </ul>
        </div>
      )}
    </>
  )
}
