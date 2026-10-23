import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ImagePlus, Loader2, Search, Sparkles } from 'lucide-react'
import { cappeApi, cappeApiBase } from '../../../api'
import { STOCK_SOURCES, licenseLabel, stockKey, thumbUrl } from '../../../magazine/library/assets'
import IllustrateForm from '../../../magazine/library/IllustrateForm'
import { UploadForm } from '../../../magazine/library/LibraryPanel'
import type { CappeAsset, CappeAssetKind, CappeStockResult, CappeStockSearch, CappeStockSearchSource } from '../../../types'
import { useCtx } from '../context'
import { endDrag, importStock, startDrag } from './drag'
import { BankPhotos } from './BankPhotos'
import { addPicture } from './place'

const HINT = 'text-[11px] leading-snug text-zinc-500'
const INPUT = 'w-full rounded-md border border-zinc-700 bg-zinc-950 py-1.5 pl-8 pr-2 text-xs text-zinc-100 placeholder:text-zinc-600 focus:border-emerald-500 focus:outline-none'
const CHIP = (on: boolean) => `rounded-full px-2.5 py-1 text-[11px] ${on ? 'bg-emerald-500/20 text-emerald-300' : 'bg-zinc-800 text-zinc-400 hover:text-zinc-100'}`
const IDEAS = ['harbour', 'city at night', 'mountains', 'flowers', 'street market', 'the moon']
// What to browse when Gummfit's library is empty (free photos, live).
const TOPICS = ['coffee', 'city', 'nature', 'food', 'people', 'travel', 'work', 'texture']
const message = (e: unknown, fallback: string) => (e instanceof Error && e.message ? e.message : fallback)

/** Free photos: Gummfit's own library first (instant, by collection), and
 *  for a search, modern CC0 stock beyond it; the archives (each picture one
 *  a magazine may publish, credited as it should be); and AI pictures. A
 *  click adds it to the page; the first time, it goes into the library too. */
export function PhotosTab() {
  const c = useCtx()
  const [source, setSource] = useState<CappeStockSearchSource>('stock')
  const [query, setQuery] = useState('')
  const [bankQuery, setBankQuery] = useState('')
  const [bankEmpty, setBankEmpty] = useState(false)
  const [last, setLast] = useState<CappeStockSearch | null>(null)
  const [results, setResults] = useState<CappeStockResult[]>([])
  const [searching, setSearching] = useState(false)
  const [adding, setAdding] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [ai, setAi] = useState(false)
  const gen = useRef(0)

  const search = async (src: CappeStockSearchSource, q: string, page: number) => {
    if (!q && src !== 'stock') return
    const mine = ++gen.current
    setSearching(true)
    setError(null)
    try {
      const res = await cappeApi.get<CappeStockSearch>(`/sites/${c.siteId}/library/search?${new URLSearchParams({ source: src, q, page: String(page) })}`)
      if (mine !== gen.current) return
      setLast(res)
      setResults((prev) => (page === 0 ? res.results : [...prev, ...res.results]))
    } catch (e) {
      if (mine === gen.current) setError(message(e, 'That search didn’t work. Try again.'))
    } finally {
      if (mine === gen.current) setSearching(false)
    }
  }
  // An empty library: browse free photos instead, so the tab never opens bare.
  const browse = () => { setBankEmpty(true); void search('stock', '', 0) }
  const run = (src: CappeStockSearchSource, q: string) => {
    if (src === 'stock') setBankQuery(q)
    if (q || (src === 'stock' && bankEmpty)) void search(src, q, 0)
    else if (src === 'stock') { gen.current++; setLast(null); setResults([]); setSearching(false) }
  }
  const submit = (e: FormEvent) => { e.preventDefault(); run(source, query.trim()) }
  const pick = (src: CappeStockSearchSource) => {
    gen.current++ // what the last source was still finding isn't this one's
    setSource(src)
    setLast(null)
    setResults([])
    setSearching(false)
    run(src, query.trim())
  }
  const idea = (q: string) => { setQuery(q); run(source, q) }

  const add = async (r: CappeStockResult) => {
    const key = stockKey(r)
    if (adding.includes(key)) return
    setAdding((a) => [...a, key])
    setError(null)
    try {
      addPicture(c, await importStock(c.siteId, c.postId, r))
    } catch (e) {
      setError(message(e, 'That picture couldn’t be added. Try another.'))
    } finally {
      setAdding((a) => a.filter((k) => k !== key))
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1" role="tablist" aria-label="Where the photos come from">
        {STOCK_SOURCES.map((s) => (
          <button key={s.key} type="button" role="tab" aria-selected={source === s.key} title={s.hint}
            onClick={() => pick(s.key)} className={CHIP(source === s.key)}>{s.label}</button>
        ))}
      </div>
      <form onSubmit={submit} role="search" className="relative">
        <span className="sr-only">Search {STOCK_SOURCES.find((s) => s.key === source)?.label}</span>
        <Search className="pointer-events-none absolute left-2.5 top-2 h-4 w-4 text-zinc-500" />
        <input value={query} onChange={(e) => setQuery(e.target.value)} maxLength={120} placeholder="Search free photos"
          aria-label="Search free photos" className={INPUT} />
      </form>
      {source === 'stock' && (
        <>
          <p className={HINT}>Photos free for any use, each credited under it anyway. Search for more.</p>
          {bankEmpty && (
            <div className="flex flex-wrap gap-1" role="group" aria-label="Topics">
              {TOPICS.map((q) => <button key={q} type="button" onClick={() => idea(q)} className={CHIP(query === q)}>{q}</button>)}
            </div>
          )}
          <BankPhotos q={bankQuery} onEmpty={browse} />
        </>
      )}
      {source !== 'stock' && !last && !searching && (
        <div className="space-y-2">
          <p className={HINT}>Only pictures you may publish and crop, each credited under it. Try:</p>
          <div className="flex flex-wrap gap-1">{IDEAS.map((q) => <button key={q} type="button" onClick={() => idea(q)} className={CHIP(false)}>{q}</button>)}</div>
        </div>
      )}
      {error && <p role="alert" className="text-xs text-red-300">{error}</p>}
      {source === 'stock' && !bankEmpty && (results.length > 0 || searching) && (
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">More free photos</h3>
      )}
      {searching && <p className="flex items-center gap-1.5 text-xs text-zinc-400"><Loader2 className="h-3 w-3 animate-spin" />{source === 'stock' ? 'Searching free photos… this can take a few seconds.' : 'Searching…'}</p>}
      {last && !results.length && !searching && (
        <p className="text-xs text-zinc-500">{last.query ? `Nothing we can publish for “${last.query}”. Try other words or another archive.` : 'No photos came back. Try a search.'}</p>
      )}
      {results.length > 0 && (
        <ul className={`grid grid-cols-2 gap-2 ${searching ? 'opacity-50' : ''}`} aria-label="Free photos" aria-busy={searching}>
          {results.map((r) => {
            const busy = adding.includes(stockKey(r))
            return (
              <li key={stockKey(r)}>
                <button type="button" draggable onDragStart={(e) => startDrag(e, { kind: 'stock', result: r })} onDragEnd={endDrag}
                  onClick={() => void add(r)} disabled={busy} title={r.credit_line} aria-label={`Add ${r.title || 'this picture'}`}
                  className="relative block aspect-[4/3] w-full overflow-hidden rounded-md bg-zinc-800 hover:ring-2 hover:ring-emerald-500">
                  {r.thumb && <img src={`${cappeApiBase}${r.thumb}`} alt="" loading="lazy" draggable={false} className="h-full w-full object-cover" />}
                  <span className="absolute left-1 top-1 rounded bg-black/70 px-1 py-0.5 text-[9px] font-semibold text-white">{licenseLabel(r.license, r.license_version)}</span>
                  {busy && <span className="absolute inset-0 flex items-center justify-center bg-black/50"><Loader2 className="h-5 w-5 animate-spin text-white" /></span>}
                </button>
              </li>
            )
          })}
        </ul>
      )}
      {last?.has_more && (
        <button type="button" disabled={searching} onClick={() => void search(last.source, last.query, last.page + 1)}
          className="w-full rounded-md border border-zinc-700 py-1.5 text-xs text-zinc-300 hover:border-zinc-500">More</button>
      )}
      <div className="border-t border-zinc-800 pt-3">
        {ai
          ? <IllustrateForm siteId={c.siteId} onDone={(a) => { setAi(false); addPicture(c, a) }} onCancel={() => setAi(false)} />
          : (
            <button type="button" onClick={() => setAi(true)} className="flex w-full items-center justify-center gap-1.5 rounded-md border border-zinc-700 py-2 text-xs text-zinc-200 hover:border-emerald-500">
              <Sparkles className="h-3.5 w-3.5 text-emerald-400" />Make an AI picture
            </button>
          )}
      </div>
    </div>
  )
}

const KINDS: { key: '' | CappeAssetKind; label: string }[] = [
  { key: '', label: 'All' }, { key: 'upload', label: 'Uploads' }, { key: 'stock', label: 'Archive' },
  { key: 'generated', label: 'AI' }, { key: 'edit', label: 'Edited' },
]

/** The site's own library: uploads, archive pictures, AI pictures and edits. */
export function YourPicturesTab() {
  const c = useCtx()
  const [assets, setAssets] = useState<CappeAsset[] | null>(null)
  const [kind, setKind] = useState<'' | CappeAssetKind>('')
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setSearch(query.trim()), 300)
    return () => clearTimeout(t)
  }, [query])
  useEffect(() => {
    let alive = true
    const params = new URLSearchParams()
    if (kind) params.set('kind', kind)
    if (search) params.set('q', search)
    const qs = params.toString()
    cappeApi.get<{ assets: CappeAsset[] }>(`/sites/${c.siteId}/assets${qs ? `?${qs}` : ''}`)
      .then((res) => { if (alive) { setAssets(res.assets); setError(null) } })
      .catch((e) => { if (alive) setError(message(e, 'Your pictures didn’t load.')) })
    return () => { alive = false }
  }, [c.siteId, kind, search])

  return (
    <div className="space-y-3">
      {uploading
        ? <UploadForm siteId={c.siteId} onDone={(a) => { setUploading(false); setAssets((l) => [a, ...(l ?? [])]) }} onCancel={() => setUploading(false)} />
        : (
          <button type="button" onClick={() => setUploading(true)}
            className="flex w-full items-center justify-center gap-1.5 rounded-md bg-emerald-600 py-2 text-xs font-medium text-white hover:bg-emerald-500">
            <ImagePlus className="h-3.5 w-3.5" />Upload a picture
          </button>
        )}
      <label className="relative block">
        <span className="sr-only">Search your pictures</span>
        <Search className="pointer-events-none absolute left-2.5 top-2 h-4 w-4 text-zinc-500" />
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search your pictures" className={INPUT} />
      </label>
      <div className="flex flex-wrap gap-1" role="tablist" aria-label="Kind of picture">
        {KINDS.map((k) => <button key={k.key || 'all'} type="button" role="tab" aria-selected={kind === k.key} onClick={() => setKind(k.key)} className={CHIP(kind === k.key)}>{k.label}</button>)}
      </div>
      {error && <p role="alert" className="text-xs text-red-300">{error}</p>}
      {assets === null && !error && <p className="flex items-center gap-1.5 text-xs text-zinc-400"><Loader2 className="h-3 w-3 animate-spin" />Loading…</p>}
      {assets?.length === 0 && <p className="text-xs text-zinc-500">{search || kind ? 'Nothing matches.' : 'No pictures yet. Upload one, or find free photos.'}</p>}
      {!!assets?.length && (
        <>
          <p className={HINT}>Click to add one to the page, or drag it onto a picture frame to fill it.</p>
          <ul className="grid grid-cols-2 gap-2" aria-label="Your pictures">
            {assets.map((a) => (
              <li key={a.id}>
                <button type="button" draggable onDragStart={(e) => startDrag(e, { kind: 'asset', asset: a })} onDragEnd={endDrag}
                  onClick={() => addPicture(c, a)} title={a.alt || a.credit_line || ''} aria-label={`Add ${a.alt || 'this picture'}`}
                  className="block aspect-square w-full overflow-hidden rounded-md bg-zinc-800 hover:ring-2 hover:ring-emerald-500">
                  <img src={thumbUrl(a)} alt="" loading="lazy" draggable={false} className="h-full w-full object-cover" />
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
