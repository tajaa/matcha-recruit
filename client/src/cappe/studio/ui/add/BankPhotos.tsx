import { useEffect, useRef, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { useCtx } from '../context'
import { bankApi, bankThumb, type BankPhoto } from './bank'
import { endDrag, startDrag } from './drag'
import { addPicture } from './place'

const CHIP = (on: boolean) => `rounded-full px-2.5 py-1 text-[11px] ${on ? 'bg-emerald-500/20 text-emerald-300' : 'bg-zinc-800 text-zinc-400 hover:text-zinc-100'}`
const message = (e: unknown, fallback: string) => (e instanceof Error && e.message ? e.message : fallback)

/** Gummfit's photos, by collection, matching `q`. A click puts one on the
 *  page; the first time, it goes into the library too. */
export function BankPhotos({ q }: { q: string }) {
  const c = useCtx()
  const [collection, setCollection] = useState<string | null>(null)
  const [items, setItems] = useState<BankPhoto[]>([])
  const [collections, setCollections] = useState<string[]>([])
  const [total, setTotal] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [adding, setAdding] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const gen = useRef(0)

  const load = (offset: number) => {
    const mine = ++gen.current
    setBusy(true)
    bankApi.photos(c.siteId, q, collection, offset)
      .then((res) => {
        if (mine !== gen.current) return
        setItems((prev) => (offset ? [...prev, ...res.items] : res.items))
        setCollections(res.collections)
        setTotal(res.total)
        setError(null)
      })
      .catch((e) => { if (mine === gen.current) setError(message(e, 'Gummfit’s photos didn’t load.')) })
      .finally(() => { if (mine === gen.current) setBusy(false) })
  }
  useEffect(() => {
    const t = setTimeout(() => load(0), 0)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- a new list whenever what is asked changes
  }, [c.siteId, q, collection])

  const add = async (p: BankPhoto) => {
    if (adding.includes(p.id)) return
    setAdding((a) => [...a, p.id])
    setError(null)
    try {
      addPicture(c, await bankApi.place(c.siteId, p.id))
    } catch (e) {
      setError(message(e, 'That photo couldn’t be added. Try another.'))
    } finally {
      setAdding((a) => a.filter((k) => k !== p.id))
    }
  }

  return (
    <div className="space-y-3">
      {collections.length > 0 && (
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Collections">
          {[null, ...collections].map((k) => (
            <button key={k ?? 'all'} type="button" role="tab" aria-selected={collection === k} onClick={() => setCollection(k)}
              className={CHIP(collection === k)}>{k ?? 'All'}</button>
          ))}
        </div>
      )}
      {error && <p role="alert" className="text-xs text-red-300">{error}</p>}
      {busy && !items.length && <p className="flex items-center gap-1.5 text-xs text-zinc-400"><Loader2 className="h-3 w-3 animate-spin" />Loading…</p>}
      {total === 0 && !busy && (
        <p className="text-xs text-zinc-500">{q || collection ? 'No Gummfit photos for that. Try the archives.' : 'No Gummfit photos yet. Try the archives.'}</p>
      )}
      {items.length > 0 && (
        <ul className="grid grid-cols-2 gap-2" aria-label="Gummfit photos">
          {items.map((p) => (
            <li key={p.id}>
              <button type="button" draggable onDragStart={(e) => startDrag(e, { kind: 'bank', photo: p })} onDragEnd={endDrag}
                onClick={() => void add(p)} disabled={adding.includes(p.id)} title={p.credit_line ?? p.name} aria-label={`Add ${p.name}`}
                className="relative block aspect-[4/3] w-full overflow-hidden rounded-md bg-zinc-800 hover:ring-2 hover:ring-emerald-500">
                <img src={bankThumb(p)} alt="" loading="lazy" draggable={false} className="h-full w-full object-cover" />
                {adding.includes(p.id) && <span className="absolute inset-0 flex items-center justify-center bg-black/50"><Loader2 className="h-5 w-5 animate-spin text-white" /></span>}
              </button>
            </li>
          ))}
        </ul>
      )}
      {total !== null && items.length < total && (
        <button type="button" disabled={busy} onClick={() => load(items.length)}
          className="w-full rounded-md border border-zinc-700 py-1.5 text-xs text-zinc-300 hover:border-zinc-500">{busy ? 'Loading…' : 'More'}</button>
      )}
    </div>
  )
}
