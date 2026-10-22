import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Check, ExternalLink, Loader2, Search, Wand2 } from 'lucide-react'
import { cappeApi, cappeApiBase } from '../../api'
import { ui } from '../../components/ui'
import type {
  CappeAsset, CappeStockImport, CappeStockImports, CappeStockResult, CappeStockSearch, CappeStockSource,
  CappeStoryOptions,
} from '../../types'
import { STOCK_SOURCES, importOpen, licenseLabel, stockKey } from './assets'

const POLL_MS = 2000
// Five minutes of polling; past that the server re-dispatches anything stuck
// and the pictures show up in the library on the next visit.
const MAX_POLLS = 150
const MAX_PER_IMPORT = 24

const message = (e: unknown, fallback: string) => (e instanceof Error && e.message ? e.message : fallback)

/**
 * "Find free photos": search Openverse, the Smithsonian, The Met and NASA for
 * pictures a magazine may publish, import the ones picked, or fill the library
 * for a topic. Imports run on the server; this polls them and hands each
 * picture to `onImported` as it lands.
 */
export default function StockSearch({ siteId, postId, onImported, pollMs = POLL_MS }: {
  siteId: string
  /** The story being edited, when opened from the editor's picker. */
  postId?: string
  onImported: (asset: CappeAsset) => void
  pollMs?: number
}) {
  const [source, setSource] = useState<CappeStockSource>('openverse')
  const [query, setQuery] = useState('')
  const [last, setLast] = useState<CappeStockSearch | null>(null)
  const [results, setResults] = useState<CappeStockResult[]>([])
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [picked, setPicked] = useState<string[]>([])
  const [jobs, setJobs] = useState<CappeStockImport[]>([])
  const [remaining, setRemaining] = useState<number | null>(null)
  const [queueing, setQueueing] = useState(false)
  const [topics, setTopics] = useState<CappeStoryOptions['topics']>([])
  const [topic, setTopic] = useState('')
  const [polls, setPolls] = useState(0)
  const generation = useRef(0)
  const delivered = useRef(new Set<string>())
  const onImportedRef = useRef(onImported)
  useEffect(() => { onImportedRef.current = onImported }, [onImported])

  useEffect(() => {
    cappeApi.get<CappeStoryOptions>(`/sites/${siteId}/stories/options`)
      .then((res) => setTopics(res.topics))
      .catch(() => setTopics([]))
  }, [siteId])

  const search = async (src: CappeStockSource, q: string, page: number) => {
    if (!q) return
    const gen = ++generation.current
    setSearching(true)
    setError(null)
    try {
      const params = new URLSearchParams({ source: src, q, page: String(page) })
      const res = await cappeApi.get<CappeStockSearch>(`/sites/${siteId}/library/search?${params}`)
      if (gen !== generation.current) return
      setLast(res)
      setResults((prev) => (page === 0 ? res.results : [...prev, ...res.results]))
      if (page === 0) setPicked([])
    } catch (e) {
      if (gen === generation.current) setError(message(e, 'That search didn’t work. Try again.'))
    } finally {
      if (gen === generation.current) setSearching(false)
    }
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    void search(source, query.trim(), 0)
  }

  const pickSource = (src: CappeStockSource) => {
    setSource(src)
    if (query.trim()) void search(src, query.trim(), 0)
  }

  // A result already in the library, or already on its way, can't be picked.
  const jobByKey = new Map(jobs.map((j) => [stockKey(j), j]))
  const unavailable = (r: CappeStockResult) => {
    const job = jobByKey.get(stockKey(r))
    return r.imported || (job ? job.status !== 'failed' : false)
  }

  const toggle = (r: CappeStockResult) => {
    const key = stockKey(r)
    setPicked((list) => (list.includes(key) ? list.filter((k) => k !== key)
      : list.length >= MAX_PER_IMPORT ? list : [...list, key]))
  }

  const track = useCallback((res: CappeStockImports) => {
    setJobs((prev) => {
      const byId = new Map(prev.map((j) => [j.id, j]))
      for (const j of res.imports) byId.set(j.id, j)
      return [...byId.values()]
    })
    for (const j of res.imports) {
      // By import and picture: a picture deleted and imported again comes
      // back on the same import row with a new library picture.
      if (j.status === 'ready' && j.asset && !delivered.current.has(`${j.id}:${j.asset.id}`)) {
        delivered.current.add(`${j.id}:${j.asset.id}`)
        onImportedRef.current(j.asset)
      }
    }
    if (res.remaining_today != null) setRemaining(res.remaining_today)
  }, [])

  const queue = async (path: string, body: Record<string, unknown>) => {
    setQueueing(true)
    setError(null)
    try {
      track(await cappeApi.post<CappeStockImports>(path, postId ? { ...body, post_id: postId } : body))
      setPolls(0)
      setPicked([])
    } catch (e) {
      setError(message(e, 'Those pictures couldn’t be imported. Try again.'))
    } finally {
      setQueueing(false)
    }
  }

  const importPicked = () => {
    const items = results.filter((r) => picked.includes(stockKey(r)))
      .map((r) => ({ source: r.source, source_id: r.source_id }))
    void queue(`/sites/${siteId}/library/import`, { items })
  }

  const stockTopic = () => {
    if (topic) void queue(`/sites/${siteId}/library/stock-topic`, { topic, count: 12 })
  }

  const open = jobs.filter(importOpen)
  const openIds = open.slice(0, MAX_PER_IMPORT).map((j) => j.id).join(',')

  useEffect(() => {
    if (!openIds || polls >= MAX_POLLS) return
    let alive = true
    const t = setTimeout(() => {
      cappeApi.get<CappeStockImports>(`/sites/${siteId}/library/imports?ids=${openIds}`)
        .then((res) => { if (alive) track(res) })
        .catch(() => { /* the next poll tries again */ })
        .finally(() => { if (alive) setPolls((n) => n + 1) })
    }, pollMs)
    return () => { alive = false; clearTimeout(t) }
  }, [siteId, openIds, polls, pollMs, track])

  const ready = jobs.filter((j) => j.status === 'ready').length
  // One line per reason, however many pictures it covers.
  const problems = new Map<string, number>()
  for (const j of jobs) {
    if (j.status !== 'failed' && j.status !== 'refused') continue
    const why = j.error || 'That picture couldn’t be imported.'
    problems.set(why, (problems.get(why) || 0) + 1)
  }
  const hint = STOCK_SOURCES.find((s) => s.key === source)?.hint

  return (
    <section className={`${ui.card} flex flex-col gap-4 p-4`} aria-label="Find free photos">
      <div className="flex flex-wrap gap-1" role="tablist" aria-label="Archive">
        {STOCK_SOURCES.map((s) => (
          <button
            key={s.key}
            type="button"
            role="tab"
            aria-selected={source === s.key}
            onClick={() => pickSource(s.key)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${source === s.key ? 'bg-emerald-500/15 text-emerald-400' : 'text-zinc-400 hover:bg-zinc-800'}`}
          >
            {s.label}
          </button>
        ))}
      </div>

      <form onSubmit={submit} className="flex flex-wrap gap-2" role="search">
        <label className="relative min-w-[12rem] flex-1">
          <span className="sr-only">Search {STOCK_SOURCES.find((s) => s.key === source)?.label}</span>
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-zinc-500" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} maxLength={120}
            placeholder="Harbour at dawn, street fashion, the moon…" className={`${ui.input} pl-9`} />
        </label>
        <button type="submit" className={ui.btnPrimary} disabled={!query.trim() || searching}>
          {searching && <Loader2 className="h-4 w-4 animate-spin" />} Search
        </button>
      </form>
      <p className="-mt-2 text-xs text-zinc-500">
        {hint}. Only pictures you may publish and crop are shown, each with the credit printed under it.
      </p>

      {error && <p role="alert" className="text-sm text-red-400">{error}</p>}

      {last && results.length === 0 && !searching && (
        <p className="rounded-xl border border-dashed border-zinc-800 px-4 py-8 text-center text-sm text-zinc-500">
          Nothing we can publish for “{last.query}”. Try other words or another archive.
        </p>
      )}

      {results.length > 0 && (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4" aria-label="Results">
          {results.map((r) => {
            const key = stockKey(r)
            const off = unavailable(r)
            const on = picked.includes(key)
            return (
              <li key={key} className={`overflow-hidden rounded-lg border ${on ? 'border-emerald-500' : 'border-zinc-800'}`}>
                <button type="button" onClick={() => toggle(r)} disabled={off} aria-pressed={on}
                  aria-label={`${on ? 'Unpick' : 'Pick'} ${r.title || r.credit_line}`}
                  className="relative block aspect-[4/3] w-full bg-zinc-900 disabled:cursor-default">
                  {r.thumb && (
                    <img src={`${cappeApiBase}${r.thumb}`} alt={r.title} loading="lazy" className="h-full w-full object-cover" />
                  )}
                  <span className="absolute left-1.5 top-1.5 rounded bg-black/70 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                    {licenseLabel(r.license, r.license_version)}
                  </span>
                  {(on || off) && (
                    <span className={`absolute right-1.5 top-1.5 inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold ${on ? 'bg-emerald-500 text-black' : 'bg-black/70 text-zinc-200'}`}>
                      <Check className="h-3 w-3" /> {on ? 'Picked' : 'In library'}
                    </span>
                  )}
                </button>
                <div className="flex items-start gap-1 px-2 py-1.5">
                  <p className="line-clamp-2 flex-1 text-[11px] text-zinc-400" title={r.credit_line}>{r.credit_line}</p>
                  {r.landing_url && (
                    <a href={r.landing_url} target="_blank" rel="noreferrer noopener" aria-label="Where it came from"
                      className="text-zinc-500 hover:text-zinc-300"><ExternalLink className="h-3 w-3" /></a>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      )}

      {last?.has_more && (
        <button type="button" className={`${ui.btnGhost} self-center`} disabled={searching}
          onClick={() => void search(last.source, last.query, last.page + 1)}>
          More from {STOCK_SOURCES.find((s) => s.key === last.source)?.label}
        </button>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t border-zinc-800 pt-3">
        <button type="button" className={ui.btnPrimary} disabled={!picked.length || queueing} onClick={importPicked}>
          {queueing && <Loader2 className="h-4 w-4 animate-spin" />}
          {picked.length ? `Import ${picked.length} picture${picked.length === 1 ? '' : 's'}` : 'Choose pictures to import'}
        </button>
        {topics.length > 0 && (
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <label>
              <span className="sr-only">Topic to stock</span>
              <select value={topic} onChange={(e) => setTopic(e.target.value)} className={ui.input}>
                <option value="">Stock a topic…</option>
                {topics.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
              </select>
            </label>
            <button type="button" className={ui.btnGhost} disabled={!topic || queueing} onClick={stockTopic}>
              <Wand2 className="h-4 w-4" /> Add 12 pictures
            </button>
          </div>
        )}
      </div>

      {(jobs.length > 0 || remaining != null) && (
        <div className="flex flex-col gap-1 text-xs text-zinc-400" aria-live="polite">
          {jobs.length > 0 && (
            <p>
              {open.length > 0 && <Loader2 className="mr-1 inline h-3 w-3 animate-spin" />}
              {open.length > 0
                ? `Importing… ${ready} of ${jobs.length} in your library.`
                : `${ready} of ${jobs.length} in your library.`}
              {open.length > 0 && polls >= MAX_POLLS && ' The rest will appear in your library when they’re done.'}
            </p>
          )}
          {[...problems].map(([why, n]) => (
            <p key={why} className="text-amber-400">{n > 1 ? `${n} pictures: ` : ''}{why}</p>
          ))}
          {remaining != null && <p>You can import {remaining} more today.</p>}
        </div>
      )}
    </section>
  )
}
