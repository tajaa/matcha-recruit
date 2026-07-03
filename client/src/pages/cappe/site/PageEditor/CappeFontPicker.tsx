import { useEffect, useState } from 'react'
import { Check, ChevronDown, Search } from 'lucide-react'
import { BODY_FONTS, FONT_CATEGORY, HEADING_FONTS } from '../../../../data/cappeThemes'
import { dLabel, inputCls } from './styles'

export const FONT_CATS: ('Sans' | 'Serif' | 'Display' | 'Mono' | 'Handwriting')[] = ['Sans', 'Serif', 'Display', 'Mono', 'Handwriting']
export function ensureFontPreviewCss() {
  const id = 'cz-fontpreview'
  if (document.getElementById(id)) return
  const parts = HEADING_FONTS.map((f) => `family=${encodeURIComponent(f)}:wght@500;700`).join('&')
  const link = document.createElement('link')
  link.id = id
  link.rel = 'stylesheet'
  link.href = `https://fonts.googleapis.com/css2?${parts}&display=swap`
  document.head.appendChild(link)
}

/** Searchable font picker — renders each option in its own typeface, grouped by
 *  category. `bodyOnly` narrows to body-readable families. */
export function CappeFontPicker({ label, value, onChange, bodyOnly }: {
  label: string; value: string; onChange: (v: string) => void; bodyOnly?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const list = bodyOnly ? BODY_FONTS : HEADING_FONTS
  useEffect(() => { if (open) ensureFontPreviewCss() }, [open])
  const filtered = list.filter((n) => n.toLowerCase().includes(q.trim().toLowerCase()))
  return (
    <div className="relative">
      <span className={dLabel}>{label}</span>
      <button type="button" onClick={() => setOpen((o) => !o)}
        className={`${inputCls} flex items-center justify-between py-1.5`} style={{ fontFamily: `'${value}', sans-serif` }}>
        <span className="truncate">{value || 'Choose font'}</span>
        <ChevronDown className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-20" onClick={() => { setOpen(false); setQ('') }} />
          <div className="absolute z-30 mt-1 max-h-72 w-full overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-900 p-1.5 shadow-xl shadow-black/40">
            <div className="relative mb-1">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
              <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search fonts…" className={`${inputCls} py-1.5 pl-7`} />
            </div>
            {FONT_CATS.map((cat) => {
              const items = filtered.filter((n) => FONT_CATEGORY[n] === cat)
              if (!items.length) return null
              return (
                <div key={cat}>
                  <p className="px-2 pb-0.5 pt-1.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-500">{cat}</p>
                  {items.map((n) => (
                    <button key={n} type="button" onClick={() => { onChange(n); setOpen(false); setQ('') }}
                      className={`flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-sm hover:bg-emerald-500/10 ${n === value ? 'text-emerald-400' : 'text-zinc-200'}`}
                      style={{ fontFamily: `'${n}', sans-serif` }}>
                      <span className="truncate">{n}</span>
                      {n === value && <Check className="h-3.5 w-3.5 shrink-0" />}
                    </button>
                  ))}
                </div>
              )
            })}
            {!filtered.length && <p className="px-2 py-3 text-center text-xs text-zinc-500">No fonts match.</p>}
          </div>
        </>
      )}
    </div>
  )
}
